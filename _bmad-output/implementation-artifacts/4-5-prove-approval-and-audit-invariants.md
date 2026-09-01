---
baseline_commit: 9460a57
---

# Story 4.5: Prove Approval and Audit Invariants

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the product team,
we want consequential edge cases proven deterministically before release,
So that stale state, retries, or observability failure can never produce an unrecorded
baseline change.

**This is a PROOF story.** Epic 4's mechanism is complete: Story 4.1 landed TX1 and the three
tables, 4.2 landed the one decision endpoint and TX3, 4.3 landed TX2, 4.4 landed the read
projection, and 4.4a landed the audit-evidence carriage that gives this story a real oracle. What
does not exist yet is a *bound, release-blocking* record that the invariants hold — one that
Gate A reads, that fails when the behaviour regresses, and that cannot go green because a suite
was skipped.

**It lands exactly one production line of behaviour-bearing code** — one new `SCOPE_CONTROLS`
member (Decision 12) — plus one report generator, one evidence file, two Gate A registry entries,
and tests. **No migration, no new table or column, no new route, no new port, no contract field,
no new setting, no new dependency, and a zero-line frontend diff.**

**Depends on, and consumes:** Story 4.1's `approval_request` / `site_baseline` / `audit_event`
schema, `ApprovalBindingV1`, `AuditEnvelopeV1` and the two audit uniqueness indexes; Story 4.2's
`revalidate_binding` and TX3; Story 4.3's TX2 and its rollback-by-escaping-exception contract;
Story 4.4's `PostgresAuditReader` and `SCOPE_CONTROLS`; Story 4.4a's `candidate.evidence_refs`
carriage at all four write sites and the `evidence_ref_records=` hook already present in
`_seed_candidate_run`; Story 3.11's `recovery_idempotency_report.py` generator shape and its
`_junit_outcome` skip-is-not-a-pass rule; Story 1.5's six `resolve_*` exact-target methods;
Story 2.2's deterministic-double discipline and `resolve_bindings()`.

**Unblocks:** Story 4.6, whose state matrix asserts against the literal states and reasons this
story pins, and the Epic 4 retrospective.

**Scope summary:** One new PostgreSQL-marked test module proving the epic's seven verification
obligations against real Postgres and the real route; one new `backend/evals/approval_audit_report.py`
mirroring Story 3.11's generator; its own machinery test; one new NFR29 invariant plus two
`GateACheck` entries in `backend/scripts/gate_a_checks.py`; one line added to the evidence-path
exact set in `test_gate_a_readiness.py`; one positive `SCOPE_CONTROLS` member closing
`deferred-work.md:623`; and `evidence/story-4.5/approval-audit-invariants.json` generated through
`resolve_bindings()` on a clean tree.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| Epic 4's proof matrix is **seven named verification obligations**, each requiring a demonstrated-red case: initial promotion, replacement, stale/expired/rejected, reconnect, idempotent replay, rollback, audit integrity. "A passing guard that cannot be made to fail by a relevant mutation does not count." | `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md` — "Verification Obligations" |
| Revalidation has **one fixed fork**: any *business* mismatch terminalizes to `stale` (or `expired`) and never retries; only a *transactional or infrastructure write fault* rolls the bundle back, leaving the binding `pending`. "Story 4.5 proves both arms of this fork distinctly." | spine EAD-10; `ADR-4-consequential-workflow.md` — D7 |
| The three atomic bundles are TX1 / TX2 / TX3; the `effect_key` for all three is the `approval_id` minted at TX1, disambiguated by the closed outcome vocabulary. | spine EAD-6; ADR-4 D7 |
| Expiry is **lazily materialized and reads never write**. A query, render, reconnect, or SSE replay that observes `now() >= expires_at` presents the binding as expired and persists nothing; the terminal `expired` state materializes only inside a decision-attempt transaction. | spine EAD-7; ADR-4 D7 |
| Success audit is unique on `(site_id, effect_key, outcome)`; non-success audit is unique on `(site_id, attempt_id)`. Telemetry can never authorize, block, or substitute. | parent `ARCHITECTURE-SPINE.md` — AD-12; spine EAD-6 |
| Approval, idempotency, and authoritative-audit regressions **block release regardless of aggregate helpfulness**, and every release report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code and image versions. | parent AD-16; NFR29; NFR27 |
| An evidence file that claims to block release **must** expose a top-level `passed` boolean **and** be registered in `gate_a_checks.py`; no invariant may rest on a stored flag alone; a generator's verdict must require the proof to have RUN (`tests > 0, skipped == 0, failures == 0, errors == 0`). | `docs/EVIDENCE-CONVENTION.md` — "A verdict key Gate A can read" |
| Commit the code, then measure, then generate through `resolve_bindings()`, then commit the evidence separately. Never hand-type an evidence file. | `docs/EVIDENCE-CONVENTION.md` — "The rule" |
| Every rule over a committed artifact must be **monotone**: `is on the chain to`, `is an ancestor of`, `was recorded as` — never an equality against something that moves. | `docs/EVIDENCE-CONVENTION.md` — "Every rule over a committed artifact must be monotone" |
| Every consequential audit row already carries the checksum-bound `evidence_refs` of the candidate its attempt **targeted** — not evidence the attempt consulted — and a row whose candidate does not resolve carries an honest empty set. | `4-4a-supply-audit-evidence-references.md` — Decisions 1, 3, 4; `api/routers/approvals.py` — `decide_approval_route` denial arm |
| `EvidenceRefV1` resolution has exactly three outcomes. `version_mismatch` is decided **before** the payload is normalized, by comparing the pinned `scenario_version_id` against the scenario's *current* row; `not_found` means the version matched but no record carries that `record_id`. | `application/contracts/evidence_ref.py` — `ResolutionOutcomeV1`; `adapters/postgres/scenario_projection.py` — `_resolve_items` |
| **Assignments carry worker identity but no `family`**, and `family` is a property of a demand row alone. This story computes no metric and scopes nothing by family; the `baseline-assignments` group appears here only as an evidence-locator group, never as a measured quantity. | `docs/DOMAIN-MODEL.md` §2, §3 |
| CloudWatch diagnosis is **Epic 6's**, and an AC clause naming an unimplemented system is proven at the seam that exists and marked `NOT COVERED` with an owner — never with an invented double. | `application/use_cases/agent_availability.py` — `SCOPE_CONTROLS`; `deferred-work.md:506`; `3-9-continue-deterministic-work-during-model-outage.md` — Decision E |
| The 2026-09-01 course correction rewrote **AC3 only**: "AC1, AC2, AC4 untouched. Remains a pure proof story." | `sprint-change-proposal-2026-09-01.md:71` |

---

## Acceptance Criteria

Verbatim from `epics.md:1286-1315`, including the scope note that sits under the story heading.

**Evidence scope note.** In this codebase evidence is a version-bound projection locator
(`EvidenceRefV1` — `scenario_version_id` plus the checksum triple plus a record locator), not a
stored object; no evidence port and no object-storage adapter exists. AR12's and AR23's
create-only S3 evidence permissions are hosted-deployment requirements discharged by **Story 6.2**
(`epics.md:1463`), not by this proof story. The earlier restatement at
`sprint-change-proposal-2026-08-09-epics-2-5.md:149` removed the *hosted* dependency but kept an
object-storage premise that has no subject here; this AC removes the premise rather than softening
it a third time.

**AC1.**
**Given** mismatch, expiry, replay, altered parameter, changed baseline, changed membership/policy,
rejection, and repeated-decision fixtures
**When** the approval suite runs on the Story 2.2 harness
**Then** every invalid attempt fails closed with its exact terminal/pending outcome and zero
baseline effect
**And** every valid approval promotes once with one authoritative audit/event bundle. (FR18, FR19,
NFR8, NFR29)

**AC2.**
**Given** database failure during the promotion bundle
**When** any write in approval consumption, baseline pointer, audit, or event fails
**Then** the entire transaction rolls back and the binding remains pending
**And** retry can complete exactly once after the fault clears. (NFR9)

**AC3.**
**Given** promoted, rejected, expired, stale, and denied decisions, plus an evidence locator whose
pinned scenario version no longer resolves
**When** each audit event and provenance item for those decisions is resolved through the evidence
locator contract
**Then** every `EvidenceRefV1` resolves `resolved` against its pinned `scenario_version_id`, or
reports `not_found` or `version_mismatch` explicitly, and no record presents an unresolvable
locator as valid
**And** each audit row for an attempt that resolved a candidate carries that candidate's
checksum-bound references, while a row whose candidate is absent carries an empty set asserted as
absence rather than assumed. (AR12, AR23)

**AC4.**
**Given** telemetry export disabled and CloudWatch degraded independently
**When** approval, rejection, or stale attempts execute
**Then** product behavior and authoritative audit remain correct and inspectable
**And** audit continuity or idempotency regression blocks release. (FR21, NFR10, NFR29)

---

## Thirteen decisions were made at story creation — do not re-litigate them

Each decision states its mechanism **and what that mechanism does not cover**. The second half is
load-bearing: Story 4.2's Decision 10 named a goal and a mechanism that blocked only one of two
directions, and the gap shipped.

### Decision 1 — This is a proof story: it asserts, it does not build

The only production change is Decision 12's one `SCOPE_CONTROLS` member. Everything else is a
test, a generator, a registry entry, or a generated artifact. Story 4.4's Decision 12 established
the shape ("AC3 and AC4 are PROVEN here, not built"), and 4.4a exists precisely because a proof
story that authors both a mechanism and its own oracle cannot fail
(`4-4a-supply-audit-evidence-references.md` — Story section).

If a proof cannot be written without new production behaviour, that is a finding to escalate, not
a licence to add it. Record it in the ledger and in Completion Notes.

**Does NOT cover:** this rule does not forbid *extending an existing test helper*.
`_seed_candidate_run` and `_seed_agent_run` in `tests/test_approval_governance_postgres.py` may
gain keyword-only parameters, because a test helper is not production behaviour. It also does not
license fixing the three pre-existing ledger items this story merely proves stable — see
Decision 5 and Decision 13.

### Decision 2 — The proof matrix is the spine's seven verification obligations, and obligation 4 is split with Story 4.6

The spine assigns the seven obligations to "Story 4.5/4.6" jointly and does not divide them. This
story takes **1, 2, 3, 5, 6, and 7 in full**, and takes **the backend half of obligation 4**: an
overdue pending binding read through any pure path writes nothing — no state change, no audit row,
no persisted event — which is EAD-7's invariant and is not a rendering question.

Story 4.6 takes obligation 4's rendering half (the pause and its identifiers replay once; the
"pending, overdue" literal presented state joins the state matrix) and the presentation half of
obligation 3 (only currently valid actions are offered). AC1's fixture list names no reconnect
fixture, which is why the split falls here.

**Does NOT cover:** this story asserts nothing about SSE stream replay, browser reconnect, or
component rendering, and adds no Playwright or Vitest coverage. A regression in *how* the pause
renders will not be caught here; it is caught by Story 4.6.

### Decision 3 — AC1's eight fixtures map to named proof nodes, and both arms of the EAD-10 fork are proven distinctly

AC1 names eight fixture kinds. Each becomes at least one named node in the generator's
`PROOF_NODES` map, so a regression is attributable to a fixture rather than to "the approval
suite". The mapping, with the outcome each must produce:

| AC1 fixture | Expected literal outcome | Fork arm |
|---|---|---|
| mismatch (candidate missing / no longer feasible / run resource version moved) | binding `stale`, `agent_cancelled(approval_stale)`, audit `approval_stale`, zero baseline effect | business |
| expiry (`now() >= expires_at` at decision time) | binding `expired`, `agent_cancelled(approval_expired)`, audit `approval_expired` | business |
| replay (same `Idempotency-Key`, same body) | original semantic result, no second audit row, no second pointer movement | — |
| altered parameter (`parameter_hash` / `consequence_hash` differ) | binding `stale` | business |
| changed baseline (pointer moved, appeared, or disappeared vs the binding's expectation) | binding `stale` | business |
| changed membership (initiating actor's membership revoked) | binding `stale` | business |
| changed policy (`policy_version` bumped via `PolicyInputsV1`) | binding `stale` | business |
| rejection (explicit `decision: "reject"`) | binding `rejected`, `agent_cancelled(approval_rejected)`, audit `approval_rejected` | — |
| repeated decision (second decision against a terminal binding) | 409 `approval_not_pending`, one `approval_denied` row, zero baseline effect | business |
| **valid approval** (obligations 1 and 2: `baseline_version = null` → insert; non-null → CAS replace) | binding `consumed`, pointer moved once, exactly one `approval_consumed` audit row and one event, prior `schedule_version` rows unchanged | — |

Membership referent is the **initiating** actor's, per spine EAD-10's "Membership referent and
supplier" paragraph — the deciding actor is enforced at the session layer and is a different
guard. Do not recheck the deciding actor inside `revalidate_binding`.

**Does NOT cover:** the fork's *write-fault* arm is not in this table — it is AC2's, and
Decision 4 owns it. This table covers only the business arm plus the two valid promotions.

### Decision 4 — AC2 needs a genuine infrastructure fault, injected through `app.dependency_overrides`; the existing lost-CAS tests are not it

`test_lost_promotion_cas_escapes_route_and_rolls_back_the_real_transaction` and
`test_lost_consume_cas_escapes_route_without_partial_commit`
(`tests/test_approval_governance_postgres.py`) already prove real rollback — but the fault they
inject is a repository method returning `None`, which is a **business/concurrency outcome**, the
other arm of EAD-10's fork. `test_promote_baseline.py` and `test_decide_approval.py` prove that a
`DBAPIError` *propagates*, but they run against hand-written fakes with no database, so they prove
nothing about actual rollback.

AC2 says "any write in approval consumption, baseline pointer, audit, or event fails". The
mechanism: reuse the existing delegating-wrapper pattern those two tests already established — a
thin class forwarding every attribute to the real adapter via `__getattr__`, with exactly one
method overridden — but have the overridden method **raise** a real driver-level error instead of
returning `None`. Inject it through the seam FastAPI already exposes:
`app.dependency_overrides[get_approval_repository | get_site_baseline_writer | get_audit_writer |
get_conversation_repository]` (`backend/api/deps.py`). The error must escape the endpoint uncaught
so `site_context`'s `engine.begin()` rolls back on unwind — this is Story 4.3's contract, recorded
in `promote_baseline.py`'s module docstring, and returning a response from a transaction-owning
route is the exact structural unsafety `deferred-work.md` records beside the fixed
`AgentRunNotQueuedError` arm.

Four fault points, one node each. After each, assert: binding still `pending`, `site_baseline`
unchanged, **zero** `audit_event` rows for that `approval_id` from the faulted attempt, and the
agent run still `approval_required`. Then remove the override and replay the identical request
with the same `Idempotency-Key` — it must complete **exactly once**, producing the same row set a
first-attempt success produces.

**Does NOT cover:** this proves rollback of the *promotion* bundle (TX2). It does not inject faults
into TX1 or TX3, and it does not prove anything about a fault occurring after `COMMIT` has been
issued — the response-before-commit window at `deferred-work.md:574` is pre-existing, belongs to
every site-scoped route, and is explicitly not this story's.

### Decision 5 — `deferred-work.md:564` is ANSWERED by citing AC2, not implemented

That entry reads: *"A database write fault inside TX2 leaves no durable denial/failure audit row…
**Owner: Story 4.5**, whose AC2 explicitly owns database failure during the promotion bundle."*

Read AC2. It requires three things: the transaction rolls back, the binding remains pending, and
retry completes exactly once. **It does not ask for a durable audit row describing the faulted
attempt.** Writing one requires a second connection and a failure-recording policy that no epic
decision supplies, and writing it inside TX2 cannot survive the rollback — which is what the entry
itself says.

So: prove AC2 as written (Decision 4), and **re-point the ledger entry** with the mismatch stated
explicitly. Do not silently drop it, and do not build the second-connection failure recorder — that
is unrequested scope, and the frozen AC governs over the ledger's owner string
(the rule Story 3.11 recorded as its Trap 2 / Decision 1c).

**Does NOT cover:** re-pointing is a ledger edit, not a decision that the gap does not matter. State
in Completion Notes that an infrastructure fault inside TX2 is observable to the client (a 5xx and
a still-`pending` binding) but leaves no server-side row, and name the owner in the re-pointed
entry.

### Decision 6 — AC3 resolves audit-row locators in the TEST, through the six `resolve_*` port methods — never through `gate.py`

`application/grounding/gate.py` — `_locator_failure` is the only end-to-end resolver of an
`EvidenceRefV1` today, and it is the wrong one twice over: it is wired to `GroundedClaimV1` (a
claim-grounding path, never audit or provenance items), and it **relabels** the vocabulary — a raw
`not_found` becomes `"calculation_failed"`, because in that context the locator came from a trusted
calculator. AC3 names the three-member `ResolutionOutcomeV1` vocabulary, so a test reusing
`_locator_failure` would never observe the outcomes the AC asks about.

Resolve directly: dispatch each ref by `ref.group` through
`application/grounding/resolvers.py` — `resolver_name_for_evidence_group` to the matching
`PostgresScenarioProjectionReader.resolve_*` method, and assert the returned `outcome`.

Resolution stays in the test. 4.4a left this fork open deliberately
(`4-4a-supply-audit-evidence-references.md` — Open questions): adding resolution to the provenance
read would put a fallible call inside the read Story 4.4's AC3 requires to survive a telemetry or
model outage.

**Does NOT cover:** this adds **no production resolver**, so the provenance API continues to return
locators without resolving them. That is compatible with AC3, which forbids presenting an
unresolvable locator *as valid* — the API presents locators as locators and asserts no validity.
If a future story wants resolution at read time, it must decide the outage question 4.4 left open;
this story does not decide it.

### Decision 7 — `locks` and `baseline-assignments` refs are structurally `not_found`, and AC3 admits that

`PostgresScenarioProjectionReader.resolve_assignment` and `resolve_lock` both pass
`lambda: ()` into `_resolve_items` — those two projection groups are unpopulated in the adapter, so
once the version matches, every ref in either group is unconditionally `not_found`. Candidate
`evidence_refs` are built from `proposal.resolved_entities` plus one `"locks"` ref per preserved
lock (`application/use_cases/create_run_snapshot.py` — `_input_evidence`), so a `locks` ref is
reachable by construction even though `get_locks` returns `()` in production today.

AC3's wording is *"resolves `resolved` … **or** reports `not_found` or `version_mismatch`
explicitly"*. A `locks` ref reporting `not_found` therefore satisfies AC3. **Assert the expected
outcome per group, never a blanket "all resolved"** — a blanket assertion would either fail
honestly on a `locks` ref or, worse, pass only because no test fixture ever produced one.

**Does NOT cover:** this story does not wire the two empty resolvers, and it does not claim the
`locks`/`baseline-assignments` groups are resolvable. It records that their `not_found` is
*structural*, not a data accident, so a future story that populates them knows this assertion must
change with it.

### Decision 8 — "a locator whose pinned scenario version no longer resolves" is built by seeding a SUPERSEDING scenario version, never an orphan UUID

`_projection_row` selects the scenario's **current** version — ordered by numeric version ordinal
descending, `.limit(1)`. A pinned version therefore "no longer resolves" when a newer
`scenario_version` row exists for the same `scenario_id`. That is the real production hazard
(a fixture reload), and it is already recorded as a systemic limitation in the ledger's Story 3.8
entry.

Build it that way: mint the ref pinned to the seeded version, then insert a second
`scenario_version` row for the same scenario with a higher ordinal, then resolve → `version_mismatch`.

**Do not** mint a ref from a bare `uuid4()`. Story 4.4a's own review caught exactly that
(`4-4a-supply-audit-evidence-references.md` — Review Findings): a ref with no scenario context
resolves by construction and exercises nothing. The same review is why
`_seed_candidate_run` binds its refs to `ids["scenario_version"]` and the row's stored
`checksum_digest` — its inline comment names this story as the reason.

**Does NOT cover:** this constructs `version_mismatch`. The third shape — the resolver returning
Python `None` because the whole `scenario_id` is invisible to the site — is a *different* case
(non-disclosing cross-site behaviour, already proven by Story 4.4's provenance 404 tests). Assert
it separately if asserted at all; do not conflate `None` with `not_found`.

### Decision 9 — AC4 is proven at the seam that exists; the CloudWatch half is marked NOT COVERED with Epic 6 as owner

AC4 bundles two premises of different character. Only one has a local subject.

**"Telemetry export disabled" — real, and already half-proven.** Story 4.3's review found AC4's
observability clause asserted by a comment; the patch is
`test_authoritative_audit_survives_a_failing_span_exporter`
(`tests/test_approval_governance_postgres.py`), which drives a real `TracerProvider` +
`SimpleSpanProcessor` whose exporter raises on every call, asserts `exporter.calls >= 3` so the
case cannot pass vacuously, and then asserts the audit rows regardless. **That test covers approve
and denial only.** AC4 names "approval, rejection, or stale attempts", so this story extends the
same pattern to `rejected`, `expired` and `stale` — it does not reinvent it, and it does not
duplicate it into a new module if extending in place is cleaner.

For the *disabled* arm: there is no telemetry setting in `backend/settings.py` and no global
provider — `PydanticAIAgentRuntime` wires spans only if a caller injects a `tracer_provider`, and
production never does. Disabled is the structural default. Prove it the way Story 3.9 did, with an
import-absence assertion over the approval/promotion/audit modules rather than a config flag.

**"CloudWatch degraded independently" — no local subject.** CloudWatch appears in zero backend
source files. It is assigned to Epic 6 in three independent places:
`application/use_cases/agent_availability.py` — `SCOPE_CONTROLS`'s literal
`"NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6"`, `deferred-work.md:506`, and Story 3.9's
Decision E, which resolved a **structurally identical clause** on a different story. Follow that
precedent exactly: mark it `NOT COVERED` with the owner, in the ledger and in Completion Notes.
**Do not invent a CloudWatch double** — a test asserting a fake's behaviour proves nothing.

This is the same defect class the 2026-09-01 course correction removed from AC3. The proposal
recorded "AC1, AC2, AC4 untouched" (`sprint-change-proposal-2026-09-01.md:71`), so AC4's
CloudWatch half was never re-examined. It is being handled here at story level, the way 3.9 handled
its own, rather than by re-opening `epics.md` — that would be a course correction, not a story.
**Raise it as retrospective input.**

**Does NOT cover:** the disabled-arm import assertion proves the approval path does not *import*
telemetry. It does not prove behaviour under a partially-initialised global provider, and it is
not a substitute for the raising-exporter test — ship both arms.

### Decision 10 — "Blocks release" is a Gate A registry entry, not a sentence in a story

AC1 and AC4 both end with a release-blocking clause (NFR29). The mechanism that makes that true is
`backend/scripts/gate_a_checks.py`. An evidence artifact that declares itself release-blocking but
is registered nowhere **cannot block anything**, and Gate A then reports green *because* the proof
is unbound — the failure that happened twice (Stories 3.10 and 3.11) and is now a documented rule.

Land three registry facts:

1. A new `Invariant` in `NFR29_GATES` — key `approval_and_audit_invariants` — because NFR29 names
   approval, idempotency and authoritative audit in the same breath as the invariants already
   modelled there. It is not one of AR28's six; do not add it to `AR28_INVARIANTS`.
2. A `GateACheck` with `evidence_path="evidence/story-4.5/approval-audit-invariants.json"`.
3. A **second** `GateACheck` with `runner="pytest"` and `test_files=("backend/tests/test_approval_audit_report.py",)`,
   because no invariant may rest on a stored flag alone. This must be a separate check:
   `GateACheck.__post_init__` **raises** when one check declares both an `evidence_path` and
   `test_files`.

`test_gate_a_readiness.py` — `test_registry_covers_more_than_the_four_evidence_files` fails red if
the invariant rests on evidence alone, and `test_every_invariant_has_at_least_one_contributing_check`
fails red if the invariant is added with no check. Both are existing guards; let them do the work.

**Does NOT cover:** it does not retro-register Story 3.10's `repair-correctness.json`, which is
still bound to no `GateACheck` and emits `result` rather than `passed`. That is a separate,
equally mechanical change recorded at the top of `deferred-work.md`, and sweeping it here would be
unrequested scope.

### Decision 11 — The generator mirrors `recovery_idempotency_report.py`, not the thin-script shape

Two precedents exist. Story 3.12 used a thin one-off script because its proof was a single
Playwright run parsed for a marker. Story 3.11 used
`backend/evals/recovery_idempotency_report.py` because its proof was a matrix of independently
orchestrated pytest nodes. **This story is the second shape** — a named node per AC1 fixture, per
AC2 fault point, and per AC3/AC4 clause.

Mirror it structurally: a `PROOF_NODES` map of name → pytest node id; a `FAILURE_MODE_GATES` map
rolling nodes up to the AC clause each proves; a `DECLARED_BINDINGS` dict carrying the seven
declared NFR27 keys; `measure_approval_audit_suite()` running each node in a subprocess with
`--junitxml` and **never raising mid-loop** — a failed or timed-out node is a `False` verdict with a
recorded detail, and every other node still runs; `_junit_outcome()` reading pytest's own JUnit XML
and requiring `tests > 0`, `executed > 0`, zero failures, zero errors, zero skips; and
`write_approval_audit_report()` emitting a top-level `passed` boolean alongside `result` and
`release_blocking`, refusing to write at all when a declared binding is missing or the verdict
shape is incomplete.

The skip rule is the point: `governed_postgres_engine` calls `pytest.skip` when PostgreSQL is
unreachable, and an all-skipped run exits 0. Every node in this story is PostgreSQL-backed, so a
generator trusting `returncode == 0` would stamp the whole matrix `passed` with the database down.

**What AC1's "runs on the Story 2.2 harness" means here.** It does **not** mean adding
`GoldenCase` JSON under `backend/evals/golden/` and driving scripted model turns. That reading was
settled by Story 3.10 and followed by 3.11 and 3.12, all three of which contributed zero golden
cases: for a proof with no model-facing surface, "the harness" means the harness's shared,
story-agnostic machinery — deterministic-double discipline with no network, `resolve_bindings()`
for NFR27 bindings, and the dual-track default/`-m postgres` run. This story has no model-facing
surface at all, so that reading applies unchanged.

**Does NOT cover:** the generator contributes **zero** new golden cases. This story ships no
capability and no model-facing surface, so a golden case would be a case about nothing. The golden
total stays at its current count — do not pad it toward NFR28's floor.

### Decision 12 — The one production line: a positive scope control, closing `deferred-work.md:623`

Story 4.4a's AC4 removed `"audit_evidence_refs:empty_at_every_write_site"` from
`application/contracts/decision_provenance.py` — `SCOPE_CONTROLS`, correctly, because it was no
longer true. Nothing positive replaced it, so the module's machine-readable statement of what the
provenance surface guarantees is now silent about evidence references, and any future write site
could put anything into `evidence_refs` with no contract, constant, or test objecting. The ledger
names this story as the natural place to state it.

Add one member: `"audit_evidence_refs:mirrors_targeted_candidate"`, and update the exact-set
assertion at `tests/test_decision_provenance.py` in the same commit. Close the ledger entry citing
this story.

**Does NOT cover:** a scope control is a declaration, not an enforcement. It does not constrain the
write sites; the invariant itself is proven by AC3's tests. Stating it makes a future divergence
visible at review — it does not make one impossible.

### Decision 13 — This story builds its own evidence fixtures, closing `deferred-work.md:627`

`tests/test_promote_baseline.py` asserts the promotion-site evidence guard against a `Runs` object
imported from `tests/test_decide_approval.py`. The assertion is identity, so it satisfies 4.4a's
Decision 4 on the letter — but if anyone empties that fixture's `evidence_ref`, the guard silently
degrades to `() == ()` and nothing fails. The ledger names "Story 4.5 when it builds its own
evidence fixtures" as the revisit trigger.

Build AC3's fixtures locally in the new module, seeded through `_seed_candidate_run`'s existing
`evidence_ref_records=` parameter, and assert **non-emptiness explicitly** before asserting
identity — so an emptied fixture reddens here even if it stops reddening there.

**Does NOT cover:** it does not refactor `test_promote_baseline.py`'s import. That module's
coupling is the epic's established three-file split; this story adds an independent guard beside
it rather than restructuring someone else's test.

---

## Tasks / Subtasks

- [x] **Task 1 — Re-derive the baselines before writing anything** (Decision 1)
  - [x] Run, from `backend/`: `uv run --frozen pytest -q`, then `uv run --frozen pytest -m postgres -q`, then `uv run --frozen pytest tests/test_evidence_convention.py -q`. Record all three counts in Debug Log References.
  - [x] Run `npm test` and `npx playwright test` counts only if a frontend or e2e file is touched; per Decision 1 the frontend diff is zero, so record "not run — zero-line frontend diff" instead of a number.
  - Baselines inherited from Story 4.4 and **not verified**: backend 1426 passed / 3 failed / 7 skipped; PostgreSQL 127 passed / 1 failed; frontend 575 passed; Playwright 62 passed. The three backend failures were recorded as external and pre-existing (two retired-slug OpenRouter cases, one conftest-import fixture). **Re-derive before attributing any failure to this story.**
  - Acceptance boundary: no code is written until the numbers are in the Debug Log.

- [x] **Task 2 — Read the files this story asserts against** (Decision 1)
  - [x] `application/use_cases/decide_approval.py`, `promote_baseline.py`, `request_approval.py`; `api/routers/approvals.py`; `api/deps.py`; `adapters/postgres/approval.py`, `site_baseline.py`, `audit.py`; `adapters/postgres/scenario_projection.py` — `_resolve_items` and the six `resolve_*` methods.
  - [x] `tests/test_approval_governance_postgres.py` in full — it already carries every helper this story reuses (`_seed_candidate_run`, `_seed_agent_run`, `decision_http_client`, `_governance_headers`, `_use_case_dependencies`, `_decision_dependencies`, `_audit_row`, `site_ids`) and the two delegating-wrapper fault-injection tests Decision 4 builds on.
  - [x] `backend/evals/recovery_idempotency_report.py` and `tests/test_recovery_idempotency_report.py` — the shape Decision 11 mirrors.
  - Acceptance boundary: the File List records which of these were read, not merely opened.

- [x] **Task 3 — Create `backend/tests/test_approval_audit_invariants_postgres.py`** (AC1; Decisions 3, 13)
  - [x] `pytestmark = pytest.mark.postgres`. Import the existing helpers from `tests/test_approval_governance_postgres.py` rather than re-writing them; extend the helpers in place if a keyword is missing (permitted by Decision 1).
  - [x] One test per row of Decision 3's table. Each asserts the four facts together: binding state, `agent_run.status` + `status_reason`, the exact `(outcome, success)` audit row set for that `approval_id`, and that `site_baseline` is byte-for-byte unchanged where the row says "zero baseline effect".
  - [x] Obligation 1 (initial promotion): `baseline_version = null` against an empty `site_baseline`; assert the row is **inserted**, one `approval_consumed` audit row, one event.
  - [x] Obligation 2 (replacement): approve naming the exact current baseline; assert the CAS succeeded and prior `schedule_version` rows are unchanged in count and content.
  - [x] Obligation 5 (idempotent replay): replay across **both** AD-8 key shapes — the HTTP body-hash command key and the agent `(agent_run_id, tool_call_id)` effect key. Assert the original semantic result, no second audit row, no second pointer movement; then assert an altered body on the same key returns 409 `idempotency_key_conflict`.
  - [x] Obligation 4, backend half (Decision 2): drive every pure read path over an overdue pending binding — the GET, the provenance read, and the idempotent-replay lookup — and assert afterwards that the binding's stored `state` is still `pending`, `audit_event` count for that approval is unchanged, and no new `persisted_event` row exists.
  - Acceptance boundary: every assertion in this module is demonstrated-red once — weaken the guard or corrupt the fixture, observe the failure, restore, and record the RED→GREEN line in Debug Log References. A guard that cannot be made to fail by a relevant mutation does not count.

- [x] **Task 4 — Prove the EAD-10 fork on both arms distinctly** (AC1, AC2; Decisions 3, 4)
  - [x] Business arm: assert that every mismatch fixture in Decision 3's table terminalizes the binding and **never** leaves it `pending`.
  - [x] Write-fault arm: assert the binding is left `pending` and **never** terminalized.
  - [x] Add one test asserting the two arms are disjoint over the same starting fixture — the same binding, one path per arm, different terminal facts.
  - Acceptance boundary: a test that only exercises one arm does not satisfy this task; the spine requires both proven distinctly.

- [x] **Task 5 — Inject a genuine mid-bundle infrastructure fault and prove retry-once** (AC2; Decisions 4, 5)
  - [x] Build the delegating wrapper described in Decision 4 — `__getattr__` forwarding to the real adapter, one method raising a real driver-level error.
  - [x] Four nodes, one per TX2 write: approval consumption, baseline pointer, audit, event. Inject through `app.dependency_overrides` on the matching `get_*` dependency.
  - [x] After each fault assert: binding `pending`, `site_baseline` unchanged, zero `audit_event` rows for that approval from the faulted attempt, agent run still `approval_required`.
  - [x] Then remove the override and replay the identical request with the same `Idempotency-Key`; assert it completes exactly once and produces the same row set a first-attempt success produces.
  - Acceptance boundary: the fault must be observed to have fired (assert the wrapper's call counter, the way the exporter test asserts `exporter.calls`), or the case passes vacuously.

- [x] **Task 6 — Prove evidence-locator resolution over audit rows and provenance items** (AC3; Decisions 6, 7, 8, 13)
  - [x] Seed a candidate through `_seed_candidate_run(..., scenario_payload=..., evidence_ref_records=...)` with a payload real enough that at least one ref in a populated group resolves `resolved`.
  - [x] Drive all five outcomes named by AC3 — promoted, rejected, expired, stale, denied — read each resulting `audit_event.evidence_refs` back through `PostgresAuditReader`, and resolve every ref by group per Decision 6.
  - [x] Assert the expected outcome **per group** per Decision 7; assert `locks` / `baseline-assignments` refs report `not_found` and state in a comment that this is structural.
  - [x] Build the `version_mismatch` case per Decision 8 by inserting a superseding `scenario_version` row. Never an orphan `uuid4()`.
  - [x] Assert the AC3 identity clause in both directions: a row whose attempt resolved a candidate carries **exactly** that candidate's `evidence_refs`, asserted non-empty first (Decision 13); and a row whose candidate is absent carries `()` **asserted as absence** — drive the denial arm's `ValidationError` path so the empty set is observed, not assumed.
  - Acceptance boundary: no blanket "every ref resolved" assertion anywhere in this task.

- [x] **Task 7 — Extend the telemetry-independence proof to rejection and stale, and add the disabled arm** (AC4; Decision 9)
  - [x] Extend `test_authoritative_audit_survives_a_failing_span_exporter`'s pattern to cover `rejected`, `expired` and `stale` attempts. Keep the `exporter.calls >= N` assertion so no case can pass vacuously.
  - [x] Add the disabled arm as an import-absence assertion over the approval, promotion and audit modules, following Story 3.9's precedent rather than inventing a settings flag.
  - [x] Mark the CloudWatch half `NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6` in the ledger and in Completion Notes. Do not build a double.
  - [x] Record the AC4 wording defect as **Epic 4 retrospective input** per Decision 9 — do not edit `epics.md`.
  - Acceptance boundary: the existing approve/denial coverage is extended or reused, never duplicated into a parallel module.

- [x] **Task 8 — Prove audit integrity under concurrency** (AC1, AC4; obligation 7)
  - [x] Assert both uniqueness rules hold across the **whole** outcome vocabulary, not just the two members already covered: success on `(site_id, effect_key, outcome)`, non-success on `(site_id, attempt_id)`.
  - [x] Assert the three identity roles are distinguishable in every envelope written by TX1, TX2, TX3 and the denial arm — `initiated_by_actor_id`, `decided_by_actor_id`, and the worker facts, per spine EAD-3.
  - [x] Assert the two pre-existing, deliberately-unsuppressed shapes are **stable, not regressed**: repeated denials write repeated rows with distinct `attempt_id`s (`deferred-work.md:572`), and each carries the candidate's full `evidence_refs` (`deferred-work.md:625`). These are specified behaviour — prove them, do not fix them.
  - Acceptance boundary: a test that only re-proves what `test_approval_governance_postgres.py` already covers adds nothing; assert the members and roles it does not.

- [x] **Task 9 — Add the positive scope control** (Decision 12)
  - [x] Add `"audit_evidence_refs:mirrors_targeted_candidate"` to `SCOPE_CONTROLS` in `application/contracts/decision_provenance.py`.
  - [x] Update the exact-set assertion in `tests/test_decision_provenance.py` in the same commit.
  - [x] Close `deferred-work.md:623` citing this story.
  - Acceptance boundary: this is the story's only production line. If a second one appears, escalate per Decision 1.

- [x] **Task 10 — Write `backend/evals/approval_audit_report.py`** (AC1–AC4; Decision 11)
  - [x] `PROOF_NODES`, `FAILURE_MODE_GATES`, `DECLARED_BINDINGS`, `measure_approval_audit_suite()`, `write_approval_audit_report()`, `main()` — the `recovery_idempotency_report.py` shape.
  - [x] `_junit_outcome()` requiring `tests > 0`, `executed > 0`, zero failures, zero errors, zero skips.
  - [x] Never raise mid-loop: a failed or timed-out node is a recorded `False` verdict and the remaining nodes still run.
  - [x] Emit a top-level `passed` boolean per Decision 10, alongside `result` and `release_blocking`.
  - [x] Refuse to write when a declared binding is missing or the verdict shape is incomplete — `ValueError`, no file.
  - Acceptance boundary: the failure path is reachable and tested, not dead code.

- [x] **Task 11 — Write `backend/tests/test_approval_audit_report.py`** (Decisions 10, 11)
  - [x] Four cases mirroring `test_recovery_idempotency_report.py`: all-pass writes `passed: true` / `release_blocking: false`; one failing gate writes `passed: false` / `release_blocking: true` with a `failures` dict and **still writes the file**; an incomplete verdict shape raises `ValueError` and writes nothing; a missing declared binding raises `ValueError` naming the key and writes nothing.
  - [x] Add a case proving `_junit_outcome` refuses an all-skipped report — this is the check the whole Gate A registration rests on.
  - [x] All writes go to `tmp_path` with `allow_dirty=True`.
  - Acceptance boundary: `assert not output.exists()` on both refusal cases.

- [x] **Task 12 — Register the Gate A invariant and both checks** (AC1, AC4; Decision 10)
  - [x] Add the `Invariant` to `NFR29_GATES` in `backend/scripts/gate_a_checks.py`. Not to `AR28_INVARIANTS`.
  - [x] Add the evidence `GateACheck` and the separate machinery `GateACheck`. Two checks, never one — `__post_init__` rejects the combination.
  - [x] Add `"evidence/story-4.5/approval-audit-invariants.json"` to the **exact-set assertion** in `tests/test_gate_a_readiness.py`, with a comment saying why, in the style of the two entries already there. Its docstring says "Adding a fourth is a decision, not a detail" — this is such a decision.
  - [x] Confirm `test_every_invariant_has_at_least_one_contributing_check` and `test_registry_covers_more_than_the_four_evidence_files` pass, and confirm they were seen to fail first with only the evidence check registered.
  - Acceptance boundary: the registry additions are demonstrated-red through both existing guards.

- [x] **Task 13 — Generate the evidence file in the convention's order** (NFR27; `docs/EVIDENCE-CONVENTION.md`)
  - [x] `git commit` the code. Confirm `git status --porcelain` is empty.
  - [x] Run the measurement — `python -m evals.approval_audit_report` from `backend/`.
  - [x] Generate through `resolve_bindings()`; supply only the seven declared keys and never `dataset`, `scenario`, `code` or `image`.
  - [x] `uv run --frozen pytest tests/test_evidence_convention.py -q`.
  - [x] `git commit` the evidence **on its own**, and make sure the commit it binds to touches at least one code file.
  - Acceptance boundary: no hand-typed field anywhere in the artifact, and no docs-only commit between the code commit and the evidence commit.

- [x] **Task 14 — Reconcile the planning record** (Decisions 5, 9, 12, 13)
  - [x] Close `deferred-work.md:623` (Decision 12) and `:627` (Decision 13), citing this story.
  - [x] Re-point `:564` per Decision 5 with the AC-versus-ledger mismatch stated.
  - [x] Record `NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6` and the AC4 wording defect as retrospective input (Decision 9).
  - [x] Confirm `:572`, `:574` and `:625` are left open and untouched, and say so.
  - Acceptance boundary: no ledger entry is deleted; closure is recorded beside the original wording, per the file's own convention.

- [x] **Task 15 — Run every suite and record the deltas**
  - [x] `uv run --frozen pytest -q`, `uv run --frozen pytest -m postgres -q`, `uv run --frozen pytest tests/test_evidence_convention.py -q`.
  - [x] Confirm the CI floors in `.github/workflows/ci.yml` still hold. They are floors and ceilings, so added tests never redden them — do **not** edit the numbers.
  - Acceptance boundary: any failure is attributed against Task 1's re-derived baseline, never against Story 4.4's inherited one.

---

### Review Findings

Code review 2026-09-01. One decision-needed finding was resolved at review (option 3); it now
carries its chosen approach inline. Baselines re-derived before any attribution, per Task 1's own rule:
default `1482 passed, 1 skipped, 7 deselected`; `-m postgres` `147 passed, 1343 deselected`;
`test_evidence_convention.py` `80 passed`. Zero failures on all three — Story 4.4's inherited
"3 failed / 1 failed" no longer reproduces, so no finding below is attributable to a pre-existing
failure. Scope confirmed: the only `application/` diff is Decision 12's single `SCOPE_CONTROLS`
line; `gate_a_checks.py` is registry and in scope per Decision 10.

- [x] [Review][Patch] AC1's business-mismatch matrix is one case where Decision 3 names five — and four fixtures have no proof node at all — Decision 3's table has ten rows; `PROOF_NODES` covers six. `test_business_mismatch_terminalizes_stale` exercises **changed membership only** — one arm of the eight-term conjunction at `application/use_cases/decide_approval.py:92`. Altered parameter, changed baseline, changed policy and repeated decision have no node. The repeated-decision fixture is the subtlest miss: `test_repeated_denials_keep_distinct_attempts_full_refs_and_identity_roles` *looks* like it, but it drives `version=99` against a still-`pending` binding and produces `stale_resource_version`, not the `409 approval_not_pending` the table specifies; `approval_not_pending` appears zero times in the new module. **Resolved at review — option 3 (split by what each fixture can honestly demonstrate):** (a) add three new PostgreSQL cases to `test_approval_audit_invariants_postgres.py` — altered parameter (`UPDATE schedule_run SET resource_version`, which moves the `parameter` digest at `decide_approval.py:80`), changed baseline (promote a different pointer after the request), and candidate infeasible (`UPDATE schedule_version SET feasible_solver_status`); (b) register the existing real-route `approval_not_pending` node at `test_approval_governance_postgres.py:1085` for repeated decision rather than rewriting it; (c) register the existing fake-backed policy node for changed policy, with a comment recording **why it cannot be a PostgreSQL case**: `decide_approval.py:98` raises `ApprovalNotGrantedError` when `scheduling_baseline_enabled` is false, short-circuiting before `revalidate_binding` at line 109, and that flag is `derive_policy_version`'s only input — so bumping `policy_version` through `PolicyInputsV1` is unreachable via the real route, and a PostgreSQL test could only fake it by updating the binding's own stored `policy_version`, proving less than the fake node it would replace. Map all five into `FAILURE_MODE_GATES` under `stale/expired/rejected`.
- [x] [Review][Patch] Decision 3's "changed policy" fixture is unreachable through the real route — ledger entry — `derive_policy_version(PolicyInputsV1(scheduling_baseline_enabled))` has exactly one input, and `decide_approval.py:98` refuses the request before `revalidate_binding` ever runs when that flag is false. The `current_policy == binding.policy_version` arm of the `valid` conjunction (`decide_approval.py:92`) therefore has no real-route path that reaches it. This is a gap in Decision 3's table, not in the implementation. Record it in `deferred-work.md` under this review and carry it into the Epic 4 retrospective alongside the AC4 wording defect.
- [x] [Review][Patch] AC3 resolves locators for one of its five named outcomes [backend/tests/test_approval_audit_invariants_postgres.py:212] — `test_audit_evidence_refs_resolve_by_group` drives only `approve → approval_consumed`. AC3 and Task 6 name promoted, rejected, expired, stale **and** denied, each read back through `PostgresAuditReader` and resolved by group per Decision 6. `test_repeated_denials_...` reads a denied row's `evidence_refs` but never resolves them through a `resolve_*` method, so resolution-through-the-contract is proven for exactly one outcome of five.
- [x] [Review][Patch] AC3's absence clause is asserted nowhere; the only test near it asserts the opposite branch [backend/tests/test_approval_audit_invariants_postgres.py:283] — Task 6 requires driving the denial arm's `ValidationError` path (`api/routers/approvals.py:374`) so the `evidence_refs=()` at line 399 is **observed**, not assumed. No test corrupts a stored `schedule_version.payload` to make `get_candidate` raise. `test_repeated_denials_...` asserts `row.evidence_refs` is non-empty for both rows — the `candidate is not None` branch — which is the opposite arm. AC3's "asserted as absence rather than assumed" is therefore assumed.
- [x] [Review][Patch] Two tests pass in CI but gate nothing, defeating Decision 10 [backend/evals/approval_audit_report.py:17] — `test_repeated_denials_keep_distinct_attempts_full_refs_and_identity_roles` (Task 8's entire deliverable: uniqueness across the outcome vocabulary, the three EAD-3 identity roles, and the `deferred-work.md:572`/`:625` stability proofs) and `test_approval_audit_path_has_no_telemetry_import_dependency` (Decision 9's disabled arm) are absent from `PROOF_NODES`. A regression in either leaves the evidence artifact green and Gate A green — the exact unbound-proof failure Decision 10 says already happened at Stories 3.10 and 3.11. Add both nodes and map them into `FAILURE_MODE_GATES` (`audit integrity` and `stale/expired/rejected` respectively).
- [x] [Review][Patch] Shared module state is restored without `try/finally`, so one real failure cascades into seven [backend/tests/test_approval_audit_invariants_postgres.py:113] — `test_business_mismatch_terminalizes_stale` sets `membership.revoked_at` on `site_ids`, which is **module-scoped** (`test_approval_governance_postgres.py:77`, as is `governed_postgres_engine` at `conftest.py:83`), and restores it at line 120 *after* the assertion at lines 117-118. Demonstrated during review: injecting one simulated regression into that assertion produced `8 failed, 8 passed` — `rejection`, `replay`, all four `faulted_tx2` parametrizations and `evidence_resolution` failed for an unrelated reason. Seven of those eight are `PROOF_NODES`, so the artifact would report eight failed gates for one defect, destroying exactly the per-fixture attribution Decision 3 exists to provide. Wrap the revoke/restore in `try/finally` (or a fixture).
- [x] [Review][Patch] Task 5 asserts one of Decision 4's four post-fault facts [backend/tests/test_approval_audit_invariants_postgres.py:196] — Decision 4 and Task 5 both require, after each injected fault: binding `pending`, `site_baseline` unchanged, **zero** `audit_event` rows for that `approval_id` from the faulted attempt, and the agent run still `approval_required`. Only `binding pending` is asserted. The fault firing is proven soundly (`wrapper.calls == 1`) and the rollback is real, but three of the four facts AC2's "entire transaction rolls back" rests on are unobserved.
- [x] [Review][Patch] The two "exactly once" promotion tests assert membership, not multiplicity [backend/tests/test_approval_audit_invariants_postgres.py:70] — `_state()` returns a **set** of `(outcome, success)`, so duplicate rows collapse invisibly at precisely the assertion whose name claims "exactly once"; `test_replacement_is_exactly_once` likewise asserts the `site_baseline` row count and the pointer value but never that exactly one `approval_consumed` row exists, and never that prior `schedule_version` rows are unchanged in count and content as Task 3 requires. Compare `test_command_replay_is_idempotent`, which correctly uses `func.count()`. Defensible — `uq_audit_event_success_effect` makes a duplicate structurally impossible and `test_audit_uniqueness_covers_the_closed_outcome_vocabulary` proves that index directly — so this is an assertion/naming mismatch, not an unproven invariant. Also drop the vacuous `assert binding.approval_id` at line 259: a UUID is always truthy, and a guard that cannot go red is this story's own stated thesis.
- [x] [Review][Patch] The 4.5 registry block breaks `gate_a_checks.py`'s story-ordered sections [backend/scripts/gate_a_checks.py:491] — the `# ---- 4.5` block was inserted between the 3.11 checks and the `# ---- 3.12` section comment, so the file now reads 3.11, 4.5, 3.12. Cosmetic; move it after the 3.12 block.

**All nine patches applied at review (2026-09-01).** Suites after the fixes: default
`1490 passed, 2 skipped, 7 deselected`; `-m postgres` `156 passed` (+9); evidence convention
re-run below. `PROOF_NODES` grew from 15 to 28 named gates. Two further defects were found
*while* applying the patches, both recorded in `deferred-work.md` under this review rather than
papered over: Decision 3's `changed policy` fixture has no real-route path
(`decide_approval` short-circuits before `revalidate_binding`), and an infeasible candidate is
unrepresentable because `ScheduleVersionV1.feasible_solver_status` is a `Literal["OPTIMAL",
"FEASIBLE"]`. A third was found in the rollback proof: TX2 writes its event through
`append_approval_request_activity` on the planner path but `resume_agent_run_for_approval` on the
agent path, so the original single `event` fault node left one of the two write sites with no
rollback proof at all — it is now two nodes (`fault_event_resume`, `fault_event_activity`).

**Confirmed correct, raised and dismissed:** Decision 9's CloudWatch judgement. `NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6` follows Story 3.9's Decision E precedent, the literal already exists at `application/use_cases/agent_availability.py:21`, CloudWatch has no local subject, and routing the AC4 wording defect to the Epic 4 retrospective rather than editing `epics.md` is right — striking an AC clause is a course correction, not a story-level edit. The telemetry half is genuinely proven: the exporter extension to `rejected`/`expired`/`stale` raises the vacuity floor to `exporter.calls >= 6` and asserts the audit row per outcome.

**Also verified sound, not findings:** the evidence artifact (top-level `passed`, 15 gates matching `PROOF_NODES`, 12 binding keys, bound to code commit `d3f7391`, generated on a clean tree in convention order); `_junit_outcome`'s skip-is-not-a-pass rule and its machinery test; the fault-injection wrapper raising a genuine `DBAPIError` with a non-vacuous call counter; Decision 8's `version_mismatch` construction (`_VERSION_ORDINAL` strips non-digits, so the superseding `"v2"` row outranks the seeded `"v1"`); both Gate A guards demonstrated red; and the ledger reconciliation (`:623`/`:627` closed, `:564` re-pointed with the AC-versus-ledger mismatch stated, `:572`/`:574`/`:625` left open and untouched).


## Dev Notes

### Files being modified — read these before editing

| File | State today | This story changes | Must not break |
|---|---|---|---|
| `backend/tests/test_approval_audit_invariants_postgres.py` | does not exist | NEW — AC1–AC4 matrix | — |
| `backend/tests/test_approval_audit_report.py` | does not exist | NEW — generator machinery gate | — |
| `backend/evals/approval_audit_report.py` | does not exist | NEW — report generator | — |
| `evidence/story-4.5/approval-audit-invariants.json` | does not exist | NEW — generated, never hand-typed | — |
| `backend/tests/test_approval_governance_postgres.py` | 1385 lines; owns every helper this story reuses and the exporter test | helper keywords may be added; the exporter test is extended to rejection/expiry/stale | its 40+ existing tests, and `_seed_candidate_run`'s existing callers |
| `backend/application/contracts/decision_provenance.py` | `SCOPE_CONTROLS` is a four-member tuple after 4.4a | one member added | the exact-set assertion in `test_decision_provenance.py`, updated in the same commit |
| `backend/tests/test_decision_provenance.py` | asserts `set(SCOPE_CONTROLS)` equals the exact four-member set | the set gains one member | the rest of the provenance projection coverage |
| `backend/scripts/gate_a_checks.py` | `NFR29_GATES` has three invariants; `GATE_A_CHECKS` has 20 checks | one invariant, two checks | `validate_registry()`, and `__post_init__`'s refusal of evidence+test_files on one check |
| `backend/tests/test_gate_a_readiness.py` | registered evidence paths are an **exact set** of five | one path added, with a comment | every other registry guard in the module |
| `_bmad-output/implementation-artifacts/deferred-work.md` | `:564` `:623` `:627` open and pointed here | two closed, one re-pointed | `:506`, `:572`, `:574`, `:625` stay open and untouched |

### Traps — the quietest first

1. **The registered-evidence-path set is an exact equality, not a superset.** Adding
   `evidence/story-4.5/...` to `gate_a_checks.py` without also adding it to the assertion in
   `test_gate_a_readiness.py` reddens a test that reads as unrelated to this story. It is
   deliberate: the docstring says growth must be a decision.
2. **`GateACheck.__post_init__` raises on one check declaring both `evidence_path` and
   `test_files`.** The evidence branch would silently discard the test results. Two checks.
3. **An all-skipped pytest run exits 0.** Every proof node here is PostgreSQL-backed. Without
   `_junit_outcome`, the generator stamps the entire matrix `passed` with the database down —
   which is the exact failure the convention's rule was written for.
4. **`version_mismatch` is decided before the payload is normalized.** A test that seeds a rich
   payload and then expects `not_found` from a mismatched version will get `version_mismatch`
   instead, and a test that assumes the reverse will pass for the wrong reason.
5. **`resolve_assignment` and `resolve_lock` search `lambda: ()`.** Any assertion of the form
   "every ref resolves" fails on a `locks` ref, or — worse — passes because no fixture produced
   one. Assert per group (Decision 7).
6. **A ref minted from a bare `uuid4()` resolves by construction.** 4.4a's review caught this
   exact shape. Seed a superseding `scenario_version` row instead (Decision 8).
7. **The two existing lost-CAS tests look like AC2 and are not.** They inject a business outcome,
   which is EAD-10's *other* fork arm. AC2 needs an infrastructure fault (Decision 4).
8. **A rollback-required error must ESCAPE the route.** Catching it and returning a response
   causes `get_site_context` to commit the partial bundle — the structural unsafety Story 4.3
   found and fixed, recorded in `promote_baseline.py`'s module docstring. A test that asserts the
   rollback while the route catches the error is asserting the bug.
9. **`promote_baseline` asserts `candidate is not None` as a precondition.** A fault-injection
   fixture that nulls the candidate raises `AssertionError`, not the DB error under test.
10. **The membership check inside `revalidate_binding` is the INITIATING actor's.** The deciding
    actor is enforced at the session layer and must not be rechecked there — pinned as of `32d9320`.
11. **`persisted_event.sequence` is per-stream** and cannot order a merged conversation + run
    timeline; same-timestamp rows are the normal case because each TX writes three rows against one
    clock. If a test asserts ordering, the tie-break is load-bearing.
12. **`PostgresAuditWriter` stores `worker_facts` and `evidence_refs` through
    `TypeAdapter.dump_python(mode="json")`.** A reader comparing raw JSONB to a dataclass will
    mismatch on shape, not on content; go through `PostgresAuditReader`.
13. **The CI baseline numbers in `.github/workflows/ci.yml` are stale relative to Story 4.4's
    measurements.** They are floors and ceilings, so they still hold. Do not "correct" them here —
    that is not this story's change, and lowering a ceiling or raising a floor mid-story is how a
    green build stops meaning anything.
14. **A guard that cannot go red.** The epic's most-repeated defect, named in the Epic 3 retro as
    this project's recurring failure mode and found again at 4.1, 4.2 and 4.4 review. Every new
    assertion in this story is demonstrated-red once and the RED→GREEN line recorded.

### Honest gaps this story ships with — state them in Completion Notes

(a) **CloudWatch degradation is `NOT COVERED`,** owner `diagnosis:cloudwatch_owned_by_epic_6`
    (Decision 9). AC4's clause has no local subject; the telemetry half is proven for real.

(b) **An infrastructure fault inside TX2 leaves no durable server-side record of the attempt**
    (Decision 5). AC2 does not ask for one; the client sees a 5xx and a still-`pending` binding.
    The ledger entry is re-pointed, not closed.

(c) **`baseline-assignments` and `locks` evidence refs are structurally `not_found`**
    (Decision 7), because the two resolvers search an empty tuple. Not a data accident.

(d) **The `baseline` assignment supply is still guarded rather than wired** (spine EAD-8), so no
    proof here asserts anything about post-promotion comparison contents.

(e) **Pre-write denial rows remain unbounded and un-suppressed** (`deferred-work.md:572`, `:625`).
    Proven stable, deliberately not fixed.

(f) **The response-before-commit window** (`deferred-work.md:574`) is untouched and pre-existing.

### Testing requirements

- Backend tests live in `backend/tests/`, named `test_*.py`, never co-located. The new matrix
  module is PostgreSQL-backed: `pytestmark = pytest.mark.postgres` at module scope, and the file
  name ends `_postgres.py` to match the established convention.
- The `postgres` marker is **not** excluded by default — `addopts = "-m \"not live\""` excludes only
  `live` — so these tests run in the default suite too, skipping cleanly when the service is
  absent. That clean skip is exactly why `_junit_outcome` exists.
- Run both tracks: `uv run --frozen pytest` and `uv run --frozen pytest -m postgres`, from
  `backend/`.
- The generator's own tests are plain unmarked pytest, exercising `write_*`/`measure_*` directly
  rather than through a subprocess, with `tmp_path` and `allow_dirty=True`.
- No new golden cases (Decision 11). No frontend or Playwright changes.

### Project structure notes

Every new path matches the Epic 4 Structural Seed and the conventions already in force:
`backend/evals/*_report.py` for a proof generator (Stories 3.10, 3.11), `backend/tests/test_*_postgres.py`
for a PostgreSQL-backed suite, `evidence/story-4.5/` for the artifact, and
`backend/scripts/gate_a_checks.py` as the single registry. No module is renamed, and AR26's
structural convergence is unaffected.

### Open questions — neither blocks this story

1. **Should AC4's CloudWatch clause be struck from `epics.md`, as AC3's object-storage premise
   was on 2026-09-01?** Decision 9 handles it at story level following Story 3.9's precedent, which
   is sufficient to ship. Striking it is a course correction. **Deadline: the Epic 4
   retrospective** — carry it in as input.
2. **Should a decision pin the scenario version, not only the resource version?** Carried
   unanswered since Story 4.1 and still open at 4.4. It does not change any assertion here, because
   AC3 resolves against the ref's own pinned `scenario_version_id` either way. **Deadline: whichever
   story first needs a decision to survive a fixture reload.**

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1286-1315` — Story 4.5 ACs and the evidence scope note]
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md` — Verification Obligations; EAD-3, EAD-6, EAD-7, EAD-8, EAD-10, EAD-12; Story → Architecture Map]
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ADR-4-consequential-workflow.md` — D7, D8, D9, Consequences]
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-12, AD-16, AD-22 amendment]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-01.md:71,143-177` — AC3 rewrite; "AC1, AC2, AC4 untouched"]
- [Source: `docs/EVIDENCE-CONVENTION.md` — the rule; the monotone principle; a verdict key Gate A can read; the eight-step checklist]
- [Source: `docs/DOMAIN-MODEL.md` §2, §3 — assignments carry no family]
- [Source: `_bmad-output/implementation-artifacts/4-4a-supply-audit-evidence-references.md` — Decisions 1, 2, 3, 4, 5; Review Findings; Open questions]
- [Source: `_bmad-output/implementation-artifacts/3-9-continue-deterministic-work-during-model-outage.md` — Decision E]
- [Source: `_bmad-output/implementation-artifacts/3-11-prove-recovery-and-idempotency.md` — generator shape, `_junit_outcome`, Gate A registration]
- [Source: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1 — "a guard that passes without proving a meaningful failure"]
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` — `:506`, `:564`, `:572`, `:574`, `:623`, `:625`, `:627`]
- [Source: `backend/application/use_cases/promote_baseline.py` — `SCOPE_CONTROLS["audit"]`, module docstring on rollback-by-escaping-exception]
- [Source: `backend/application/use_cases/decide_approval.py` — `revalidate_binding`, `RevalidationV1`, the TX3 audit write]
- [Source: `backend/api/routers/approvals.py` — `decide_approval_route` denial arm and its evidence-refs comment]
- [Source: `backend/api/deps.py` — `site_context`, `PostCommitActions`, the four `get_*` dependencies Decision 4 overrides]
- [Source: `backend/adapters/postgres/scenario_projection.py` — `_resolve_items`, `_projection_row`, `resolve_*`]
- [Source: `backend/application/contracts/evidence_ref.py` — `ResolutionOutcomeV1`, `EvidenceRefV1`]
- [Source: `backend/application/contracts/audit_envelope.py` — `AuditOutcomeV1`'s six members]
- [Source: `backend/application/contracts/decision_provenance.py` — `SCOPE_CONTROLS`]
- [Source: `backend/scripts/gate_a_checks.py` — `NFR29_GATES`, `GateACheck.__post_init__`, `validate_registry`]
- [Source: `backend/tests/test_gate_a_readiness.py` — the exact evidence-path set; `test_registry_covers_more_than_the_four_evidence_files`]
- [Source: `backend/evals/recovery_idempotency_report.py` — `PROOF_NODES`, `FAILURE_MODE_GATES`, `_junit_outcome`, `_run_proof_node`]
- [Source: `backend/scripts/evidence_binding.py` — `resolve_bindings`, `DERIVED_BINDING_KEYS`, `DirtyTreeError`]
- [Source: `.github/workflows/ci.yml` — floors and ceilings; the `-m "not live"` guard]

---

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

Follow Tasks 1–15 in order with demonstrated RED→GREEN proof for every new assertion, exactly one production-line change, a code commit before measurement, and a separately generated evidence commit.

### Debug Log References

- 2026-09-01 Task 1 baseline (`backend/`): `uv run --frozen pytest -q` → 1455 passed, 1 skipped, 7 deselected, 0 failed in 143.65s.
- 2026-09-01 Task 1 PostgreSQL baseline (`backend/`): `uv run --frozen pytest -m postgres -q` → 131 passed, 1332 deselected, 0 failed in 40.46s.
- 2026-09-01 Task 1 evidence baseline (`backend/`): `uv run --frozen pytest tests/test_evidence_convention.py -q` → 74 passed, 0 failed in 2.93s.
- Frontend and Playwright: not run — zero-line frontend diff.
- 2026-09-01 RED→GREEN (report binding): report tests first failed because the declared PostgreSQL proof module did not exist; after adding it, the resolver bound the dataset. A second RED exposed duplicate dataset paths; deduplicating by test file produced 5 passed.
- 2026-09-01 RED→GREEN (proof matrix): the first matrix run failed on the real membership schema (`revoked_at`, not a derived status), the closed evidence-group vocabulary, and explicit resolver arguments. Correcting the fixtures produced 14 passed; expanded matrix/report/exporter run produced 21 passed.
- 2026-09-01 RED→GREEN (audit integrity): repeated-denial proof first failed on the 40-character idempotency-key boundary and then on the serialized `WorkerFactsV1` shape; bounded keys and exact structural keys produced 1 passed.
- 2026-09-01 RED→GREEN (Gate A): with the new invariant and no checks, `test_every_invariant_has_at_least_one_contributing_check` failed on `approval_and_audit_invariants`; restored evidence check made it pass. With evidence only, `test_registry_covers_more_than_the_four_evidence_files` failed; restoring the separate machinery check produced 2 passed.
- 2026-09-01 pre-evidence regression: 1471 passed, 2 skipped, 7 deselected; the three observed failures were all story-owned and resolved except the intentional registered-evidence-file absence, which remains red until Task 13 generates the artifact in convention order.
- 2026-09-01 Task 13: clean code commit `d3f73915f05d009f1e35a538b27147959869ff81`; generator completed every named node with `passed: true`; `test_evidence_convention.py` → 80 passed; evidence-only commit `c8d7cc7`.
- 2026-09-01 Task 15 final: default → 1482 passed, 1 skipped, 7 deselected; PostgreSQL → 147 passed, 1343 deselected; evidence convention → 80 passed. Deltas from Task 1: +27 default passes, +16 PostgreSQL passes, +6 evidence-convention passes, zero new failures.

### Completion Notes List

- Implemented Epic 4's PostgreSQL proof matrix, genuine DBAPI fault injection with retry-once, direct evidence-locator resolution, telemetry independence, audit uniqueness/identity/repeated-denial guards, skip-safe report generator, and two-part Gate A registration.
- Added exactly one production line: `audit_evidence_refs:mirrors_targeted_candidate`. Frontend diff remains zero lines.
- NOT COVERED: `diagnosis:cloudwatch_owned_by_epic_6`; no local CloudWatch subject or double was introduced. Epic 4 retrospective input records the AC4 wording defect.
- Honest gaps retained: TX2 infrastructure failures leave no durable server-side attempt row; locks/baseline-assignments remain structurally `not_found`; baseline assignment supply remains guarded; repeated denial rows and the response-before-commit window remain unchanged.

### File List

- Read: `backend/application/use_cases/decide_approval.py`, `promote_baseline.py`, `request_approval.py`; `backend/api/routers/approvals.py`, `backend/api/deps.py`; `backend/adapters/postgres/approval.py`, `site_baseline.py`, `audit.py`, `scenario_projection.py`; `backend/tests/test_approval_governance_postgres.py`; `backend/evals/recovery_idempotency_report.py`; `backend/tests/test_recovery_idempotency_report.py`.
- Added: `backend/tests/test_approval_audit_invariants_postgres.py`, `backend/tests/test_approval_audit_report.py`, `backend/evals/approval_audit_report.py`.
- Generated: `evidence/story-4.5/approval-audit-invariants.json` (through `resolve_bindings()`, bound to code commit `d3f7391`).
- Modified: `backend/application/contracts/decision_provenance.py`, `backend/tests/test_decision_provenance.py`, `backend/tests/test_approval_governance_postgres.py`, `backend/scripts/gate_a_checks.py`, `backend/tests/test_gate_a_readiness.py`, `_bmad-output/implementation-artifacts/deferred-work.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`, this story file.

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-01 | Story created. Thirteen decisions recorded; proof matrix bound to the Epic 4 spine's seven verification obligations. |
| 2026-09-01 | Implemented and verified approval/audit proof matrix; generated separately bound evidence; status moved to review. |
| 2026-09-01 | Code review: nine findings applied; proof matrix bound to 28 named gates; evidence rebound to `f9ea3e2`. Status moved to done. |
