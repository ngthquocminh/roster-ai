---
baseline_commit: 0091dcf364c557eea00c49da39423c1822ce3e49
---

# Story 2.2: Establish the Deterministic Evaluation Harness

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a product engineer,
I want one versioned evaluation harness available from the first agent slice,
So that every epic proves its own behavior deterministically instead of deferring correctness evidence to a late release milestone.

**This is the Epic 2 enabler that follows 2.1.** It ships no planner-visible feature and defines no real capability. It builds the *machinery* that every later evaluation-bearing story (2.9, 3.10–3.12, 4.5–4.6, 6.4) runs its own cases through — the shared runner, the case schema, the report generator. It does not, and must not, build those stories' cases.

**Story 2.1 is done.** The `AgentRuntime` port (`backend/application/ports/agent_runtime.py`), its owned contracts (`backend/application/contracts/agent_runtime.py`), the `PydanticAIAgentRuntime` adapter (`backend/agent/runtime.py`), and one throwaway demonstration tool (`shiftmind_demonstration`) all exist and are green. This story consumes that seam; it does not modify it.

**Unblocks:** the evaluation acceptance criteria in Stories 2.9, 3.10–3.12, 4.5–4.6, and 6.4 — all of them read "runs on the Story 2.2 harness."

## Acceptance Criteria

1. **Given** normal CI **when** the evaluation harness runs **then** it executes against deterministic model doubles and version-controlled fixtures with no live provider call, and any live-provider suite is separately named, explicitly gated, budgeted, and marked non-authoritative **and** a live-provider result can never satisfy a release gate on its own. *(NFR26, AR16)*

2. **Given** any evaluation report the harness produces **when** it is persisted as release evidence **then** it binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions **and** a report missing any binding is rejected rather than recorded. *(NFR27)*

3. **Given** a reviewed failure from any epic **when** it is sanitized and added to the golden dataset **then** the harness accepts it as a version-controlled regression case tagged with its owning capability and risk class **and** each epic's proof stories contribute their cases to the same dataset so the Release Gate can measure the aggregate. *(NFR28)*

## Tasks / Subtasks

- [x] **Task 1: Define the golden-dataset case schema and create `backend/evals/`** (AC: #3)
  - [x] New top-level package `backend/evals/` — AR26's structural seed names it `# versioned AI and architecture proof datasets`. This is the only new top-level backend package this story creates; Story 2.1 deliberately left it unscaffolded for this story to own.
  - [x] `backend/evals/cases.py` — a frozen-dataclass case schema (not a cross-epic `V1` contract; this is dataset/test infrastructure, not a persisted product contract, so it does not join AD-20's sixteen-name list). One case declares, per Story 2.9's own line ("expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state"): a stable case ID, an owning **capability** tag (free-text string; no relation to `CapabilityManifestV1` — that contract is Story 2.6's), a **risk class** restricted to AD-5's exact five values (`Literal["inspect", "draft", "compute", "consequential", "prohibited"]`). **Verified: no such literal exists in the repo yet** — nothing under `backend/` declares these five values today, because the registry that will enforce them is Story 2.5's. So you define it here, and you define it as a *dataset tag vocabulary*, not as the registry's authority type: it labels which class a case belongs to, and grants nothing. Use AD-5's five values exactly and invent no sixth; when Story 2.5 builds the real registry it may lift this vocabulary or define its own authoritative one — either way an out-of-vocabulary tag must be impossible here, a scripted turn (prompt + expected tool-call sequence with arguments), an expected outcome (`allow` / `refuse` / `clarify`), expected evidence references (empty tuple is valid — most Epic 2 cases have none yet), and expected visible state/text.
  - [x] `backend/evals/golden/` — the version-controlled case files live here as JSON, one case per file or grouped by capability subdirectory; your call, document whichever in the README (Task 8).
  - [x] **Acceptance boundary:** a loader test round-trips one hand-written case file through JSON → dataclass, and a case with an out-of-vocabulary `risk_class` (e.g. `"dangerous"`) is rejected at load time, not silently accepted.

- [x] **Task 2: Generalize the spike's model doubles into a reusable, case-driven double builder** (AC: #1)
  - [x] `backend/evals/doubles.py` — builds a deterministic PydanticAI double from a case's scripted tool-call/response sequence. This is what Story 2.1's "unblocks" line means by *"formalizes the model doubles this spike proves"*: `backend/spikes/agent_runtime/` and `backend/tests/test_agent_runtime_adapter.py`'s hand-written `FunctionModel` callables (e.g. `_demo_then_report`) are the pattern; this task makes that pattern **data-driven** so a new golden case needs a new JSON file, not a new Python function.
  - [x] `models.ALLOW_MODEL_REQUESTS = False` at module scope — this module must never be able to reach a network, by construction, same as `backend/tests/test_agent_runtime_adapter.py:35`.
  - [x] Drive cases through the **real** `AgentRuntime` port (`PydanticAIAgentRuntime.run_turn()`), never a bespoke parallel runner. The point of this harness is to prove the seam Story 2.1 built, not a second one that could silently diverge from it.
  - [x] **Acceptance boundary:** one demonstration case runs end to end through `PydanticAIAgentRuntime.run_turn()` using only the generated double, and the test asserts on the returned `AgentRunOutcomeV1` — an owned type, never a framework type (mirrors Story 2.1's Task 9 "assertions on owned types only" rule).

- [x] **Task 3: Build the tool-routing evaluator and its extension point** (AC: #1, #3)
  - [x] `backend/evals/evaluators.py` — define an `Evaluator` `Protocol` judged against `(case, AgentRunOutcomeV1) -> EvalVerdict` (pass/fail + a reason string). Ship **exactly one** evaluator in this story: tool routing — does the actual tool name + arguments (or the correct absence of a tool call, for a `refuse`/`clarify` case) match the case's expected outcome. This is what NFR28's "≥90% overall tool routing, 100% consequential/prohibited routing" measures against.
  - [x] **Do not build the grounding evaluator (NFR12, Story 2.7) or the refusal/injection evaluator (Story 2.9) here.** The `Protocol` is the extension point those stories plug into later — pre-building them speculatively is exactly the kind of scope creep Story 2.1's Dev Notes warned against for the capability registry.
  - [x] **Acceptance boundary:** three unit tests — a correct-routing pass, a wrong-tool fail, a wrong-arguments fail — each asserting the verdict's reason string names what differed.

- [x] **Task 4: Wire the deterministic default suite and a separately gated live variant** (AC: #1)
  - [x] `backend/tests/test_evaluation_harness.py` — plain pytest, **no marker**, `models.ALLOW_MODEL_REQUESTS = False` at module scope. Loads every case under `backend/evals/golden/`, builds its double (Task 2), runs it through the real adapter, evaluates it (Task 3), and asserts pass. This is the suite normal CI runs; per AC1 it must reach zero network calls, ever.
  - [x] Live variant: **reuse the existing `live` marker** (`backend/pyproject.toml:51`, excluded by default via `addopts = -m "not live"`) — do not invent a second marker or a parallel gating mechanism. Add `@pytest.mark.live` test(s) at the bottom of the same file (mirroring `backend/tests/test_gemini_provider.py`'s single-file, mostly-deterministic-plus-one-live-block shape) that run the **same** golden cases against a real provider via `create_agent_runtime()`, and `@pytest.mark.skipif` cleanly when no API key is present (mirror `test_gemini_provider.py:28,243-244`'s `_HAS_KEY` pattern).
  - [x] A live run's result must be marked non-authoritative wherever it could be persisted or aggregated (e.g. a `run_source: Literal["double", "live"]` field on whatever result type Task 5's report consumes) — AC1's "a live-provider result can never satisfy a release gate on its own" has to be true of the *data shape*, not just of a marker CI happens to exclude by default.
  - [x] **Acceptance boundary:** a default `uv run --frozen pytest` run touches network zero times and passes; `uv run --frozen pytest -m live` is collected, runs (or skips cleanly without a key), and is demonstrably excluded from the default run.

- [x] **Task 5: Report generation bound to NFR27, rejecting an incomplete binding** (AC: #2)
  - [x] `backend/evals/report.py` — aggregate case verdicts (pass/fail counts; tool-routing percentage overall and separately for `consequential`+`prohibited` cases only) and call `scripts/evidence_binding.resolve_bindings()` to produce the `version_bindings` block. **Reuse it, do not reimplement it** — it already refuses a dirty tree and a missing declared key (`ValueError` naming which key), which is most of what AC2 asks for. Your job is supplying the seven declared keys correctly for an eval report: `evaluator`, `model`, `prompt`, `tool`, `policy`, `application`, `solver`.
  - [x] **Resolve this before writing the generator — it is a real design gap, not a style choice.** `resolve_bindings()` derives **both** `dataset` and `scenario` from the same Gate A `default_fixtures()` list (`fixture_id:version` pairs) — see `evidence/story-1.5/nfr35-evidence-target-resolution.json`'s `version_bindings.dataset` and `.scenario`, which are near-identical strings. That was correct for Gate A evidence, where the thing measured and the scenario fixture used were the same set. It is **not** correct here: this story's `dataset` binding must describe the *golden evaluation dataset* (case count, tag distribution, its own version) — a new artifact this story creates — while `scenario` should describe which Gate A scenario fixture, if any, a case actually touched (Task 7's demonstration-tool cases touch none at all, since `shiftmind_demonstration` reads no scenario data).
    - `resolve_bindings(fixtures=...)` already accepts an override — any object with `.fixture_id`/`.version` attributes counts, matching `scripts/gate_a_cutover.py:FixtureSpec`'s shape. Passing a synthetic single entry there is the mechanism, but doing so naively still aliases `dataset` and `scenario` to the same value, which does not fix the gap.
    - Decide, and record the decision and rationale in Dev Notes (matching Story 2.1's decision-recording convention): either (a) add a small, backward-compatible extension to `evidence_binding.py` — e.g. an optional parameter that lets `dataset` be derived independently (count + sha256 of the committed golden-dataset files, mirroring `contract_digests()`'s own file-hash pattern) while `scenario` keeps deriving from `fixtures=` (empty/`"not applicable"` when no case touches scenario data); or (b) some other resolution you can justify — but do not ship a report where `dataset` silently equals `scenario` with no rationale recorded, and do not change the derivation for existing Gate A call sites (`resolve_bindings()`'s default behavior with no override must keep working unmodified for `evidence/story-1.4`, `-1.5`, `-1.9`, `-1.10`, `-1.11`).
  - [x] Make "a report missing any binding is rejected rather than recorded" literal: the file is written **only after** `resolve_bindings()` returns successfully. No partial or placeholder file on failure.
  - [x] **Acceptance boundary:** a test asserting an incomplete declared-bindings call raises and writes no file, and a complete call writes a JSON file that `backend/tests/test_evidence_convention.py`'s repo-wide `evidence/**/*.json` walk accepts unmodified (that test file needs no change — it already covers "a new evidence file in a later epic... automatically").

- [ ] **Task 6: Produce this story's own demonstration evidence file** (AC: #1, #2)
  - [ ] Follow `docs/EVIDENCE-CONVENTION.md` exactly: commit the code from Tasks 1–5 and 7 first, confirm `git status --porcelain` is empty, run the deterministic suite (Task 4) on that clean tree, generate `evidence/story-2.2/evaluation-harness-demonstration.json` via Task 5's generator, then commit the evidence file separately.
  - [ ] **State explicitly, in the report and in Completion Notes, that this is a demonstration of the machinery — not a claim on NFR28's 50-case Gate B floor.** Gate B (`epics.md`'s Release Gate table, "Golden dataset size" row) is measured later, after Stories 2.9, 3.10–3.12, and 4.5–4.6 have all contributed their own cases; this story's seed cases (Task 7) exist only to prove the harness runs, evaluates, and reports correctly end to end.
  - [ ] **Acceptance boundary:** `evidence/story-2.2/evaluation-harness-demonstration.json` exists, passes `backend/tests/test_evidence_convention.py`, and its `git_commit` is a real ancestor of `HEAD` that touches a code file (not a docs-only commit — this convention document names that exact defect).

- [x] **Task 7: Seed cases against the one tool that actually exists** (AC: #3)
  - [x] Add a small number of golden cases (this is a schema/shape demonstration, not a dataset-size target — see Task 6) exercising `shiftmind_demonstration`, the **only** tool Epic 2 has today (`backend/agent/runtime.py:126-130`). Tag them `capability="demonstration"` — deliberately not a real capability name; do not fabricate a `scheduling_inspect`-shaped case that Story 2.5 hasn't built yet.
  - [x] Cover at least: one `repeat=1` case (executes freely, no approval — tag `risk_class="inspect"`, the closest AD-5 analog for a read-only free-running call) and one `repeat>1` case (suspends for approval — tag `risk_class="consequential"`, since AD-5 defines that class as needing "exact-action approval," which is exactly what `ApprovalRequired` triggers here).
  - [x] **Do not write cases for capabilities that don't exist.** Real cases for Stories 2.5, 2.7, 2.9, etc. are those stories' job, per `epics.md`'s own unblocks list — this story proves the schema and pipeline accept a contribution, not that Epic 2's real capabilities are covered.
  - [x] **Acceptance boundary:** at least one `allow`-outcome case and one `consequential`/approval-required case, both tagged per Task 1's schema and passing under Task 4's deterministic suite.

- [ ] **Task 8: Document the regression-case contribution workflow** (AC: #3)
  - [ ] `backend/evals/README.md` — the case schema (Task 1), the tag vocabulary (capability is free text; risk class is exactly AD-5's five values), and the contribution workflow: a reviewed failure is sanitized (secrets/PII scrubbed — NFR4: "Secrets never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures") and added as a new version-controlled case file under `backend/evals/golden/`, carrying its own case-level version distinct from any contract `schema_version`. State explicitly that Stories 2.9, 3.10–3.12, and 4.5–4.6 contribute their **own** cases to this **same** directory — this story does not write those cases, only the pipeline that accepts them.
  - [ ] Add a lightweight schema-validation guard (can live in Task 4's test file or its own small test) that fails CI if any file under `backend/evals/golden/` does not validate against Task 1's schema — so a malformed future contribution fails loudly rather than being silently skipped by the loader.
  - [ ] **Acceptance boundary:** README exists and states the exact fixture shape from `epics.md` Story 2.9's AC ("expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state"); the validation guard demonstrably fails on a temporarily-injected malformed case file and passes on the shipped tree (same red-then-green discipline Story 2.1's Task 9 used).

- [ ] **Task 9: Make the harness's own boundary executable** (AC: #1)
  - [ ] Extend `backend/tests/architecture/test_agent_runtime_boundaries.py` (or add a sibling file in the same directory — your call, document which) asserting `backend/evals/**` contains no live network call by construction: `models.ALLOW_MODEL_REQUESTS = False` appears at module scope in every module under `backend/evals/` that constructs a PydanticAI model, and no module under `backend/domain/**` or `backend/application/**` imports `evals` (dependency direction: `evals` may import `agent`/`application`/`domain`; the reverse must fail).
  - [ ] **Acceptance boundary:** the guard fails when temporarily given a violating case, and passes on the shipped tree — demonstrate both, per Story 2.1's established convention for this suite.

- [ ] **Task 10: Full regression gate** (AC: #1, #2, #3)
  - [ ] Backend: `uv run --frozen pytest`; `uv run --frozen pytest -m postgres` (Docker PostgreSQL 18 via `docker-compose.yml`); `uv run --frozen pytest -m live` (confirm it skips cleanly with no key present, and does not run by default); `alembic check` shows zero diff — this story adds no migration.
  - [ ] Frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`. This story changes no frontend file; the suites must stay green regardless.
  - [ ] **Re-run Gate A explicitly and report by name.** AR28's "no later gate may weaken an earlier gate's invariants" still binds every Epic 2 story: regenerate `evidence/story-1.11/gate-a-readiness-report.json` and confirm it still reads `gate_a_passed: true`.
  - [ ] **Re-derive the baselines at the start rather than trusting these.** Story 2.1's own final change-log entry recorded 485/486 backend tests green (1 self-skip from a dirty-tree self-check, matching Story 1.11's documented pattern) at its `done` commit; re-derive the exact current numbers on a clean tree before treating any delta as this story's own regression.
  - [ ] **Acceptance boundary:** every suite green at its re-derived baseline plus this story's new tests, `pytest -m live` confirmed skippable without a key, and Gate A still `true`.

## Dev Notes

### What this story is, and what it is not

It is: a versioned case schema, a reusable deterministic-double runner over the real `AgentRuntime` seam, one evaluator (tool routing) plus the extension point for the rest, an NFR27-bound report generator, and a handful of demonstration cases proving all of it works.

It is **not**:

| Not this | Owned by |
|---|---|
| The grounding evaluator that checks numerical claims (NFR12) | Story 2.7 |
| The refusal/clarification/injection evaluator and its fixtures | Story 2.9 |
| Real capability cases (scheduling inspect, proposals, approvals, etc.) | Stories 2.5, 2.7, 2.9, 3.10–3.12, 4.5–4.6 |
| The 50-case / ≥4-per-capability / ≥10-consequential-or-prohibited NFR28 floor | Measured in aggregate at Gate B, after those stories land — see the `epics.md` dataset-threshold caveat below |
| `CapabilityManifestV1` and capability registration | Story 2.6 |
| Any chat UI, route, or frontend change | Stories 2.3–2.8 |
| Any modification to `backend/agent/`, `backend/application/ports/agent_runtime.py`, or `backend/application/contracts/agent_runtime.py` | Story 2.1 (done) — this story is a consumer, not a modifier, of that seam |

### The dataset-threshold caveat this story must not accidentally violate

From `epics.md`'s Release Gate section, verbatim: *"The 50-case floor was set when thirteen Epic 5 stories were expected to contribute cases. The hosted stories now in Epic 6 contribute infrastructure assertions rather than agent-behavior cases, so the floor must be re-verified against the actual contribution of Stories 2.9, 3.10–3.12, and 4.5–4.6 when Epic 2's harness lands. If it does not hold, lower the threshold with a recorded rationale — never pad the dataset to reach it."* This story is the harness that "lands" — it is not the moment to re-verify the floor (that needs the later stories' real contribution counts), and it is absolutely not license to pad Task 7's demonstration cases toward 50. Say in Completion Notes that the floor re-verification is future work for whoever writes Story 2.9 or the Gate B report, not something this story attempted.

### The `dataset` vs. `scenario` binding trap

This is the single most likely place to under-think this story, because the existing tool (`evidence_binding.resolve_bindings()`) makes the wrong shape trivially easy to produce (see Task 5). NFR27 lists `dataset` and `scenario` as two *separate* bindings. Every existing evidence file (Stories 1.4, 1.5, 1.9, 1.10, 1.11) has them read as near-identical strings because, for Gate A, the thing being measured against genuinely *was* the Gate A scenario fixture set. For an evaluation-harness report, they are genuinely different things: `dataset` is *this story's own golden case set*; `scenario` is *which Gate A scenario fixture, if any, a case touched* — which for Task 7's demonstration-tool cases is none at all. Do not ship a report where a demonstration-tool run's `scenario` binding reads as if it touched real scenario data.

### Existing conventions to match, not reinvent

| Need | Copy the pattern from |
|---|---|
| Deterministic model double construction | `backend/tests/test_agent_runtime_adapter.py` (`FunctionModel`, `models.ALLOW_MODEL_REQUESTS = False`), `backend/spikes/agent_runtime/tests/test_capabilities.py` |
| Gated live test, skip-if-no-key | `backend/tests/test_gemini_provider.py:28, 243-249` (`_HAS_KEY`, `@pytest.mark.live`, `@pytest.mark.skipif`) |
| NFR27 version-binding resolution | `backend/scripts/evidence_binding.py:resolve_bindings()` — reuse, do not reimplement |
| Evidence generation workflow | `docs/EVIDENCE-CONVENTION.md` — commit code → measure clean → generate → commit evidence separately |
| Architecture boundary guard shape (red then green) | `backend/tests/architecture/test_agent_runtime_boundaries.py` |
| Frozen-dataclass schema, `Literal` vocabularies | `backend/application/contracts/agent_runtime.py` |
| Absolute imports from the backend root | every module — `from evals.cases import ...`, never relative |

### Anti-patterns for this story

- **Do not build a second agent-execution path.** Cases must run through the real `PydanticAIAgentRuntime.run_turn()` / `AgentRuntime` port, not a parallel hand-rolled call into PydanticAI. That would prove nothing about the seam Story 2.1 built.
- **Do not install `pydantic_evals`** or the `pydantic-ai` meta-package's `evals` extra. Story 2.1 deliberately pinned `pydantic-ai-slim[google,openrouter]` to avoid pulling it in; this story's harness is hand-built, not framework-supplied.
- **Do not build the grounding or refusal evaluators.** Ship the `Protocol` extension point only; Stories 2.7 and 2.9 own their own evaluator implementations.
- **Do not fabricate cases for capabilities that don't exist yet** (no pretend `scheduling_inspect` cases before Story 2.5 ships it).
- **Do not pad the golden dataset toward 50 cases.** That is an aggregate measured at Gate B from every proof story's real contribution, not a target for this enabler.
- **Do not let `dataset` silently alias `scenario`** in a report where they should differ (see the trap above).
- **Do not add a second live-gating mechanism.** Reuse the existing `live` marker (`backend/pyproject.toml:51`) exactly as `test_gemini_provider.py`/`test_openrouter_provider.py` already do.
- **Do not touch `backend/agent/**`, `backend/application/ports/agent_runtime.py`, or `backend/application/contracts/agent_runtime.py`.** This story consumes that seam; modifying it is out of scope and would re-open Story 2.1's closed acceptance boundary.
- **Do not weaken Gate A.** Re-run and re-confirm `gate_a_passed: true` (Task 10).
- **Do not hand-type the evidence file.** Generate it through `resolve_bindings()` per `docs/EVIDENCE-CONVENTION.md`; hand-typing is the exact defect that produced Epic 1's four unreproducible `git_commit` bindings.

### Previous Story Intelligence (from Story 2.1, `done`)

- **Environment:** local venv is Python **3.10.9** (not the 3.12 container target); `backend/pyproject.toml` allows `>=3.10,<3.13`. `pydantic-ai-slim[google,openrouter]==2.27.0` is locked; `opentelemetry-sdk` is a **dev-group-only** test dependency (added for Story 2.1's telemetry-content guard) — reuse it if this story needs to assert on emitted spans, do not re-add it.
- **Markers:** `live` (excluded by default, `addopts = -m "not live"`) and `postgres` (skips cleanly with no DB) already exist — this story adds no new marker.
- **pytest runs from `backend/`**; `testpaths = ["tests"]`, `backend/conftest.py` makes backend modules importable via `sys.path.insert`. A directory outside `backend/tests/` is not collected — this is why Story 2.1 put its architecture suite at `backend/tests/architecture/` rather than the spine's nominal root-level `tests/architecture/`, and why this story's `test_evaluation_harness.py` belongs under `backend/tests/`, not under `backend/evals/` itself.
- **The demonstration tool:** `shiftmind_demonstration` (`backend/agent/runtime.py:126-130`), typed via `DemonstrationRequestV1(label: str, repeat: int = 1)`. `repeat == 1` executes freely; `repeat > 1` raises `ApprovalRequired` and suspends. This is the only tool this story's seed cases (Task 7) may exercise.
- **`AgentRunOutcomeV1`** (`backend/application/contracts/agent_runtime.py`) is the type every case's evaluator judges: `status` (`completed`/`suspended`/`timed_out`/`failed`), `output_text`, `turn` (owned transcript), `approval` (pending calls, when suspended), `tool_results`. There is no framework type anywhere in this shape — evaluators must never import `pydantic_ai`.
- **A skipped test is not a passed test** — Story 1.11's rule, restated by Story 2.1's Task 7/9 tests. Nothing this story adds may self-skip in the default run.
- **Baselines at Story 2.1's `done` commit** (`0091dcf`, this story's `baseline_commit`): backend 485/486 green (1 self-skip from a dirty-tree self-check test, expected to pass on a clean tree); frontend 50 files/287 tests; e2e 46; alembic zero diff; Gate A `gate_a_passed: true`. Re-derive before trusting (Task 10).

### Git Intelligence (recent commits on `story/2-1-agent-runtime-boundary`)

`0091dcf` (fix: code review findings for 2.1) → `2ee48ec` (docs: regenerate Gate A readiness) → `a28ea28` (feat: establish the owned AgentRuntime boundary) → `b38500c` (docs: story context for 2.1) → `7f268e0` (docs: trim Epic 2-5 scope, split Epic 6). This story branches from `0091dcf`; the `AgentRuntime` seam it consumes was last touched there.

### Project Structure Notes

- **New:** `backend/evals/` (`__init__.py`, `cases.py`, `doubles.py`, `evaluators.py`, `report.py`, `README.md`, `golden/**` case files), `backend/tests/test_evaluation_harness.py`, an addition to `backend/tests/architecture/` (Task 9), `evidence/story-2.2/evaluation-harness-demonstration.json`.
- **Modified:** possibly `backend/scripts/evidence_binding.py` (Task 5's dataset/scenario decision, if you choose the extension path — keep it backward-compatible; every existing Gate A call site must keep working with no changes).
- **Not modified:** `backend/agent/**`, `backend/application/ports/agent_runtime.py`, `backend/application/contracts/agent_runtime.py`, `backend/llm/**`, `backend/services/**`, `backend/domain/**`, any migration, any frontend file.
- **Structural seed note:** `backend/evals/` is the AR26 structural-seed slot for "versioned AI and architecture proof datasets" — it holds both the harness code and the golden case files, mirroring how `backend/agent/` holds Story 2.1's adapter code. Test *invocation* code still lives under `backend/tests/` because that is the only directory pytest collects (`testpaths = ["tests"]`), matching the variance Story 2.1 already recorded for `backend/tests/architecture/`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md, lines 638-661] — Story 2.2 statement, unblocks line, and all three acceptance criteria, verbatim
- [Source: _bmad-output/planning-artifacts/epics.md, lines 162, 165] — AR16 (deterministic model doubles, versioned golden datasets, bound release reports) and AR19 (existing ports preserved — not this story's concern, cited for continuity)
- [Source: _bmad-output/planning-artifacts/epics.md, lines 97, 127, 129] — NFR12 (grounding evaluator, Story 2.7's), NFR27 (the eleven bindings), NFR28 (the 50-case floor, ≥4/capability, ≥10 consequential/prohibited, ≥90%/100% tool routing)
- [Source: _bmad-output/planning-artifacts/epics.md, lines 151] — AR5: the application-owned registry's exactly-five risk classes (`inspect`, `draft`, `compute`, `consequential`, `prohibited`) and their meaning
- [Source: _bmad-output/planning-artifacts/epics.md, lines 838-841] — Story 2.9's AC naming the exact case shape ("expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state") and "the cases are contributed to the shared golden dataset tagged by capability and risk class"
- [Source: _bmad-output/planning-artifacts/epics.md, lines 1508-1527] — the Release Gate table (Story 2.2 named as evidence owner for "Deterministic-first CI" and "Report version binding") and the dataset-threshold caveat this story must not violate
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md, lines 72-76] — AD-5: governed capability modules, the exact five risk classes and their authority meaning
- [Source: ARCHITECTURE-SPINE.md, lines 180-184] — AD-16: deterministic-first release evidence, the eleven-binding rule, and that authorization/grounding/idempotency/etc. regressions block release regardless of aggregate helpfulness
- [Source: ARCHITECTURE-SPINE.md, lines 198-202] — AD-19, cited for continuity: this story must not touch the `AgentRuntime` seam it defines
- [Source: ARCHITECTURE-SPINE.md, lines 293-303] — the structural seed naming `backend/evals/` as "versioned AI and architecture proof datasets," the slot this story fills
- [Source: docs/EVIDENCE-CONVENTION.md] — commit → measure clean → generate → commit-separately; the four Epic 1 evidence files' `git_commit` defect this convention exists to prevent; the "code that was measured" rule Task 6 follows
- [Source: backend/scripts/evidence_binding.py] — `resolve_bindings()`, `NFR27_BINDING_KEYS`, `DERIVED_BINDING_KEYS`/`DECLARED_BINDING_KEYS`, `DirtyTreeError`, `contract_digests()`'s file-hash pattern (a template for an independent `dataset` digest, if you take that path)
- [Source: evidence/story-1.5/nfr35-evidence-target-resolution.json] — a worked example of `resolve_bindings()`'s output shape, and the concrete evidence that `dataset`/`scenario` currently alias each other
- [Source: backend/tests/test_evidence_convention.py; backend/tests/test_gemini_provider.py, lines 13-14, 28, 243-249] — the repo-wide evidence walk this story's new file must satisfy unmodified, and the `_HAS_KEY`/`@pytest.mark.live`/`@pytest.mark.skipif` pattern Task 4's live variant copies
- [Source: backend/pyproject.toml, lines 48-54] — the `live`/`postgres` markers and `addopts = "-m \"not live\""`, reused rather than duplicated
- [Source: backend/agent/runtime.py, lines 46-54, 109-130] — `DemonstrationRequestV1`, the `shiftmind_demonstration` tool, and its conditional-approval shape (`repeat == 1` free, `repeat > 1` suspends) that Task 7's seed cases exercise
- [Source: backend/application/contracts/agent_runtime.py] — `AgentRunOutcomeV1` and every owned type an evaluator may inspect; no framework type crosses this boundary
- [Source: backend/application/ports/agent_runtime.py] — the `AgentRuntime` Protocol and `AgentRuntimeError` this story's runner drives, never bypasses
- [Source: backend/tests/test_agent_runtime_adapter.py, lines 1-64] — the hand-written `FunctionModel` double pattern (`_demo_then_report`, `_call_demo`) Task 2 generalizes into data-driven form
- [Source: backend/tests/architecture/test_agent_runtime_boundaries.py] — the red-then-green architecture-guard convention Task 9 follows
- [Source: backend/scripts/gate_a_cutover.py, lines 41-45, 76-89] — `FixtureSpec(path, fixture_id, version)` and `default_fixtures()`, the shape `resolve_bindings(fixtures=...)` expects for an override
- [Source: _bmad-output/implementation-artifacts/2-1-establish-the-owned-agent-runtime-boundary.md] — full previous-story context: environment facts, conventions, anti-patterns, and the final baseline this story's Task 10 re-derives from
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml, Story 2.1 creation note] — Story 2.2 explicitly named as the story that "formalizes the model doubles this spike proves"; confirms Task 2's framing
- [Source: git log 7f268e0..0091dcf] — the commit sequence this story branches from

## Dev Agent Record

### Agent Model Used

GPT-5 Codex (bmad-dev-story)

### Implementation Plan

1. Re-derive all clean-tree baselines, then implement the case schema, reusable
   deterministic double, and single tool-routing evaluator in strict task order
   with red-green-refactor tests.
2. Add the default and live-gated harness paths, then extend
   `resolve_bindings()` backward-compatibly so evaluation datasets bind
   independently from scenario fixtures.
3. Add only the two demonstration-tool seed cases, document contribution rules,
   prove architecture guards red then green, and keep the Story 2.1 runtime seam
   at a zero-line diff.
4. Commit code, measure on a clean tree, generate Story 2.2 evidence through the
   report generator, commit evidence separately, regenerate Gate A, and finish
   the full regression/DoD sequence.

### Debug Log References

**Clean baseline re-derived before implementation (2026-08-10, `5ce7d1b`):**
backend 486 passed / 6 deselected; PostgreSQL 27 passed / 465 deselected;
frontend 50 files / 287 tests; e2e 46 passed; typecheck, lint, build, and
`alembic check` all green. The first concurrent frontend attempt exhausted
Vitest workers and collided on preview port 4173; sequential reruns restored the
recorded 50/287 and 46/46 baselines without code changes.

**Task 5 dataset/scenario decision:** extended `resolve_bindings()` with an
optional `dataset_files=` derivation path. Evaluation datasets are parsed for
case count, case versions, capability/risk distributions and pinned by raw
per-file SHA-256; `fixtures=` independently describes scenario data, with an
explicit empty set rendered as `not applicable`. Gate A callers omit
`dataset_files`, so their existing default derivation and every Story
1.4/1.5/1.9/1.10/1.11 call site remain unchanged. This keeps both bindings
derived (never caller-authored prose) while representing their genuinely
different identities for Story 2.2.

### Completion Notes List

- Task 1: added the frozen evaluation-case schema and strict JSON loader. The
  five AD-5 values are explicitly dataset tags, not authority; malformed JSON,
  mixed scripted-turn shapes, and out-of-vocabulary risks fail loudly.
- Task 2: generalized Story 2.1's hand-written `FunctionModel` pattern into a
  case-driven builder with model requests disabled at module scope; its test
  runs through the real adapter and asserts only on `AgentRunOutcomeV1`.
- Task 3: shipped the `Evaluator` Protocol and exactly one implementation,
  `ToolRoutingEvaluator`; correct routing, wrong tool names, and wrong arguments
  have explicit reason-string tests. No grounding or refusal evaluator added.
- Task 4: default evaluation is unmarked and network-disabled; the existing
  `live` marker collects a key-gated variant. `EvalVerdict.run_source` makes
  live results non-authoritative by construction, not by CI convention alone.
- Task 5: report generation aggregates overall and protected-class routing and
  resolves all NFR27 bindings before creating a file. `dataset_files=` now
  derives an independent, hashed golden-dataset identity while all Gate A
  default call sites retain their original behavior.
- Task 7 (Task 6 prerequisite): added exactly two `demonstration` cases—one
  free-running `inspect` call and one approval-suspended `consequential` call.
  They prove the schema/pipeline only and do not pad toward NFR28's Gate B floor.

### File List

- `backend/evals/__init__.py` (new)
- `backend/evals/cases.py` (new)
- `backend/evals/doubles.py` (new)
- `backend/evals/evaluators.py` (new)
- `backend/evals/report.py` (new)
- `backend/scripts/evidence_binding.py` (modified)
- `backend/evals/golden/demonstration/repeat-once.json` (new)
- `backend/evals/golden/demonstration/repeat-with-approval.json` (new)
- `backend/tests/test_evaluation_harness.py` (new)
- `_bmad-output/implementation-artifacts/2-2-establish-the-deterministic-evaluation-harness.md` (modified)

## Change Log

| Date | Change |
|---|---|
| 2026-08-10 | Story created. |
