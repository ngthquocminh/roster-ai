# Evidence Convention

How every `evidence/**/*.json` file in this repository must be produced.

Enforced mechanically by `backend/scripts/evidence_binding.py` (at generation
time) and `backend/tests/test_evidence_convention.py` (repo-wide, on every test
run). Read this before writing any story that produces evidence.

## The rule

**Commit the code first. Then measure. Then generate. Then commit the
evidence separately.**

```
loop: write/fix code → run tests freely      ← dirty tree is fine, this is development
git commit code                              ← tree becomes clean
run the measurement                          ← THIS is the run that gets recorded
generate evidence (script; refuses if dirty) ← HEAD now names exactly the tree measured
git commit evidence                          ← separate commit
```

There is no chicken-and-egg problem. `git_commit` names **the code that was
measured**, not the commit that contains the report. Provided the tree is clean
at generation time, the hash is exact and the measurement is reproducible by
anyone who checks that commit out.

## Two kinds of test run

These are different activities and conflating them is what caused the defect
below.

| | Development iteration | Recorded measurement run |
|---|---|---|
| Purpose | make the code work | produce evidence |
| Tree state | dirty, constantly | **must be clean** |
| How often | continuously | once, at the end |
| Output | your judgement | `evidence/**/*.json` |

Run the suite as often as you like while building. Only the run performed on a
clean tree, immediately before generating the evidence file, is the one the
evidence describes.

## Why this exists

Every one of Epic 1's first four evidence files recorded an unreproducible
binding:

| Evidence file | Recorded `git_commit` | Commit that really added the code |
|---|---|---|
| story-1.4 | `80ef64eb…` | `dd84595 feat(1-4)` |
| story-1.5 | `f1eab57f…` | `e925c07 feat(1-5)` |
| story-1.9 | `e2b2038f…` | `366bd4e feat(1-9)`, later `f27bafd` |
| story-1.10 | `29ac7a1d…` — a **docs-only** commit | `d986707 feat(1-10)`, later `a42e8b7` |

Each was hand-typed at the "run tests" step, *before* the commit containing its
code existed, so `git rev-parse HEAD` returned the parent. Each honestly
recorded `working_tree_dirty: true` — which is precisely what makes the binding
unusable, because the uncommitted diff it refers to is recorded nowhere.

It repeated four times because each story was told to copy the previous story's
file as a template. Nobody was asked to reconsider the template, only to
imitate it. Hence: generate, never hand-type.

## What `resolve_bindings()` enforces

```python
from scripts.evidence_binding import resolve_bindings, contract_digests

bindings = resolve_bindings({
    "evaluator": "...",     # you supply the prose bindings
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": "...",
    "policy": "...",
    "application": "...",
    "solver": "not applicable — no solver run",
})
```

* **Refuses a dirty tree.** `git status --porcelain` non-empty — *including
  untracked `??` entries* — raises `DirtyTreeError` listing the offending paths.
* **Derives, never hardcodes:**
  * `code.git_commit` from `git rev-parse HEAD`, and `code.working_tree_dirty`
    computed live on every generation
  * `schema_version` by walking `down_revision` across
    `backend/migrations/versions/*.py` to the single head — a file-graph walk,
    so report generation never needs PostgreSQL running
  * `dataset` / `scenario` by importing `default_fixtures()` from
    `backend/scripts/gate_a_cutover.py` — never a second copy of the list
  * `image` as `"local source tree"` / `postgres:18`. There is no registry and
    no image pipeline; a fabricated digest would be a false binding. Immutable
    digests arrive with Epic 5 (Stories 5.5–5.7).
* **Emits all eleven NFR27 bindings plus `schema_version`.** A binding that
  does not apply keeps its key and states the reason — it is never omitted.
* **Rejects a caller that supplies a derived binding.** Passing your own `code`
  block is the exact defect being prevented.

### The escape hatch

`allow_dirty=True` (`--allow-dirty` on the CLI) proceeds against a dirty tree
and **writes its own use into the report**:

```json
"binding_override": "--allow-dirty; tree was dirty at generation"
```

An override nobody can see in the output is not an override, it is a hole. Use
it only when a measurement genuinely cannot be taken on a clean tree, and say
why in the story.

### `contract_digests` uses a raw file hash

`contract_digests()` is the sha256 of the contract file's **bytes**. This is
deliberately *not* the RFC 8785 canonical-JSON rule in
`adapters/postgres/fixture_history.py`: that rule hashes fixture *payloads* to
establish database identity, which is a different thing from pinning the exact
bytes of a committed artifact. Do not "fix" one to match the other.

## What the repo-wide guard checks

`backend/tests/test_evidence_convention.py` walks **every** `evidence/**/*.json`
— not a named list — so a new evidence file in a later epic is covered
automatically. For each file it asserts:

* all eleven NFR27 bindings are present
* `schema_version` is present and lies **on the migration chain leading to the
  current head** — not necessarily equal to it, see below
* `working_tree_dirty` is `false`, or `binding_override` explains why not
* `git_commit` is a real object **and** an ancestor of `HEAD`
* the recorded commit **touches at least one code file** — a docs-only commit
  proves nothing about the behaviour the file claims to have measured

It skips gracefully when git is unavailable. It does **not** skip when an
assertion merely fails.

Two further things are checked and **reported as drift rather than as
violations**: whether every referenced path still exists, and whether
`contract_digests` still match the files on disk. Both answer "has the
repository moved on since the measurement?", which is worth knowing and is not
the same question as "was this evidence honestly produced?".

## Every rule over a committed artifact must be monotone

This is the principle the rest of the guard is built on, and it is here because
Story 1.11 got it wrong the first time.

> **Once an evidence file satisfies the audit, it must satisfy it forever —
> unless the file itself is edited.**

A rule that can flip from pass to fail because the *world* changed is not a
rule about the artifact. It is a time bomb. The distinction to hold on to:

| Question | Evaluated | Lives in |
|---|---|---|
| Was this evidence generated correctly? | when it is **written** | `resolve_bindings()` |
| Is this evidence still valid now? | every time it is **read** | `audit_evidence_file()` |

Story 1.11 originally specified — and correctly implemented — *"`schema_version`
present and equal to the current Alembic head"*. One rule doing both jobs. The
consequence was that adding a single Alembic revision would have turned every
evidence file in the repository red at once, dropped four Gate A checks to
`unbound`, and blocked the gate for a reason with nothing to do with the gate.
The two ways out would have been re-running every historical measurement, or
hand-editing `schema_version` — which is precisely the hand-typing this whole
document exists to prevent. A convention whose predictable failure mode is
"someone edits the evidence" is worse than no convention.

The tell is easy to spot once you know to look. In the same task list, one
bullet down, `git_commit` was specified as *"a real object **and an ancestor
of** `HEAD`"* — ancestry never breaks as history moves forward. The right shape
was already in the author's hands; what was missing was a pass applying it to
every rule.

**When writing a new rule, ask:** *"when the thing I am comparing against moves,
does an artifact that was correct become incorrect?"* If yes, the rule belongs
in drift reporting, or needs a monotone form (`is on the chain to`, `is an
ancestor of`, `was recorded as`) instead of an equality.

`backend/tests/test_evidence_convention.py::test_evidence_survives_a_future_migration`
locks this down: it builds a synthetic successor revision and asserts every
existing evidence file still binds. It is a test about the *rule's* lifecycle,
not about the data — which is the level both of this story's binding defects
slipped through.

This sweep is a *convention* guard. It deliberately does not assert semantic
content; the story-specific guards
(`test_scenario_projection.py` for Stories 1.4/1.5,
`test_gate_a_mutation_audit.py` for Story 1.9) still own that and stay as they
are.

## A verdict key Gate A can read

**Rule: an evidence file that claims to block release MUST expose a top-level
`passed` boolean, and MUST be registered in `backend/scripts/gate_a_checks.py`.**

`gate_a_readiness.py` reads `document.get("passed")` and nothing else. Anything
else — `result: "passed"`, `release_blocking: false`, a nested
`gates.*.passed` — is recorded by the gate as `"missing"`, with the detail
`evidence file records no 'passed' verdict`. That is by design: the gate fails
closed on a shape nobody anticipated rather than guessing.

The failure mode this rule exists to prevent is silent, and it happened twice
before it was caught. Story 3.10 introduced a report-style artifact carrying
`result`/`release_blocking` instead of `passed`, and registered it in no
`GateACheck`. Story 3.11 was then explicitly instructed to mirror 3.10's shape,
so the divergence propagated by instruction. Both stories ran Gate A, both
recorded `gate_a_passed: true, blocking: []`, and both took that as
confirmation — **but the gate passed precisely because the artifact was
unregistered.** An unregistered evidence file cannot block anything, so the
check that was supposed to detect the problem went green as a consequence of
the problem. This is the "guard that cannot go red" pattern the Epic 1-2
retrospective names as this project's most expensive, applied to the gate
itself rather than to a test.

Emitting `result` as well is fine — 3.11 emits both — but `passed` is the
contract.

Two further rules follow, both learned the same way:

* **No invariant may rest on a stored flag alone.** A registered evidence file
  pins a verdict from the commit that produced it, which is a past-tense answer
  to a present-tense question. Pair it with a live check on the generator, as
  `recovery_and_idempotency` pairs `recovery_and_idempotency_proof` (evidence)
  with `recovery_idempotency_report_machinery` (pytest). Enforced by
  `test_registry_covers_more_than_the_four_evidence_files`.
* **A generator's verdict must require the proof to have RUN.** A process exit
  code is not enough: `governed_postgres_engine` calls `pytest.skip` when
  PostgreSQL is unreachable, and an all-skipped pytest run exits 0. A generator
  reading only `returncode == 0` therefore stamps every PostgreSQL-backed gate
  `passed` against zero executed assertions. Read pytest's own JUnit report and
  require `tests > 0`, `skipped == 0`, `failures == 0`, `errors == 0` — see
  `_junit_outcome` in `backend/evals/recovery_idempotency_report.py`.

## Checklist for a new evidence-producing story

1. Build and iterate freely.
2. `git commit` the code.
3. Confirm `git status --porcelain` is empty.
4. Run the measurement.
5. Generate the evidence file through `resolve_bindings()` — never by hand.
6. Run `uv run --frozen pytest tests/test_evidence_convention.py`.
7. `git commit` the evidence on its own.
8. If the artifact claims to block release: emit a top-level `passed`, register
   it in `gate_a_checks.py`, and pair it with a live check on its generator.
   Otherwise nothing reads it and Gate A stays green because it is unbound.
