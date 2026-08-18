---
baseline_commit: 2b48b7287427befd38f4e34992fc17ce972fbf28
---

# Story 3.1: Create and Revise a Reversible Repair Draft

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want operational intent resolved into a reviewable draft,
so that I can correct constraints and objectives before any computation or baseline change.

**Unblocks:** Story 3.2 (`RunSnapshotV1` freezes a `ProposalV1`) and Story 3.6 (Run optimization
validates "proposal and baseline versions"). Both consume this story's contract; neither is
required for this story to be acceptable.

**Depends on, and consumes:** Story 2.5's application-owned grant registry and `AgentDepsV1`;
Story 2.6's generic `CapabilityModuleV1` renderer and `CapabilityError` base; Story 2.7's request
path (`POST /conversations/{id}/agent-runs/{run_id}/execute`), `tool_result_sink` trusted-result
capture, and content-addressed `result_id` convention; Story 2.9's named `ToolOutput` variants,
application-resolved entity candidates (`application/clarification/resolve.py`), and
`ActivityItemV1` variant plumbing; Story 1.4/1.5's `ScenarioProjectionV1` exact-target resolvers.

**Scope summary:** One migration (three tables). One new router. One new capability. One new
structured-output variant. One new activity discriminant. **No new dependency.** No evidence file.

**This story is the first in the repository to:**

1. create a **scheduling-aggregate** table (`proposal`, `proposal_version`) — AD-22 gives
   proposals to `Scheduling`, and no scheduling table exists (verified: `adapters/postgres/schema.py`
   defines exactly `organization`, `site`, `scenario`, `scenario_version`, `fixture_lineage`,
   `evidence_reference`, `app_user`, `membership`, `session_index`, `conversation`, `message`,
   `agent_run`, `persisted_event`, `login_handshake`);
2. implement **AD-8/AR8 HTTP command idempotency**. Verified by exhaustive grep: the strings
   `Idempotency-Key` and `idempotency_key` appear **nowhere** in `backend/`. The only hits for
   "idempotency" are `CapabilityManifestV1.idempotency_semantics` declaration strings;
3. mount a **mutating route outside `/api/v1/conversations`**;
4. ship a `draft`-risk-class capability. `RiskClassV1` already reserves `draft`
   (`application/contracts/capability_manifest.py:20-22`) and `RiskClassV1` is re-exported into the
   golden-case vocabulary (`evals/cases.py:14-25`), so no vocabulary changes.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. Every rule below is recorded somewhere
citable; none of it may be re-derived from adapter code (retro §3.2, the single most expensive
pattern of Epics 1–2).

| Fact | Where it is written |
|---|---|
| Demand family → unit mapping; assignments carry no family; route a question by the **unit the answer is measured in** | `docs/DOMAIN-MODEL.md` §1–§3 |
| A draft must not compute a metric — that is `scheduling_compute`'s, and an ungoverned second calculator is what Story 2.5's trap list forbids | `docs/DOMAIN-MODEL.md` §5; `sprint-status.yaml` (2.5 traps) |
| Proposals/solver inputs/schedule versions are immutable; the baseline is a versioned pointer; stale inputs **fail closed without silent rebasing** | AD-9 (`ARCHITECTURE-SPINE.md:138-142`) |
| `ProposalV1`'s required shape: proposal/version IDs, scenario/baseline versions, resolved entities, constraints/objectives, preserved locks, consequence summary and canonical hash | AD-20 *Normative contract minimums* (`ARCHITECTURE-SPINE.md:320`) |
| The **draft activity payload is a reference, not the proposal**: "draft = proposal ref/summary" | AD-20 `ActivityItemV1` row (`ARCHITECTURE-SPINE.md:331`) |
| Risk classes are exactly `inspect`/`draft`/`compute`/`consequential`/`prohibited`; `draft` = "Create reversible constraints, goals, and candidate parameters", human control = "Planner reviews or revises" | AD-5 (`ARCHITECTURE-SPINE.md:76`); PRD §5.1 autonomy tiers |
| Contract hashes are SHA-256 over RFC 8785 canonical JSON, carrying algorithm + schema version | AD-20 (`ARCHITECTURE-SPINE.md:208`); *Consistency Conventions* |
| Schedule intervals are integer-minute half-open `[start_minute, end_minute)` offsets from a UTC `horizon_start`; **only the solver adapter converts to float hours** | AD-20 (`ARCHITECTURE-SPINE.md:208, 255`) |
| Mutating HTTP commands require an idempotency key scoped to actor, site, operation, canonical body hash, plus expected resource version; database uniqueness protects it; a replay returns the original semantic result and a conflicting body fails | AD-8 (`ARCHITECTURE-SPINE.md:132-136`); AR8 (`epics.md:154`) |
| Only an application orchestrator may cross aggregate owners; adapters and repositories may not widen a bundle | AD-22 (`ARCHITECTURE-SPINE.md:216-220`) |
| Draft card contents and the literal label "Draft — no baseline change"; revise/reject separate from Send and approval | UX-DR9 (`epics.md:194`); `EXPERIENCE.md:87`; `DESIGN.md:128` |
| Manual assistive-technology verification is out of scope; automated coverage is the recorded bar | `EXPERIENCE.md:196` |
| Never hand-type an evidence file; commit code → measure → generate → commit evidence separately | `docs/EVIDENCE-CONVENTION.md` |

**A rule this story needed and found unwritten is recorded in Gap 1 rather than assumed.**

---

## Seven decisions were made at story creation — do not re-litigate them

### Decision 1 — The capability **validates and resolves**; the application **persists**. A handler cannot write, by construction

`AgentDepsV1` (`application/capabilities/deps.py`) carries a `ScenarioProjectionReader`, a clock, a
budget and a `tool_result_sink` — and **no writer, no repository, no unit of work**. On the request
path `connection` is set to `None` (`api/routers/conversations.py:214`) and reads go through
`ShortTransactionScenarioProjectionReader`, which opens its own short site transaction per call.
`test_handler_module_has_no_adapter_or_framework_import`
(`tests/test_capability_conformance.py:142-144`) forbids a handler module from importing `adapters`
at all.

So the draft capability returns a **trusted `SchedulingDraftResultV1`**, captured by
`tool_result_sink` exactly as `scheduling_compute` results are, and the **application orchestrator**
writes the proposal at finalisation, inside `finish_agent_run`'s single transaction.

That composes a new atomic bundle. AD-22's fixed list (accept-turn, enqueue-compute,
complete-compute, request-approval, promote-baseline) does not include one for drafting, and AD-22
permits only an application orchestrator to cross owners. Record it explicitly in the story's
`SCOPE_CONTROLS`:

> `create-draft = proposal + proposal version + activity event + agent-run terminal transition`,
> composed by the conversation orchestrator. Repositories and adapters do not widen it.

**Rejected alternative:** giving the handler a write port. It would put a scheduling-aggregate
write behind a model-proposed tool call inside a request whose transaction boundary the handler does
not own, and it would require the capability package to import an adapter — the one import the
conformance fence names.

### Decision 2 — The model **cites** a draft; it never authors one. Fourth named `ToolOutput`

The turn's structured output gains a fourth variant beside `final_result` / `clarification` /
`refusal` (`agent/runtime.py:64-69, 129-138`):

```python
DRAFT_OUTPUT_TOOL = "draft"
ToolOutput(DraftProposalV1, name=DRAFT_OUTPUT_TOOL)
```

`DraftProposalV1` is **UNTRUSTED and carries exactly one field**: `draft_id`. No constraint values,
no entity labels, no consequence summary, no version strings. Everything the Draft card renders
comes from the trusted `SchedulingDraftResultV1` the capability produced and the persisted proposal
row — never from the model's output.

This is Story 2.7's `produce` branch (AD-11's "produce **or** verify" disjunction) applied to
drafts, and it is Story 2.9 Decision 5's shape applied to entities: the model proposes
`(group, record_id)` inside the capability call, the application resolves each on the trusted path
and supplies the label.

**Rejected alternative — let the model author the proposal and validate it in a gate.** It
recreates precisely the failure mode the 2026-08-13 correct-course removed
(`sprint-change-proposal-2026-08-13.md` Findings 1–3): the model would author labels and a
consequence summary the application must then either trust or discard, and any disagreement
manufactures a failure over a proposal that was already valid. There is no fourth failure type to
add and no reason to add one.

`ANSWER_OUTPUT_TOOL = "final_result"` keeps its exact name (Story 2.9 Decision 1 measured why:
`evals/doubles.py:62-75` selects the scripted output tool **by name** from `info.output_tools`, and
a rename breaks every frozen case).

### Decision 3 — The constraint vocabulary is the five the CP-SAT builder **already applies**, re-declared in `application/contracts`. Nothing legacy is imported

Measured in the repository, not chosen: `engine/cpsat/builder.py:346-404` implements exactly four
soft-penalty terms plus one demand transform, keyed on `OverrideCall.tool`:

| Kind | Arg shape (from `builder.py` / `services/constraint_service.py:211-455`) | How CP-SAT applies it |
|---|---|---|
| `set_min_workers_per_task` | `task_id: str`, `n: int > 0` | bounded shortfall slack per demanded hour, `MIN_WORKERS_PENALTY` |
| `scale_demand` | `task_id: str`, `factor: float > 0` | per-task factor in `_aggregate_demand` (`builder.py:112-117`) |
| `lock_worker_shift` | `member_id: str`, `day: int` | bounded `absent` bool, `LOCK_SHIFT_PENALTY` |
| `exclude_worker_from_task` | `member_id: str`, `task_id: str` | direct penalty on task assignment vars |
| `set_max_hours` | `member_id: str`, `max_hours: float` | bounded overflow var under the hard cap |

Choosing any other vocabulary would produce a `ProposalV1` Story 3.2 cannot execute.

**Two things follow, and both are load-bearing:**

- **The identity bridge is free, and this is measured.** `TaskV1.record_id == str(task_id)` and
  `WorkerV1.record_id == str(contact_id)` (`adapters/postgres/scenario_projection.py:140, 230`), and
  the builder matches on `member.contact_id` and `task_id`. So the builder's `task_id`/`member_id`
  args are **byte-identical** to the `work-areas-and-tasks` and `workers` evidence-group
  `record_id`s. There is nothing to translate and no mapping table to build.
- **`day: int` does not enter the governed contract.** AD-20 fixes schedule time as integer-minute
  half-open offsets and says only the solver adapter converts. Express the lock window as
  `start_minute` / `end_minute`; Story 3.2 converts at the adapter boundary.

**Do NOT import `services/constraint_service.py` or `domain/overrides.py`.** `backend/services/**`
and `backend/domain/**` have held mandated zero-line diffs through every Epic 2 story; the legacy
validator resolves against the legacy `SchedulingProblem`, not `ScenarioProjectionV1`; and its
`_resolve_task` / `_resolve_member` perform **fuzzy human-token matching**, which is exactly the
model-authored-identity inversion AD-2 forbids and Story 2.9 Decision 5 rejected. Read them as
reference for arg semantics and error copy; import nothing.

`DraftConstraintKindV1` is a **closed vocabulary persisted inside a `persisted_event` payload and a
`proposal_version` row**. Say so in its docstring, exactly as `MetricV1` does
(`application/contracts/grounding.py:18-40`): adding, renaming or removing a member is a contract
change, not a refactor (`deferred-work.md:198` records the cost of learning that late).

### Decision 4 — Revise and reject are explicit **HTTP commands** on a new `/api/v1/proposals` router, and they carry the repository's first idempotency key

AC3 names "expected version and idempotency key" and cites AR8. This does not contradict Story
2.7's Decision 1, which declined a key because **its own AC named none** and FR-7 is absent from
AD-8's binding list; here the AC names one explicitly.

**Mount point — `/api/v1/proposals`, a new router.** Both alternatives are closed:

- **Not `/api/v1/scenarios/...`.** `test_gate_a_mutation_audit.py:24-34` asserts every
  `/api/v1/scenarios` path exposes only `get`, and AR28 forbids weakening a Gate A invariant. This
  is the constraint that decides the mount.
- **Not `/api/v1/conversations/...`.** Story 2.7 mounted there because its aggregate *was* the
  conversation. AD-22 gives `proposal` to `Scheduling`.

**Both commands are `POST`.** `api/main.py:251-256` sets
`allow_methods=["GET", "POST"]`, so a `PATCH`/`PUT`/`DELETE` would pass same-origin and fail CORS
preflight cross-origin — a defect that only appears in a deployed topology. CSRF and session are
free: `enforce_versioned_session_and_csrf` (`api/main.py:181-238`) covers every `/api/v1` path, and
`frontend/src/api/client.ts:18-31` already attaches `X-CSRF-Token` to unsafe methods through
middleware.

**Idempotency is scoped to exactly the two operations this story ships.** Build a
`command_idempotency` table unique on `(site_id, actor_id, operation, body_hash)` storing the
original response body, and compare `expected_resource_version` **inside** the command transaction.
Do **not** build generic middleware for FR12/16/18/19 — Stories 3.6, 3.4 and 4.1–4.3 each own their
own bundle and their own effect keys, and a premature generic layer would fix a shape none of them
has specified yet.

### Decision 5 — Rejection is a **terminal state**, revision is a **new immutable version**, and immutability is enforced by grant

AD-9. `proposal_version` rows are append-only; `proposal.state` moves `active → rejected` once.

Follow the grant pattern the schema already establishes rather than inventing one. Migration
`a4f92d7c8e31:94-100` does `GRANT SELECT, INSERT` then `REVOKE UPDATE, DELETE` on every table, then
grants exactly one column (`conversation.resource_version`); `c7d6e5f4a3b2:17` grants exactly
`agent_run(status)`. So:

- `proposal_version`: `SELECT, INSERT` only, `UPDATE`/`DELETE` revoked. **Immutable by grant, not
  by convention** — a later story cannot silently mutate a version row.
- `proposal`: the same, plus `GRANT UPDATE (state, current_version_id, resource_version)`. Three
  columns, named, nothing else.
- `command_idempotency`: `SELECT, INSERT` only.

Every table carries `site_id`, `ENABLE`/`FORCE ROW LEVEL SECURITY`, the
`site_id = NULLIF(current_setting('app.site_id', true), '')::uuid` policy, an `ix_<table>_site_id`
index, and composite `(id, site_id)` uniqueness — copy `a4f92d7c8e31` line for line (AD-23).

### Decision 6 — The draft activity is a **reference**, and the Draft card reads current proposal state

AD-20 fixes this: "draft = proposal ref/summary" (`ARCHITECTURE-SPINE.md:331`). Inlining the whole
proposal into the activity payload is the obvious implementation and it is wrong for a mechanical
reason: `persisted_event` is an immutable audit record, so a revised proposal would leave the
timeline rendering the superseded draft forever.

`DraftActivityV1` therefore carries the common activity fields plus `proposal_id`,
`proposal_version_id`, and a short **application-composed** `consequence_summary`. The card fetches
current state from `GET /api/v1/proposals/{proposal_id}`, which is also where staleness (AC4) is
computed. This is AD-14 as written: "Cached data is never authority or a substitute for resource
versions."

**This decision is what removes a structural blocker.** `persisted_event.agent_run_id` is
`nullable=False` with an FK (`a4f92d7c8e31:69, 74`) and `ck_persisted_event_stream_is_conversation`
pins the stream to the conversation. A planner-initiated revise command has **no agent run**, so it
could not emit an event without widening a column an Epic 4 audit story owns. Under this decision it
does not need to: revise/reject mutate the proposal and the card re-reads.

**Recorded reduction:** a revision or rejection produces no persisted event, so a second browser tab
does not learn of it until it refetches. TanStack Query owns that cache (AD-14). State it in
`SCOPE_CONTROLS` "NOT COVERED" form; do not invent an event type to paper over it.

### Decision 7 — Staleness is driven by the **scenario** version, because no baseline schedule version exists anywhere

See Gap 1 for the measurements. `expected_baseline_schedule_version` is **declared** on `ProposalV1`
(AD-20 names it) and populated from `ScenarioOverviewV1` — which returns `None` today. Do not invent
a value, and do not repurpose `scenario_version_id` for it (different aggregates; the same mistake
Story 2.7 declined for `producing_run_version`).

AC4's staleness is drivable through the one version that can actually differ. Every projection read
re-resolves "latest version" for the scenario (`deferred-work.md:59` records this as an accepted
limitation), so importing a second `scenario_version` for the same scenario makes a pinned proposal
stale **today**. That is the test path: seed a second version, assert the proposal renders visibly
stale, assert no field was rebased, assert no computation is offered.

---

## Acceptance Criteria

Verbatim from `epics.md:855-875`. The 2026-08-09 Epics 2–5 scope audit lists Story 3.1 under
"KEEP as-is" (`sprint-change-proposal-2026-08-09-epics-2-5.md:138`), so these four are canonical and
unmodified.

**AC1 —**
**Given** a grounded request to preserve locks, avoid a named assignment, and reduce overtime
**When** the draft capability resolves the request
**Then** `ProposalV1` records proposal/version IDs, scenario and expected baseline versions,
resolved entities, constraints/objectives, preserved locks, consequence summary, and canonical hash
**And** invalid entities, tasks, ranges, combinations, or stale expected versions fail before solver
execution. (FR9, AR9, AR20)

**AC2 —**
**Given** a valid draft
**When** the planner reviews it in Chat
**Then** the Draft card shows resolved entities, constraints/objectives, locks, expected versions,
consequences, and "Draft — no baseline change"
**And** revise and reject are separate active controls from Send and approval; this story introduces
no Run optimization control or required placeholder. (FR10, UX-DR9, UX-DR35)

**AC3 —**
**Given** the planner revises or rejects a draft
**When** the command is accepted with expected version and idempotency key
**Then** a new immutable proposal version or terminal rejection is persisted exactly once
**And** the operational baseline pointer and schedule version remain unchanged. (FR10, AR8, AR9)

**AC4 —**
**Given** the current scenario or baseline version no longer matches the draft
**When** review or execution is attempted
**Then** the draft is visibly stale, computation is blocked, and the planner must refresh or create a
new version
**And** no silent rebase occurs. (AR9, UX-DR25)

---

## Two honest gaps, raised rather than papered over

### Gap 1 — There is no baseline schedule version, no lock supply, and no baseline assignment supply

AC1 requires "expected baseline versions" and "preserved locks". Measured at creation:

| Claim | Measurement |
|---|---|
| `baseline_schedule_version` is always `None` | `adapters/postgres/scenario_projection.py:556` returns the literal `None`; `adapters/postgres/scenario_catalogue.py:116-118` selects `literal(None, type_=String)`. There is no such column on `scenario_version` (`schema.py:93-146`) and no `schedule_version` table anywhere. |
| There is **no lock supply at all** | `ScenarioProjectionReader.get_locks` calls `_apply_query((), query, LOCK_SORTS, LOCK_FILTERS)` — a hardcoded empty tuple (`scenario_projection.py:651-668`). Not "the fixture has no locks": there is no code path that produces one. |
| There is no baseline assignment supply | `get_baseline_assignments` returns `()` (`docs/DOMAIN-MODEL.md` §2 records this; the only populated source is the eval double `evals/fixture_projection.py`). |
| Both committed fixtures agree | `data/contract/sample_tiny_input.projection-v1.json` and `..._more_tm...json`: `baseline_schedule_version: null`, `lock_count: 0`, `baseline_assignment_count: 0`. Real data exists for tasks (6), workers (10 / 22), demand (1547) and constraints (14). |

**A correction, recorded rather than left to mislead.** Story 2.7's creation note states
`baseline_schedule_version` "IS populated from ScenarioOverviewV1, which already carries it"
(`sprint-status.yaml`). The overview carries the **field**; its value is `None` at both producers.
Every `EvidenceRefV1` the repository has ever persisted therefore has
`baseline_schedule_version = None`. Do not build on the false reading.

**Required posture:**

- Declare `expected_baseline_schedule_version` and populate it from `ScenarioOverviewV1`. `None`
  today is the truthful value.
- Keep `preserved_locks` a real field over the real supply. **Do not write a test that asserts
  "locks were preserved" against a supply of zero** — that is retro §3.1's dominant failure mode
  (19 findings in Epic 2), a guard that cannot go red. Prove the *mechanism* against a seeded reader
  that **does** return locks, following `evals/fixture_projection.py`, which already supplies
  assignments the real reader does not.
- **Do not edit a committed contract fixture to add locks.** FR22/AR4 make fixtures immutable and
  application-provided, Story 1.1 owns import, and `data/contract/**` digests are Gate A bound
  (commits `7355492`, `1d32035` exist because those bytes are load-bearing).
- **Do not build a `schedule_version` table or a baseline pointer.** Story 3.2 owns
  `ScheduleVersionV1`; Story 4.3 owns the pointer move.
- Record each reduction in `SCOPE_CONTROLS` "NOT COVERED" form — Story 2.5's convention, asserted by
  `test_installed_module_records_its_scope_controls`.

### Gap 2 — "fail before solver execution" has no solver to be before

AC1's failure clause says invalid input must "fail before solver execution". Verified: no
`RunSnapshotV1`, `ScheduleVersionV1` or `SchedulerEngine` invocation exists on any governed path —
`backend/engine/` is reachable only from the legacy SQLite `services/run_service.py`. The clause is
therefore **satisfied vacuously today** and becomes meaningful at Story 3.2.

**Required posture:** make the validation a real, tested refusal *at draft time* rather than
claiming the clause is proven. Two distinct behaviours, both asserted:

- an unresolvable entity or an out-of-vocabulary kind → **retryable** `invalid_query`, so the model
  can correct itself inside the run (the `MetricDimensionMismatchError` precedent,
  `scheduling_compute.py:120-133`);
- an out-of-range argument (`n <= 0`, `factor <= 0`, `max_hours` above the employment-type hard cap,
  `end_minute <= start_minute`) → the same retryable path, with a message that names the bound.

Then state in `SCOPE_CONTROLS` that no solver exists yet to be "before", and that Story 3.2 inherits
the clause. Same posture as Story 2.6 for `AuditEnvelopeV1` and Story 2.7 for
`producing_run_version`.

---

## Tasks / Subtasks

Three phases with one reporting checkpoint, the 2.7/2.9 pattern and for the same reason: the phase
boundary sits where the only clean split *would* be, so that decision can be revisited with numbers
instead of guessed before any code exists. **Phase A satisfies AC1 and AC3's server half with a
zero-line `frontend/` diff.**

**Retro action A2 is in force from this story.** Every new guard, conformance assertion and
architecture test must be **observed failing with its structural assertion removed**, and the
Completion Notes must record the observed red. A guard nobody has seen fail is a guard nobody has
tested.

### Task 1 — Re-home the RFC 8785 canonicalizer (AC: 1, 3)

- [x] Move `canonicalize_json` from `backend/adapters/postgres/canonical_json.py` to
      `backend/application/contracts/canonical.py`, unchanged. It is already pure (stdlib +
      `decimal` only) and complete (surrogate rejection, JCS number form, UTF-16 key ordering).
- [x] Add `contract_digest(value) -> tuple[str, str, str]` returning
      `(algorithm, schema_version, hex_digest)` = `("sha256", "rfc8785-v1", ...)`. Those two literals
      already exist as CHECK constraints on `scenario_version`
      (`schema.py:134-141`); reuse the strings, do not coin new ones.
- [x] Update the only two importers — measured, not estimated:
      `adapters/postgres/fixture_history.py:14` and `backend/tests/test_fixture_history_import.py:12`.
- [x] **Why this is required rather than tidy:** the draft capability computes `ProposalV1`'s
      canonical hash, and `test_handler_module_has_no_adapter_or_framework_import` forbids a handler
      module from importing `adapters`. A third hand-rolled canonicalizer is what AD-20 exists to
      prevent.
- [x] `scheduling_compute.py` keeps a **zero-line diff**. Its `derive_result_id` carries a
      deliberately restricted float-free JCS variant and every `result_id` in the four frozen
      `scheduling_compute` golden cases is pinned to it. Add one test asserting the two agree on the
      float-free shapes `derive_result_id` accepts, so a future story can collapse them safely, and
      note the deliberate coexistence in `canonical.py`'s docstring.

### Task 2 — `ProposalV1` and the draft contracts (AC: 1, 2, 3, 4)

- [x] `application/contracts/proposal.py`, framework-free, frozen dataclasses, every one carrying
      `schema_version` (AD-20 *Normative contract minimums*).
- [x] `DraftConstraintKindV1` — closed `Literal` with the five names from Decision 3. Docstring
      states it is a closed vocabulary persisted inside `persisted_event.payload` and
      `proposal_version`, so a change is a contract change (mirror
      `grounding.py:18-40`'s "NOTE on what is deliberately ABSENT" style).
- [x] `DraftConstraintProposalV1` — **UNTRUSTED** model input: `kind`, `group`, `record_id`(s), and
      the kind's typed arguments. No label, no prose, no version.
- [x] `ResolvedEntityV1` — **TRUSTED**: `group`, `record_id`, `label`, `scenario_version_id`. Reuse
      `application/clarification/resolve.py`'s `_planner_label` shape so Chat and Scenario Data agree
      on how a record is named; extract it to a shared helper rather than copying it.
- [x] `DraftConstraintV1` — **TRUSTED**: kind, resolved entities, validated arguments, and an
      application-composed `description` (the `parsed_constraint` idea from
      `services/constraint_service.py:250, 296, ...`, re-authored not imported).
- [x] `ProposalV1` — AD-20's required shape exactly: `proposal_id`, `proposal_version_id`,
      `scenario_id`, `scenario_version_id`, `expected_baseline_schedule_version`,
      `resolved_entities`, `constraints`, `preserved_locks`, `consequence_summary`,
      `canonical_hash` (+ algorithm and schema version), `state`, `resource_version`.
- [x] `ProposalStateV1 = Literal["active", "rejected"]`. Two states, not five: nothing in this story
      supersedes or expires a proposal, and a value with no producer is the declared-but-unsupplied
      shape retro §3.3 names.
- [x] **Staleness is derived at read time and never written back.** It is a comparison between the
      proposal's pinned `scenario_version_id` and the currently-resolved one, so persisting it would
      immediately be able to disagree with the truth. This is Story 2.8 Decision 6's shape
      ("'Evidence unavailable' is derived at render time and never written back") and it is why
      `ProposalStateV1` has no `stale` member.
- [x] `DraftProposalV1` — the **UNTRUSTED** model output variant. Exactly `draft_id` +
      `schema_version` (Decision 2).
- [x] Contract fixture + field-order test in the shape of
      `tests/test_evidence_ref.py::test_evidence_ref_v1_has_the_normative_frozen_transport_free_shape`
      (line 63), which asserts `[field.name for field in fields(reference)]` against a literal list.
      Story 3.2 freezes this contract into a `RunSnapshotV1`; pin the order now.

### Task 3 — The `scheduling_draft` capability (AC: 1)

- [x] `application/capabilities/scheduling_draft.py`, in `scheduling_compute.py`'s exact shape:
      module-level `CAPABILITY_NAME`, `SCHEDULING_DRAFT_POLICY`, `EVALUATION_FIXTURES`,
      `SCOPE_CONTROLS`, typed error classes with `code`, `ERROR_CODES`, a manifest factory with a
      **deferred** `from settings import default_settings` inside it, and a module factory.
- [x] Manifest: `risk_class="draft"`, `approval_policy="none"`, `permission="scenario:draft"`,
      `scope="current_site/current_scenario_version"`, non-empty `audit_mapping` and
      `evidence_mapping`, `version_semantics` naming the immutable pin,
      `idempotency_semantics` naming the canonical-hash addressing.
      `budget_limit` / `timeout_seconds` from new settings.
- [x] **`declared_codes == set(manifest.errors)` is an EQUALITY**
      (`tests/test_capability_conformance.py:118-124`). Every `SchedulingDraftError` subclass in the
      module must appear in `errors`, and every declared code must have a class.
- [x] `retryable_error_codes` covers `invalid_query` only — Gap 2's correction path. A timeout is
      non-retryable (Story 2.7 Task 8's precedent: re-issuing burns the budget it protects).
- [x] Resolve every proposed entity through the trusted exact-target resolvers
      (`resolver_name_for_evidence_group`, as `resolve_clarification` does). **A miss is a refusal,
      never a retarget** (AR11). Bound the proposed constraint tuple by an application constant, as
      `MAX_CANDIDATES = 10` bounds candidates — model output must not decide how many projection
      reads a request performs.
- [x] Read the pinned version's locks and carry them as `preserved_locks`. Read
      `ScenarioOverviewV1` for `expected_baseline_schedule_version`.
- [x] Compose `consequence_summary` from the validated constraints **in the application**. It must
      contain **no computed metric** — a handler that computes coverage has become an ungoverned
      calculator `scheduling_compute` must later recompute against (Story 2.5's trap list;
      `docs/DOMAIN-MODEL.md` §5).
- [x] `model_facing_view` returns `SchedulingDraftModelViewV1(draft_id=...)` and nothing else.
      `test_every_installed_module_declares_a_model_facing_view` and
      `test_scheduling_compute_never_hands_the_model_its_computed_value` are the precedent; add the
      sibling assertion for this module.
- [x] `draft_id` is content-addressed over `(scenario_version_id, canonical constraints, canonical
      preserved locks)` using Task 1's canonicalizer. **Load-bearing:** golden cases drive an
      authored `ScriptedModelTurn`, so a scripted turn must be able to cite a `draft_id` written into
      the case file. A per-call UUID would make every draft case unwritable
      (`sprint-change-proposal-2026-08-13.md` §5.3 records this for `result_id`).
- [x] Register in `application/capabilities/installed.py` `_INSTALLED_FACTORIES` — one line.
- [x] `settings.py`: add `scheduling_draft_enabled: bool = True`, `scheduling_draft_timeout_seconds`,
      `scheduling_draft_max_constraints`. **Three sites each** — dataclass field, the `_flag`/parse
      block (~lines 233-256), and the constructor kwargs (~lines 283-289). A policy with no setting
      makes `enabled_feature_policy` raise (`installed.py:63-68`), which is the intended fail-closed
      behaviour — verify it by observing that red before adding the setting.

### Task 4 — Fourth output variant and the untrusted→trusted seam (AC: 1)

- [x] `agent/runtime.py`: add `DRAFT_OUTPUT_TOOL = "draft"`, add
      `ToolOutput(DraftProposalV1, name=DRAFT_OUTPUT_TOOL)` to the `answer_type is not None` list,
      and **add the name to `OUTPUT_TOOL_NAMES`**.
- [x] **This is the quietest trap in Task 4.** `ToolRoutingEvaluator` counts every assistant tool
      call whose name is *not* in `output_tool_names` as a routed capability call
      (`evals/evaluators.py:44, 61`). Omit the name and every draft case fails on an "unexpected tool
      call" that is really the output tool — and the tempting fix loosens the branch carrying NFR28's
      100% consequential/prohibited rule. `runtime.py:57-61`'s own comment warns of exactly this
      ("a hardcoded copy diverges silently the day a fourth variant is registered").
- [x] `_reject_numeric_prose` already returns early for any output that is not a `GroundedAnswerV1`
      (`runtime.py:168-169`), so a draft output needs no change there — confirm, do not modify.
- [x] `AgentRunOutcomeV1` gains the trust-boundary **pair**, mirroring
      `clarification`/`resolved_clarification` exactly: `draft: DraftProposalV1 | None` (UNTRUSTED,
      set in `backend/agent/`) and `resolved_draft: ProposalV1 | None` (TRUSTED, set by the use
      case). Document which side of the boundary each sits on, in the style of the existing
      `answer`/`grounded_response` comment block (`agent_runtime.py:229-248`).
- [x] `run_turn` sets `draft=` when `isinstance(result.output, DraftProposalV1)`, beside the existing
      clarification and refusal branches (`runtime.py:336-339`).

### Task 5 — Use-case wiring: four functions that each fail differently if missed (AC: 1, 2)

- [x] `execute_turn`: when `outcome.draft is not None`, bind the cited `draft_id` to the trusted
      `SchedulingDraftResultV1` captured in `calculation_results`. A cited `draft_id` with no matching
      trusted result is a **failure**, not a rendered draft.
- [x] **The existing lookup will not find it.** `execute_turn.py:51-55` builds `by_id` by filtering
      the sink on `isinstance(getattr(value, "result_id", None), str)` — a result exposing only
      `draft_id` is silently absent, and the symptom is "the model cited a draft that does not
      exist" on a turn where the capability succeeded. Resolve it deliberately, not by accident:
      name the trusted result's identifier field **`result_id`** (matching the sink's existing
      contract and `TrustedCalculationResultV1`'s convention) and let `DraftProposalV1.draft_id`
      be the model-facing name for the same value. Assert the round trip in a test.
- [x] `terminal_status`: add the resolved draft to the `any(value is not None for value in (...))`
      tuple (`execute_turn.py:64-72`). **Miss this and a successful draft turn is finalised
      `agent_failed`** — it fails as a wrong status beside a rendered draft, not as an exception.
- [x] `terminal_outcome`: return `None` for a draft turn, as it does for a clarification and a
      grounded response (`execute_turn.py:142-145`). Miss this and the payload becomes a
      `TerminalOutcomeV1` and the draft is silently discarded.
- [x] `activity_payload`: add the draft branch **before** the terminal branch.
- [x] `outcome_visible_text`: add a draft branch returning the application-composed
      `consequence_summary`. **Miss this and every draft golden case's `expected_visible_text`
      assertion is vacuous** — `runtime.py` sets `output_text=None` for every structured case, so
      `(output_text or "") == ""` passes trivially. That is the exact defect
      `deferred-work.md:132-136` recorded and Story 2.9 closed; do not reopen it.
- [x] **`rehydrate_history`: add a `DraftActivityV1` branch** (`execute_turn.py:271-306`). Its
      `else` raises `ValueError("unsupported history activity ...")`, so **without this branch every
      subsequent turn in a conversation that contains a draft fails** — and no test written for
      *this* story's happy path goes red, because that path creates one draft in a fresh
      conversation. Ship a test that sends a second message after a draft.

### Task 6 — Persist the proposal and the draft activity (AC: 1, 3, 4)

- [x] One Alembic migration adding `proposal`, `proposal_version`, `command_idempotency` with the
      RLS, index, composite-uniqueness and grant pattern from Decision 5. Mirror `a4f92d7c8e31`
      line for line.
- [x] `proposal`: `id`, `site_id`, `scenario_id`, `scenario_version_id`, `conversation_id`,
      `created_by_actor_id`, `state`, `current_version_id`, `resource_version`, `created_at`.
      Composite FKs `(scenario_id, site_id)`, `(scenario_version_id, site_id)`,
      `(conversation_id, site_id)` — the cross-aggregate composite-FK pattern `conversation` already
      uses (`a4f92d7c8e31:37-38`). `CHECK (state IN ('active','rejected'))`.
- [x] `proposal_version`: `id`, `site_id`, `proposal_id`, `version_ordinal`, `payload` JSONB,
      `canonical_hash`, `checksum_algorithm`, `checksum_schema_version`, `created_at`, with
      `UNIQUE (proposal_id, version_ordinal)` and the digest/algorithm CHECK constraints copied from
      `scenario_version` (`schema.py:134-145`).
- [x] `command_idempotency`: `id`, `site_id`, `actor_id`, `operation`, `body_hash`,
      `response_payload` JSONB, `created_at`, `UNIQUE (site_id, actor_id, operation, body_hash)`.
- [x] Add the tables to `adapters/postgres/schema.py`.
- [x] `application/ports/proposal.py` — a new port in `ports/scenario_projection.py`'s shape:
      `connection: Any`, **never** `sqlalchemy.Connection`. `ports/scenario_catalogue.py` is the
      repo's one open AD-1 violation and `deferred-work.md:151-168` names copying it as the mistake
      to avoid. Add the new module to `test_conversation_boundaries.py`'s `GUARDED` tuple — that
      file's own rule is that a guard whose list stops growing becomes a false coverage claim.
- [x] `adapters/postgres/proposal.py` implementing it.
- [x] `DraftActivityV1` in `application/contracts/activity.py` — the reserved `draft` discriminant
      (`activity.py:11-20`), carrying `proposal_id`, `proposal_version_id`, `consequence_summary`
      (Decision 6). Add it to the `ActivityItemV1` union.
- [x] `adapters/postgres/conversation.py`: `_payload_to_json` gains the draft branch,
      `_activity_from_payload`'s allow-list gains `"draft"` and its constructor branch,
      `finish_agent_run`'s payload union and its `else: raise TypeError` (line 399-400) gain the
      draft type. `planner_message`'s serialized payload must stay **byte-identical**.
- [x] `finish_agent_run` writes the proposal, its first version, the activity event and the agent-run
      transition in **one** transaction (Decision 1's `create-draft` bundle).
- [x] **Do not delete or re-point `test_conversations_postgres.py`'s unrenderable-variant probe.**
      Story 2.7 re-pointed it from `agent_response` to a still-reserved discriminant when that
      variant landed; if it now names `draft`, re-point it again at a reserved one. It is the only
      proof an unknown payload fails typed rather than as a 500 mid-timeline.

### Task 7 — Revise, reject, and the first idempotency key (AC: 3, 4)

- [x] `api/routers/proposals.py`, mounted `app.include_router(proposals.router, prefix="/api/v1")`
      with `prefix="/proposals"`.
- [x] `GET /api/v1/proposals/{proposal_id}` — current state, current version, resolved entities,
      constraints, preserved locks, expected versions, `state`, and a computed `stale` flag with the
      expected and current scenario version named (AC4, Decision 7).
- [x] `POST /api/v1/proposals/{proposal_id}/revisions` — body carries the revised constraint set,
      `expected_resource_version`, and an `Idempotency-Key` header. Persists a new
      `proposal_version` and bumps `resource_version`.
- [x] `POST /api/v1/proposals/{proposal_id}/rejection` — same envelope; moves `state` to `rejected`
      once.
- [x] Idempotency, all inside the command transaction: canonical body hash via Task 1's
      canonicalizer → look up `(site_id, actor_id, operation, body_hash)` → on hit return the stored
      response **unchanged**; on miss with a matching `expected_resource_version`, apply and store;
      on a **same key with a different body hash** return a stable conflict problem
      (`409`, code `idempotency_key_conflict`) and apply nothing; on a version mismatch return
      `409 stale_resource_version` naming expected and current.
- [x] **Prove replay does not double-apply against the database**, not against a mock: two
      sequential requests with the same key must leave exactly one new `proposal_version` row.
      A test that asserts the response bodies match would pass with no idempotency at all.
- [x] A revise or reject on a **stale** proposal is refused and applies nothing (AC4). A revise on a
      `rejected` proposal is refused. Both assert the row count is unchanged.
- [x] Assert the baseline is untouched — AC3's second clause. With no baseline pointer to move
      (Gap 1), the honest assertion is structural: no proposal command's SQL touches `scenario`,
      `scenario_version`, or any table outside the three this migration adds. Add an architecture
      test over `adapters/postgres/proposal.py` in the shape of
      `test_gate_a_postgres_read_adapters_contain_no_mutating_sql_literals`. Say in the test's
      docstring that it stands in for a pointer that does not exist yet, so Story 4.3 replaces rather
      than duplicates it.
- [x] `test_gate_a_mutation_audit.py` shows a **zero-line diff**. Add a companion assertion in the
      new suite that no `/api/v1/scenarios` path gained a method — the mount decision made
      structural, so a later refactor that moves the router cannot pass silently.

### Task 8 — Evaluator cases and the NFR28/NFR5 answers (AC: 1)

- [x] Golden cases are **owed mechanically**, not optionally: `validate_manifest` requires non-empty
      `evaluation_fixtures` (`capability_manifest.py:107-108`) and
      `test_installed_module_conforms` asserts every named fixture is a real file on disk
      (`test_capability_conformance.py:116`).
- [x] Ship **exactly four** under `backend/evals/golden/scheduling_draft/`, tagged
      `capability="scheduling_draft"`, `risk_class="draft"` (already in `RiskClassV1`):
      valid multi-constraint draft; unresolvable entity; out-of-range argument; stale expected
      version. Four exactly — `epics.md:1527` forbids padding, and NFR28's floor is four per allowed
      product capability.
- [x] Add `"scheduling_draft"` to `MVP_PRODUCT_CAPABILITIES`
      (`tests/test_evaluation_harness.py:487`). PRD §4.8 item 2 — "create or revise a reversible
      schedule-change draft" — makes it a product capability, not an exemption.
      `test_every_capability_meets_the_nfr28_four_case_floor` is designed to fail on an unclassified
      capability; classifying it is the intended path.
- [x] **Answer the NFR5 question that test's own assertion message demands** (lines 517-522): which
      untrusted content source can this capability's `model_facing_view` carry? **None new** — the
      view carries `draft_id` and nothing else, every label is application-composed from the
      governed projection (Decision 2), and the two covered sources (planner chat text, scenario
      data) are unchanged. **No new injection case is owed.** State this in the story's Completion
      Notes; an unstated answer reads as an unexamined one.
- [x] **No new evaluator.** Story 2.9 spent the last reserved evaluator fence
      (`deferred-work.md:129-136`). `ToolRoutingEvaluator` and `PolicyOutcomeEvaluator` cover these
      four cases once Task 4's `OUTPUT_TOOL_NAMES` entry and Task 5's `outcome_visible_text` branch
      are in place. If a case appears to need a new evaluator, that is a signal one of those two
      wiring steps is missing.
- [x] Do **not** regenerate `evidence/story-2.2/evaluation-harness-demonstration.json`.

### ⛳ Checkpoint — commit Phase A and report six numbers

**Not an unconditional pause.** This must work in an unattended `bmad-dev-auto` / `bmad-loop` run,
so **continue into Phase B unless one of the four abort conditions below fires.**

Commit Phase A (Tasks 1–8) and report:

1. Backend suite: passed / skipped / deselected, versus the Phase-A baseline.
2. `alembic check` from the **repository root** — expected: `No new upgrade operations detected.`
   and exactly one new migration file. (`deferred-work.md:138-147`: running it from `backend/` fails
   with a misleading `script_location` error. Do not repeat that mistake.)
3. `frontend/` diff: expected **zero lines**.
4. Golden dataset total (17 at creation → 21) and the per-capability counts.
5. **PROOF THE `rehydrate_history` BRANCH WAS OBSERVED RED.** Remove the `DraftActivityV1` branch
   and confirm the second-turn-after-a-draft test raises
   `ValueError: unsupported history activity DraftActivityV1`. This is the story's quietest trap
   (Task 5) and a branch never seen to be necessary proves nothing.
6. **PROOF THE IDEMPOTENCY REPLAY TEST WAS OBSERVED RED.** Remove the `command_idempotency` lookup
   and confirm the replay test fails on a **row count of 2**, not on a mismatched response body.
   A replay test that only compares bodies passes with no idempotency at all.

**Abort and escalate instead of continuing if:** the paging/row-count proof in (5) or (6) could not
be observed red; Phase A exceeded roughly 2× its estimate; Gap 1's measurements turned out wrong in
code (a real lock or baseline version supply exists after all); or an AC1/AC3 behaviour turned out to
need a route Phase A did not build.

### Task 9 — Codegen and the Draft card (AC: 2, 4)

- [x] `npm run codegen` from `frontend/` (`codegen:export` then `codegen:types`). Codegen **is**
      owed: `ActivityItemOut` gains a union member and three proposal routes appear.
      `frontend/openapi.json` and `frontend/src/api/schema.d.ts` are both expected to change.
- [x] `api/schemas.py`: `DraftActivityOut(ActivityCommonOut)` with
      `activity_type: Literal["draft"]`, added to the `ActivityItemOut` discriminated union
      (`schemas.py:159-165`), plus the proposal request/response models.
- [x] `frontend/src/api/proposals.ts` — thin typed wrappers over the single `openapi-fetch` client,
      types derived from `paths[...]`. No hand-authored interfaces.
- [x] `frontend/src/hooks/useProposal.ts`, `useReviseProposal.ts`, `useRejectProposal.ts` — thin
      TanStack Query wrappers; business logic stays in the component.
- [x] `frontend/src/features/chat/DraftCard.tsx`. **Name the domain concept `proposal` in code**:
      `Composer.tsx:26` already uses `draft` for unsent message text, and two meanings for one word
      inside one feature directory is a real defect source.
- [x] The card renders, per AC2 and UX-DR9: resolved entities, constraints/objectives with their
      application-composed descriptions, preserved locks, expected scenario and baseline versions,
      consequence summary, and the literal text label **"Draft — no baseline change"** above the
      parameters (`DESIGN.md:128`). Identifiers use the `{typography.identifier}` monospace style.
- [x] Inherit shadcn `Card`, `Input`, `Select`, `Button`, `Separator` — all present under
      `components/ui/`. Introduce no new palette (UX-DR33) and no glow, gradient or pulse (UX-DR32).
- [x] `ActivityTimeline.tsx`: add the `case "draft":` branch. The `default` branch's
      `const exhaustive: never = item` keeps `tsc` proving exhaustiveness; its runtime fallback copy
      stays (`ActivityTimeline.tsx:287-301`).
- [x] Revise and reject are **separately labelled, separately reachable, `min-h-11` controls**,
      visually and structurally discontinuous from Send (AC2, UX-DR35). Ship an automated assertion
      of the discontinuity — `EXPERIENCE.md:196` makes automated coverage the only accepted proof
      here.
- [x] **Ship no Run optimization control and no disabled placeholder for one.** AC2 says so
      explicitly, and Story 2.3 Task 9 set the same precedent. Story 3.6 introduces the control and
      its command together.
- [x] Stale state (AC4): the card names expected and current versions, disables revise, offers only
      currently-valid actions, and **never silently refetches into a rebased draft**. Follow
      `EXPERIENCE.md:123`'s "Scenario/baseline drift marks affected Draft/Approval request stale and
      disables consequential actions".

### Task 10 — Accessibility proof (AC: 2, 4)

- [x] Extend `frontend/src/test/accessibility-contract.test.tsx` — **not** a sibling file.
      `deferred-work.md:206` records that Story 2.8's sibling
      (`evidence-accessibility.test.tsx`) sits outside the `accessibility_component_layer` Gate A
      check's hand-written file list, so its assertions are protected by CI but invisible to Gate A.
      Do not create a second orphan.
- [x] Assert: the Draft card is a named region; the "Draft — no baseline change" label is real text,
      not a colour or an icon; revise and reject have distinct accessible names; the stale state is
      announced through the existing polite live-region pattern; a disabled control carries an
      accessible explanation. Status meaning must never depend on colour alone (UX-DR32, NFR18).
- [x] **Add no new Playwright spec.** Story 3.12 owns the end-to-end repair journey, and a new spec
      inside a Gate A check trips `deferred-work.md:208`'s reporter-truncation item, whose owner is
      "the first story that adds a new Playwright spec to a Gate A check".

### Task 11 — Fences, ledger, regression, Gate A (AC: 1, 2, 3, 4)

- [x] Verify every zero-line fence in *Project Structure Notes* with `git diff --stat`.
- [x] Full regression: backend default, `pytest -m postgres`, `pytest tests/test_evidence_convention.py`,
      `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npx playwright test`,
      `alembic check` from the repository root.
- [x] **Ledger routing. This story CLOSES nothing** — stated explicitly so nobody closes something
      opportunistically. Every Epic 3 item the retro lists belongs to a later story: `:16`
      (`remaining_budget`), `:39` (retention job), `:180` (stranded run) → Story 3.3; `:202`
      (`shortfall_minutes`), `:200` (headcount metric) → Story 3.2/3.8 once the solver supplies a
      per-worker rate; `:190` (overlap filter keys) → only a story amending `GROUP_QUERY_TABLES`,
      which this is not; `:206`, `:208` → untouched per Tasks 10; `:214`, `:216` → untouched.
      `ALLOWED_LEAKS` in both architecture guards stays untouched.
- [x] **RE-ANNOTATE `deferred-work.md:172-176` (UX-DR35 Send discontinuity) without closing it.**
      The retro assigns it to Story 3.1 because "its AC ships revise/reject beside Send"
      (`epic-1-2-retro-2026-08-16.md` §5.1). Judged at creation: **the entry's own stated owner
      condition is "the first story to ship a Run optimization or Approve control on the Chat
      surface", and AC2 forbids this story from shipping either.** So Story 3.1 discharges the half
      it can — revise/reject are discontinuous from Send, with an automated assertion (Task 9) — and
      the entry stays **open** with its owner restated as **Story 3.6**. Annotate in place; this is
      the Story 2.4/2.5/2.8 precedent for a false ledger premise.
- [x] **Correct the retro's Story 3.1 premise, in `deferred-work.md:106-107`.** It states that Story
      1.9's parity/mutation-denial invariant "gates the mutation-denial invariant that Story 3.1
      writes into". Judged FALSE at creation: Story 1.9's invariant is about **fixture source data**
      (FR22/FR24) — no `scenario` or `scenario_version` row is touched here, and Story 2.3 already
      added a governed write path without disturbing it. What Story 3.1 actually does is add the
      first mutating route outside `/api/v1/conversations`, which is why Task 7's structural
      assertions exist. Record the correction and leave the P3 work where the retro finally put it:
      **alongside** Epic 3, not gating this story.
- [x] Add the two Story 2.7 corrections from Gap 1 to the ledger:
      `baseline_schedule_version` is `None` at both producers, and `get_locks` has no supply at all.
- [x] **No evidence file is owed.** No AC carries a measured threshold, and NFR35's four rows belong
      to Stories 1.4, 1.5, 2.4 and 3.5 (AD-26).
- [x] Re-run Gate A per AR28. **The two-commit dance is retired** as of commit `8139866`:
      `gate_a_readiness.main()` now exempts its own output from the dirty-tree check. Follow
      `docs/GATE-A-RUNBOOK.md` §3 as written and expect `gate_a_passed: true`, `blocking: []`.
      Do not tune the registry or soften a result to reach `true`.

### Review Findings

Code review of 2026-08-18 (three parallel layers: adversarial, edge-case, acceptance).
31 findings after deduplication: 28 patch, 3 deferred. 0 dismissed.
Of the 28 patches, 3 began as decision-needed findings, were resolved by Minh on 2026-08-18, and
carry their resolution inline. All 28 were applied in this review; the 3 deferred items were not.
Every location below was re-read in the source before rating; subagent severities were discarded.

- [x] [Review][Patch] **RESOLVED 2026-08-18 — the code is wrong; adopt AD-8 as written.** Fold `expected_resource_version` into the body hash so a replay carrying a different expected version returns 409 `idempotency_key_conflict`, and so rejections stop hashing the constant `sha256(b"{}")`. `test_revision_replay_does_not_append_a_second_version` must be updated: it currently changes the version 1→2 and still expects a replay. Original finding: **AD-8's "plus expected resource version" clause is deliberately dropped from the idempotency body hash** — `_body_hash(expected_resource_version, value=None)` never references its first parameter, and a comment above it defends the omission ("the expected version is the concurrency guard, not the semantic command body"). AD-8 (`ARCHITECTURE-SPINE.md:136`) and this story's own facts table both say the key is scoped to actor, site, operation, canonical body hash **plus expected resource version**. Consequence: replaying one key with a genuinely stale `expected_resource_version` returns the stored 200 instead of 409 `stale_resource_version`; for rejections the hash is the constant `sha256(b"{}")` for every rejection ever issued, so AD-8's "a conflicting body fails" clause is unreachable on that path. `test_revision_replay_does_not_append_a_second_version` actively encodes the divergence by changing the version from 1 to 2 and still expecting a replay. Either the code adopts AD-8 as written, or AD-8's reading is amended and the story's facts table corrected — a deliberate documented choice against a recorded architecture rule is yours to settle. [backend/application/use_cases/manage_proposal.py:70-76, :197]
- [x] [Review][Patch] **RESOLVED 2026-08-18 — keep 56 as a flat sanity ceiling, but stop claiming it is employment-type-derived.** Drop `employment_type` from the refusal message and add a `SCOPE_CONTROLS` entry recording the assumption (`NOT COVERED: per-employment-type caps; 56 is a flat upper sanity bound`), satisfying `docs/DOMAIN-MODEL.md` §5 item 7. The real per-type cap arrives with the solver at Story 3.2. Original finding: **`HARD_MAX_HOURS_PER_WEEK = 56.0` is an invented universal ceiling presented as an employment-type cap** — the refusal message interpolates the worker's `employment_type` while the bound ignores it entirely. The real constant, `config/constants.py:9` `DEFAULT_MAX_HOURS_PER_WEEK`, is documented in its own section header as "per employment type, used when not specified" and is consumed as a *fallback*: `max_hours_per_week.get(member.emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK)` (`engine/cpsat/builder.py:277`, `:392`). So a part-time worker whose configured cap is 20h has `max_hours: 55` accepted and persisted as a trusted constraint, which makes builder.py:392's overflow bound `(hard_cap - max_hours)` negative at Story 3.2. No governed per-worker cap is reachable from the draft path: `WorkerV1.contracted_hours` exists in the projection and is unused, and `max_hours_per_week` is solver-side. `docs/DOMAIN-MODEL.md` §5 item 7 is explicit that a rule you need which is not written down must be recorded before implementing against it, and `SCOPE_CONTROLS` declares no such assumption. What is the cap, and where should it come from? [backend/application/capabilities/scheduling_draft.py:34, :286-304]
- [x] [Review][Patch] **RESOLVED 2026-08-18 — intended for this MVP scope.** Shared intra-site drafting is the product posture: any planner in a site may revise or reject any draft, and `created_by_actor_id` stays as the audit trail. Record it as an explicit `SCOPE_CONTROLS` entry so the absence is a stated decision rather than an oversight. Original finding: **The first mutating routes outside `/api/v1/conversations` enforce no role and no ownership** — `revise` and `reject` depend only on `get_site_context` and `get_session`; `ResolvedSession` carries `app_user_id`, `site_id`, `csrf_token_hash`, `expires_at` and no role. The capability declares `required_role="planner"` and the conversation path passes `role=PLANNER_ROLE`, both bypassed by the direct HTTP command path. `proposal.created_by_actor_id` is written and never read. This is not a cross-tenant hole — RLS and `site_id` hold, and `PLANNER_ROLE` is a hardcoded constant rather than a session attribute, so every authenticated member of a site is a planner by construction today. The question is a product one: is intra-site "any planner may revise or reject any other planner's draft, in any conversation" the intended posture for the first mutating surface outside conversations? [backend/api/routers/proposals.py:93-139, backend/application/ports/session.py:25-30]
- [x] [Review][Patch] Revise command accepts the TRUSTED contract off the wire and persists client-authored content unvalidated [backend/api/schemas.py:206-208, backend/application/use_cases/manage_proposal.py:110-137]
- [x] [Review][Patch] `proposal_id` is a pure content hash inserted without conflict handling, so a repeated identical draft is a primary-key collision that aborts finalisation and strands the run in `agent_running` [backend/application/capabilities/scheduling_draft.py:408-411, backend/adapters/postgres/proposal.py:32-43]
- [x] [Review][Patch] A revision keeps the old application-composed `description`, so the immutable version records `max_hours: 36` beside "Cap Alex at 40 hours per week" and the card renders the wrong number [backend/application/use_cases/manage_proposal.py:155-172, frontend/src/features/chat/DraftCard.tsx:103]
- [x] [Review][Patch] The stale card ships an `sr-only`, permanently disabled, handler-less decoy button that is the only element the accessibility assertions can resolve; the real control is not rendered when stale and its `aria-describedby` sits in a branch that runs only when `!stale`, so it is always `undefined` [frontend/src/features/chat/DraftCard.tsx:152, :166-168]
- [x] [Review][Patch] The three failure golden cases cannot go red — all declare `expected_outcome: "allow"`, `expected_visible_state: "completed"`, and an `expected_visible_text` equal to their own scripted prose; deleting the capability's refusals leaves them green [backend/evals/golden/scheduling_draft/unresolvable-entity.json, out-of-range-argument.json, stale-version.json]
- [x] [Review][Patch] No golden case emits the `draft` output tool — all four end in a plain `response_text`, so `DraftProposalV1`, `DRAFT_OUTPUT_TOOL`, the `execute_turn` citation binding and `outcome_visible_text`'s draft branch have zero golden coverage, and no case cites a `draft_id`, which was the entire reason it had to be content-addressed [backend/evals/golden/scheduling_draft/]
- [x] [Review][Patch] A stale proposal can never be rejected, leaving the aggregate permanently `active` with no terminal path — the backend raises `StaleProposalError` before the state transition and the card removes the Reject button entirely; rejection changes no baseline and is the one action unconditionally safe on a stale draft [backend/application/use_cases/manage_proposal.py:210-211, frontend/src/features/chat/DraftCard.tsx:146-148]
- [x] [Review][Patch] An idempotent replay returns a frozen `stale` flag and `current_scenario_version_id` from the stored payload, defeating AC4 on the replay path and contradicting AD-14 ("cached data is never authority") [backend/application/use_cases/manage_proposal.py:79-87]
- [x] [Review][Patch] The idempotency key is folded into the `operation` string and the lookup filters on three of the unique key's four columns with an unordered `.limit(1)`, so DB uniqueness cannot enforce the same-key-different-body rule that AD-8 assigns to it [backend/application/use_cases/manage_proposal.py:66-67, backend/adapters/postgres/proposal.py:100-106]
- [x] [Review][Patch] The capability timeout is measured after every entity resolution and the full lock drain complete, so it bounds nothing and can only convert a finished draft into a non-retryable failure [backend/application/capabilities/scheduling_draft.py:393-397]
- [x] [Review][Patch] Revise and reject failures produce no user-visible feedback — `isError`/`error` are never read and no `onError` exists, so four distinct RFC 7807 codes render as nothing at all [frontend/src/features/chat/DraftCard.tsx:145-165, frontend/src/hooks/useReviseProposal.ts, frontend/src/hooks/useRejectProposal.ts]
- [x] [Review][Patch] Every revise/reject click mints a fresh `crypto.randomUUID()` as a re-evaluated default parameter, so the idempotency mechanism is unreachable from the only client that calls it [frontend/src/api/proposals.ts:25, :44]
- [x] [Review][Patch] `useEffect` on `query.data` overwrites local edits on any refetch — a window-focus refetch silently discards the planner's typed value and resets the selected constraint to 0 [frontend/src/features/chat/DraftCard.tsx:34-39]
- [x] [Review][Patch] The baseline-untouched architecture test asserts one file's import block rather than scanning for mutating SQL literals as the test Task 7 named it after does; a `connection.execute(text("UPDATE scenario ..."))` would pass it, and it covers neither the use case, the orchestrator, nor the router [backend/tests/test_proposal_persistence.py]
- [x] [Review][Patch] The Gate A mount guard forbids only `post`, while the invariant it stands in for asserts `/api/v1/scenarios` paths expose *only* `get`; a future `patch`/`put`/`delete` passes silently [backend/tests/test_proposal_persistence.py]
- [x] [Review][Patch] The `ProposalV1` to `DraftActivityV1` mapping lives in the conversation adapter, which now imports the Scheduling-aggregate contract — AD-22 permits only an application orchestrator to cross owners, and `finalize_agent_run` already exists as that orchestrator [backend/adapters/postgres/conversation.py:28, :397-405]
- [x] [Review][Patch] "Discontinuous from Send" is never asserted against Send — both tests named for it compare revise against reject and neither renders `Composer.tsx` or any Send control, while `deferred-work.md` records the item as partially discharged; the `Separator` it leans on is a hand-rolled `aria-hidden` div with no `role="separator"` [frontend/src/features/chat/DraftCard.test.tsx:92, frontend/src/test/accessibility-contract.test.tsx, frontend/src/components/ui/separator.tsx]
- [x] [Review][Patch] Two canonical-hash producers use different pre-canonicalization shapes — `asdict` plus manual UUID stringification on the draft path, `TypeAdapter(type(constraints))` on the revise path where `type(constraints)` is the bare builtin `tuple` and the declared item type is erased. Both layers executed both paths and they agree today, so this is fragility rather than a live bug, but nothing pins the equivalence the way `test_restricted_result_id_matches_the_shared_canonicalizer` pins the compute pair [backend/application/capabilities/scheduling_draft.py:118-131, backend/application/use_cases/manage_proposal.py:146-154]
- [x] [Review][Patch] `create_draft` writes before the run-still-claimable guard, so a duplicate finalisation aborts with `IntegrityError` and masks the `AgentRunNotQueuedError` the ordering exists to raise; reversing the two calls costs nothing [backend/application/use_cases/finalize_agent_run.py:29-43]
- [x] [Review][Patch] A stale *and* rejected proposal renders as merely stale — the ternary tests `stale` first, making the "This proposal was rejected." branch unreachable, and Refresh re-renders the same screen forever [frontend/src/features/chat/DraftCard.tsx:146-164]
- [x] [Review][Patch] The revise path hardcodes `1 <= len(constraints) <= 10` while the draft path reads `settings.scheduling_draft_max_constraints`, so lowering the setting yields drafts that cannot be revised and raising it is bypassed by the command path [backend/application/use_cases/manage_proposal.py:110, backend/api/schemas.py:207]
- [x] [Review][Patch] Error plumbing contradicts the declared contract — `_command_problem` returns a `JSONResponse` from routes annotated `-> ProposalOut` with `response_model=ProposalOut`, and `read_proposal` raises a bare `HTTPException(404)` with no problem code while advertising `ProblemDetailsV1`; the generated client therefore types none of the conflict codes [backend/api/routers/proposals.py:53-77, :89]
- [x] [Review][Patch] `PARAMETER["exclude_worker_from_task"]` is a dead mapping kept alive only by exhaustiveness and neutralised by a separate guard at the use site — a trap for the next editor who removes the guard [frontend/src/features/chat/DraftCard.tsx:18, :114]
- [x] [Review][Patch] The timeline discards the persisted activity payload and casts away the discriminated union — `DraftActivityV1` carries `proposal_version_id` and `consequence_summary` specifically so a reference can render, yet the card shows "Loading draft proposal..." until a round trip completes, and `as Draft` defeats the file's own `const exhaustive: never` check [frontend/src/features/chat/ActivityTimeline.tsx]
- [x] [Review][Patch] `get_proposal` returns 404 when the scenario projection is momentarily unavailable, or when `current_version_id` is NULL (inner join), so "the scenario could not be read" and "an inconsistent row" both render as "this proposal does not exist" [backend/application/use_cases/manage_proposal.py:52-62, backend/adapters/postgres/proposal.py:65-76]
- [x] [Review][Defer] No reaper exists for an agent run stranded in `agent_running` by an aborted finalisation [backend/application/use_cases/finalize_agent_run.py] — deferred, pre-existing
- [x] [Review][Defer] Every `ProposalV1` field carries a default, so `ProposalV1()` constructs an empty proposal and AD-20's "required shape" is enforced only by downstream `is None` re-checks [backend/application/contracts/proposal.py:76-95] — deferred, pre-existing pattern
- [x] [Review][Defer] More than 200 preserved locks makes a scenario permanently undraftable through a non-retryable error with no setting to raise it [backend/application/capabilities/scheduling_draft.py:33, :308-333] — deferred, unreachable until a lock supply exists (Gap 1)


---

## Dev Notes

### What this story is, and what it is not

**It is:** the reversible-draft boundary. Intent → validated, resolved, immutable `ProposalV1` →
reviewable card → revise or reject. Nothing computes and nothing is promoted.

**It is not:**

| Not this | Owner |
|---|---|
| A Run optimization control, or a disabled placeholder for one | Story 3.6 (AC2 forbids it here) |
| `RunSnapshotV1`, CP-SAT execution, `ScheduleVersionV1` | Story 3.2 |
| Job leasing, fencing epochs, a reaper for runs stranded in `agent_running` | Story 3.3 (`deferred-work.md:180`) |
| Cancellation of anything | Story 3.4 (`ScheduleRun`) — and note `AgentRun` cancellation has **no owner at all** (`deferred-work.md:214`, retro §5.2: two different cancellations sharing one word) |
| Run progress cards, the Runs workspace | Stories 3.5, 3.7 |
| `ComparisonV1`, `MetricSetV1` | Story 3.8 |
| Approval, the baseline pointer, `AuditEnvelopeV1` | Epic 4 |
| A generic idempotency middleware | Each command's own story (Decision 4) |
| Any new metric, or a metric computed inside the draft | `scheduling_compute`; `docs/DOMAIN-MODEL.md` §5 |
| Editing a committed contract fixture | Story 1.1 owns fixture import |

### The traps, ranked by how quietly they fail

1. **`rehydrate_history`'s `else: raise ValueError`** (`execute_turn.py:297-298`). A conversation
   containing a draft breaks **every later turn** in it. No test written for this story's happy path
   goes red; the failure is a 500 on turn two, in a conversation the planner has already invested in.
2. **A vacuous "locks were preserved" assertion.** `get_locks` returns a hardcoded `()`, so the
   assertion passes against nothing. Retro §3.1's dominant failure mode; Gap 1 states the required
   posture.
3. **A vacuous `expected_visible_text`.** `output_text` is `None` for every structured case, so
   `(output_text or "") == ""` passes trivially unless `outcome_visible_text` gains a draft branch.
   Exactly `deferred-work.md:132-136`'s defect, closed by Story 2.9 — do not reopen it on paper.
4. **A fourth output tool missing from `OUTPUT_TOOL_NAMES`.** Every draft case fails on an
   "unexpected tool call" that is really the output tool, and the tempting fix loosens the branch
   carrying NFR28's 100% rule (Task 4).
5. **`test_a_disabled_capability_is_absent_from_the_composed_grant` goes red for the right reason.**
   It hardcodes three `*_enabled` flags in `replace_dataclass`
   (`tests/architecture/test_execute_turn_boundaries.py:92-103`); a fourth capability whose flag is
   left at its default makes `_granted(all_off)` non-empty. **Add `scheduling_draft_enabled=False`
   to `all_off` and `=True` to `all_on`, and add the one-off discriminating case.** Do not weaken the
   assertion — it is the AD-2 "absent, never present-and-refusing" proof.
6. **`terminal_status` missing the resolved draft** — a successful draft turn finalises as
   `agent_failed`, rendering a valid draft beside a failure status.
7. **A third RFC 8785 implementation.** Task 1 exists for this. `adapters/postgres/canonical_json.py`
   is already complete and pure; capability handlers may not import `adapters`.
8. **`declared_codes == set(manifest.errors)` is equality, not subset**
   (`test_capability_conformance.py:118-124`).
9. **Reusing `services/constraint_service.py`'s fuzzy `_resolve_task`/`_resolve_member`.** Reads as
   reuse; **is** the model-authored-identity inversion (AD-2; Story 2.9 Decision 5).
10. **Mounting under `/api/v1/scenarios`** — breaks `test_gate_a_mutation_audit.py:24-34`, which
    AR28 forbids editing.
11. **A `PATCH`/`PUT`/`DELETE` command** — `api/main.py:254` allows only `GET` and `POST` through
    CORS. Passes same-origin, fails in a deployed topology.
12. **Naming the domain concept `draft` in frontend code** — collides with `Composer.tsx:26`'s
    unsent-message-text `draft`.
13. **An idempotency replay test that compares response bodies instead of row counts** — passes with
    no idempotency at all. Checkpoint item 6 exists for this.
14. **A trusted draft result the sink's `by_id` filter cannot see** (Task 5). The capability
    succeeded, the model cited correctly, and the turn reports that the citation does not resolve.

### Existing conventions to match, not reinvent

| Need | Copy from |
|---|---|
| Capability module shape (errors, `ERROR_CODES`, `SCOPE_CONTROLS`, deferred settings import, module factory) | `application/capabilities/scheduling_compute.py` |
| Content-addressed identifier a scripted golden case can cite | `scheduling_compute.derive_result_id` (`:207-247`) |
| Trusted result → model-facing view split | `SchedulingComputeResultV1` / `SchedulingComputeModelViewV1` (`:149-204`) |
| Application-resolved entity labels from a model-proposed `(group, record_id)` | `application/clarification/resolve.py` |
| Untrusted/trusted contract pair on `AgentRunOutcomeV1` | `clarification` / `resolved_clarification` |
| New `ActivityItemV1` variant, all five change points | Story 2.7's `agent_response`; Story 2.9's `clarification` |
| Migration: RLS, FORCE RLS, policy, index, composite uniqueness, grant-then-revoke | `migrations/versions/a4f92d7c8e31_add_durable_conversations.py` |
| A single narrow column UPDATE grant | `migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py` |
| Digest/algorithm CHECK constraints | `schema.py:134-145` (`scenario_version`) |
| Port with `connection: Any` (never the vendor type) | `application/ports/scenario_projection.py:104` |
| Frozen contract field-order test | `tests/test_evidence_ref.py:63` |
| Thin typed API wrapper + TanStack hook | `frontend/src/api/conversations.ts`, `hooks/useSendMessage.ts` |
| RFC 7807 problem responses with stable codes | `api/problems.py`; `conversations.py:323-335` |

### Latest technical information (verified against the repo at `2b48b72`)

- **No new dependency.** `pydantic-ai-slim[google,openrouter]==2.27.0` is a repository lock
  (`backend/pyproject.toml`), so no AR19/AR27 gate ceremony applies. `ToolOutput` is already imported
  (`agent/runtime.py:33`) and Story 2.9 measured that `ToolOutput(X, name=...)` preserves the exact
  tool name and yields `allows_text=False`.
- **CI now exists and enforces counts.** `.github/workflows/ci.yml` (merged in PR #3) runs backend
  pytest, the PostgreSQL suite, the evidence-convention sweep, `alembic check`, frontend
  lint/typecheck/build/vitest, and Playwright. `.github/scripts/assert_counts.py` enforces pass
  counts as **floors** and skip counts as **ceilings**, so adding tests never reddens CI — but a
  silently skipped suite always does. Note the backend default ceiling is `--max-skipped 1`
  (`ci.yml:179`); a local run recorded 2 skipped at `8139866`. **Verify which is current before
  assuming a red CI is yours.**
- **Gate A is re-runnable.** Prep task P2 is cleared (`8139866`); the two-commit dance no longer
  applies. `docs/GATE-A-RUNBOOK.md:246-247`'s dirty-tree note refers to `regenerate_evidence.py`,
  a different script, and is still accurate.
- **`alembic check` must run from the repository root.** `alembic.ini` is checked in at the root with
  `script_location = %(here)s/backend/migrations`; from `backend/` it fails with a misleading
  `No 'script_location' key found` (`deferred-work.md:138-147`).
- **Golden dataset at creation: 17 cases** — `demonstration` 2, `scheduling_compute` 4,
  `scheduling_inspect` 11. This story contributes 4 → **21**. NFR28's 50-case floor is **not**
  re-verifiable here: three of its five named contributors (3.10–3.12, 4.5–4.6) have contributed
  nothing. Record the contribution and the running total; do **not** lower the threshold (Gate B's
  call, with all five present) and do **not** pad (`epics.md:1527`).
- **Fixture reality, measured** (both `data/contract/*.projection-v1.json`): tasks 6, workers 10 /
  22, demand intervals 1547, constraints 14, **locks 0, baseline assignments 0,
  `baseline_schedule_version` null**. See Gap 1.

### Project Structure Notes

**New files** (AR26's structural seed):

```
backend/application/contracts/canonical.py          # moved from adapters/postgres/canonical_json.py
backend/application/contracts/proposal.py
backend/application/capabilities/scheduling_draft.py
backend/application/ports/proposal.py
backend/adapters/postgres/proposal.py
backend/migrations/versions/<rev>_add_proposal_aggregate.py
backend/api/routers/proposals.py
backend/evals/golden/scheduling_draft/{valid,unresolvable-entity,out-of-range-argument,stale-version}.json
frontend/src/api/proposals.ts
frontend/src/hooks/{useProposal,useReviseProposal,useRejectProposal}.ts
frontend/src/features/chat/DraftCard.tsx
```

**Modified (UPDATE, not NEW) — read each completely before editing:**

`agent/runtime.py` · `application/contracts/agent_runtime.py` · `application/contracts/activity.py` ·
`application/use_cases/execute_turn.py` · `application/capabilities/installed.py` ·
`adapters/postgres/conversation.py` · `adapters/postgres/schema.py` ·
`adapters/postgres/fixture_history.py` (one import line) · `api/schemas.py` · `api/main.py` (one
`include_router` line) · `api/deps.py` (proposal repository provider) · `settings.py` ·
`tests/architecture/test_execute_turn_boundaries.py` (trap 5) ·
`tests/architecture/test_conversation_boundaries.py` (`GUARDED`) · `tests/test_evaluation_harness.py`
(`MVP_PRODUCT_CAPABILITIES`) · `tests/test_fixture_history_import.py` (one import line) ·
`frontend/src/features/chat/ActivityTimeline.tsx` · `frontend/openapi.json` ·
`frontend/src/api/schema.d.ts` (codegen) · `frontend/src/test/accessibility-contract.test.tsx`

**Mandated zero-line diffs** — verify with `git diff --stat`:

```
backend/domain/**                          backend/engine/**
backend/llm/**                             backend/ingest/**
backend/store/**                           backend/services/**
backend/agent/translate.py                 backend/application/capabilities/scheduling_compute.py
backend/application/capabilities/scheduling_inspect.py
backend/application/grounding/**           backend/application/clarification/resolve.py (except the
                                             extracted shared label helper)
backend/adapters/postgres/scenario_projection.py
backend/adapters/postgres/scenario_catalogue.py
backend/application/ports/scenario_catalogue.py
backend/tests/test_gate_a_mutation_audit.py
backend/scripts/gate_a_checks.py           data/contract/**
evidence/story-2.2/**                      frontend/src/features/scenario-data/**
frontend/src/features/evidence/**          frontend/e2e/**
frontend/src/features/chat/Composer.tsx    frontend/src/features/chat/ConversationList.tsx
```

`backend/adapters/postgres/canonical_json.py` is **deleted** by Task 1 and is therefore not fenced.

### References

- `_bmad-output/planning-artifacts/epics.md#Story-3.1` (ACs, verbatim) and `#Epic-3` sequencing note
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-09-epics-2-5.md:138` — Story 3.1 KEEP as-is
- `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`
  — AD-1, AD-2, AD-5, AD-8, AD-9, AD-13, AD-14, AD-20 (*Normative contract minimums*, `ActivityItemV1` row), AD-21, AD-22, AD-23, AD-26
- `_bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md` — §3.3 step 6, §4.3 FR-9/FR-10, §4.8 item 2, §5.1 autonomy tiers
- `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — Draft card (`:87`), Chat states (`:123`), Flow 1 step 4 (`:233`), Accessibility Floor (`:196`)
- `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md:128` — Draft card visual contract
- `docs/DOMAIN-MODEL.md` — §1 family/unit, §2 what an assignment carries, §3 question routing, §5 checklist
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md` §3
- `_bmad-output/implementation-artifacts/deferred-work.md` — `:59`, `:106-107`, `:132-136`, `:138-147`, `:151-168`, `:172-176`, `:180`, `:190`, `:198`, `:200`, `:202`, `:206`, `:208`, `:214`
- `_bmad-output/implementation-artifacts/epic-1-2-retro-2026-08-16.md` — §3.1, §3.2, §3.3, §5.1, §5.2, §6.1 (A2, A3), §6.3
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-13.md` — the cite-don't-recompute mechanism this story reuses

### Baselines at creation — re-derive them, do not trust them

Both Story 2.7 and Story 2.8 found their inherited baselines stale (2.7 by 100+ tests).

| Suite | CI-recorded (`faf22eb`, 2026-08-16) | Collected at `2b48b72` |
|---|---|---|
| backend default | 864 passed, 1 skipped, 7 deselected | 876 collected (883 total, 7 deselected) |
| backend `-m postgres` | 45 passed, 0 skipped | 45 collected |
| evidence convention | 48 passed, 0 skipped | — |
| frontend vitest | 400 passed, 63 files | 400 / 63 files |
| Playwright | 48 passed, 7 files | 48, 7 files |
| `alembic check` | zero operations | — |
| Gate A | `gate_a_passed: true`, `blocking: []` | — |

`8139866`'s commit message records 866 passed / 2 skipped locally, which exceeds CI's
`--max-skipped 1` ceiling. Establish the real current numbers before attributing any CI failure to
this story's changes.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

- Execute each story task in order using red-green-refactor, with a focused test gate and full regression before marking it complete.
- Preserve the application/adapter boundary, immutable contract shapes, governed version pins, and zero-line scope fences named by the story.
- Complete Phase A, record the required non-vacuous red proofs and checkpoint measurements, then continue through frontend delivery and Gate A.

### Debug Log References

- Task 1 RED: focused collection failed because `application.contracts.canonical` did not exist.
- Task 1 GREEN: 57 focused tests passed; full backend regression passed (868 passed, 2 skipped, 7 deselected).
- Task 2 RED: proposal contract tests failed to import the not-yet-created shared label and proposal contracts.
- Task 2 GREEN: 8 focused tests passed; full backend regression passed (871 passed, 2 skipped, 7 deselected).
- Task 3 RED: capability tests initially failed because the module did not exist; after registration, the policy-setting test failed on the deliberately absent `scheduling_draft_enabled` supplier before that setting was added.
- Task 3 GREEN: 71 focused capability/settings/conformance/boundary tests passed; full backend regression passed (889 passed, 2 skipped, 7 deselected).
- Task 4 RED: adapter tests proved the `draft` output tool and outcome fields were absent and that the unchanged text-path snapshot had no draft fields.
- Task 4 GREEN: 67 focused adapter/contract/evaluation tests passed; full backend regression passed (891 passed, 2 skipped, 7 deselected).
- Task 5 RED: execute-turn tests failed to import the new draft activity and had no trusted-result binding, terminal, visible-text, or rehydration branches.
- Task 5 GREEN: 25 focused use-case/conversation-contract tests passed; full backend regression passed (894 passed, 2 skipped, 7 deselected).
- Task 6 RED: draft serialization, proposal metadata, and migration tests failed at the absent persistence seams.
- Task 6 GREEN: 66 focused contract/schema/architecture/PostgreSQL tests passed (1 skipped); full backend regression passed (900 passed, 2 skipped, 7 deselected).
- Task 7 RED: PostgreSQL command tests initially failed while resolving the deliberately minimal fixture projection, proving the new command paths were exercised before the current-version seam was isolated.
- Task 7 GREEN: 72 focused proposal/API/schema/architecture tests passed; full backend regression passed (906 passed, 2 skipped, 7 deselected).
- Task 8 GREEN: 45 focused evaluator/conformance tests passed; dataset is exactly 21 cases with exactly 4 scheduling-draft cases; full backend regression passed (906 passed, 2 skipped, 7 deselected).
- Phase A checkpoint: 906 passed / 2 skipped / 7 deselected versus the archived `2b48b72` baseline of 867 executable passes / 1 skipped / 7 deselected (+39 passes, +1 intentional skip). The archive's 14 evidence-binding failures were solely caused by its synthetic one-commit Git history.
- Phase A checkpoint: `alembic check` reported `No new upgrade operations detected.` with exactly one new migration; `frontend/` had a zero-line diff.
- Phase A checkpoint: golden dataset total 21 — demonstration 2, scheduling_compute 4, scheduling_draft 4, scheduling_inspect 11.
- Phase A mutation proof: removing the draft-history branch raised exactly `ValueError: unsupported history activity DraftActivityV1`; restoring it returned the focused test to green.
- Phase A mutation proof: removing the command-idempotency lookup made the database replay assertion fail with 2 new revision rows versus 1 expected; restoring it returned the focused test to green.
- Task 9 RED: the Draft-card component suite failed to resolve the not-yet-created `DraftCard` module.
- Task 9 GREEN: 20 focused Draft/timeline tests passed; full frontend regression passed (404 tests / 64 files), typecheck and build passed, and lint reported only the three pre-existing Fast Refresh warnings.
- Task 10 RED proof: removing the card's accessible name made the mandated contract fail to find `region` named `Draft proposal`.
- Task 10 GREEN: 43 focused accessibility/Draft/timeline tests passed, including axe, distinct command, stale live-region, and disabled-description assertions.
- Task 11 pre-Gate regression: every zero-line fence passed; backend default 906 passed / 2 skipped / 7 deselected, PostgreSQL 51 passed, evidence convention 48 passed; frontend lint/typecheck/build passed, Vitest 404 passed / 64 files, Playwright 48 passed; `alembic check` reported no new operations.
- Task 11 Gate A: fresh bound artifacts recorded pytest 907 passed / 1 skipped / 7 deselected, Vitest 404 passed, and Playwright 48 passed / 0 failed / 0 errors / 0 skipped; readiness returned `gate_a_passed: true`, `blocking: []`.

### Completion Notes List

- Task 1: Re-homed the complete RFC 8785 canonicalizer under application contracts, added governed SHA-256 digest metadata, updated the two measured importers, and proved compatibility with the deliberately retained float-free scheduling-compute identifier path.
- Task 2: Added frozen, framework-free proposal contracts with pinned field order and closed vocabularies, a round-trip JSON fixture, derived-only staleness, and a shared application-owned planner label.
- Task 3: Added the governed draft capability with exact entity resolution, bounded validation, real lock preservation, truthful baseline-version handling, content-addressed identifiers, model-minimal projection, static installation, feature-policy settings, and retryable invalid-query failures.
- Task 4: Added the fourth named `draft` output tool, kept it excluded from capability routing results, and carried model citations separately from trusted resolved proposals.
- Task 5: Bound draft citations only to same-turn trusted capability results, failed closed on unmatched citations, finalized valid drafts as completed, projected non-vacuous visible text, and rehydrated later turns from draft activities.
- Task 6: Added governed proposal/version/idempotency storage, a framework-free proposal port and adapter, application-owned atomic finalization, draft activity persistence, RLS/grants, and commit/rollback integration proofs.
- Task 7: Added current proposal reads, immutable revisions, terminal rejection, derived staleness, optimistic concurrency, transactional canonical-body idempotency, stable conflicts, and structural baseline/scenario mutation fences.
- Task 8: Shipped exactly four scheduling-draft goldens, including a valid multi-constraint draft, and classified the capability under the NFR28 product floor. NFR5 adds no injection case: the model-facing view carries only `draft_id`; application-composed labels never enter it, so the untrusted sources remain planner chat text and scenario data.
- Phase A checkpoint completed without an abort condition: both paging/idempotency red proofs were observed, the original no-baseline/no-lock-supply gaps remain truthful, and the required proposal route was delivered within Phase A.
- Task 9: Regenerated OpenAPI/types and added generated-contract proposal wrappers, thin query/mutation hooks, an editable review card, explicit stale behavior, and a typed timeline branch. The missing `Separator` primitive assumed by the story was added in the existing shadcn-compatible component shape.
- Task 10: Extended the Gate-A-visible accessibility contract with named-region, literal-status, command-discontinuity, live-region, disabled-explanation, and axe proofs; added no Playwright spec.
- Task 11 (pre-Gate): Verified every scope fence, completed the full regression matrix, re-annotated the ledger without closing an item, recorded both Gap 1 corrections, and confirmed no story-specific evidence file is owed.
- Task 11 (Gate A): Regenerated the repository-wide readiness report from fresh post-commit JUnit inputs; all AR28, NFR29, and measurement-integrity checks passed with no blocker.

### File List

- backend/application/contracts/canonical.py (new)
- backend/adapters/postgres/canonical_json.py (deleted)
- backend/adapters/postgres/fixture_history.py (modified)
- backend/tests/test_fixture_history_import.py (modified)
- backend/tests/test_scheduling_compute.py (modified)
- backend/application/contracts/proposal.py (new)
- backend/application/clarification/resolve.py (modified)
- backend/tests/test_proposal_contracts.py (new)
- backend/tests/fixtures/proposal-v1.json (new)
- backend/application/capabilities/scheduling_draft.py (new)
- backend/application/capabilities/installed.py (modified)
- backend/settings.py (modified)
- backend/tests/test_scheduling_draft.py (new)
- backend/tests/test_settings.py (modified)
- backend/tests/test_capability_conformance.py (modified)
- backend/tests/architecture/test_execute_turn_boundaries.py (modified)
- backend/evals/golden/scheduling_draft/valid.json (new)
- backend/evals/golden/scheduling_draft/unresolvable-entity.json (new)
- backend/evals/golden/scheduling_draft/out-of-range-argument.json (new)
- backend/evals/golden/scheduling_draft/stale-version.json (new)
- backend/tests/test_evaluation_harness.py (modified)
- backend/agent/runtime.py (modified)
- backend/application/contracts/agent_runtime.py (modified)
- backend/tests/test_agent_runtime_adapter.py (modified)
- backend/application/contracts/activity.py (modified)
- backend/application/use_cases/execute_turn.py (modified)
- backend/tests/test_execute_turn_use_case.py (modified)
- backend/application/ports/proposal.py (new)
- backend/application/use_cases/finalize_agent_run.py (new)
- backend/application/use_cases/manage_proposal.py (new)
- backend/adapters/postgres/proposal.py (new)
- backend/migrations/versions/e9f0a1b2c3d4_add_reversible_proposals.py (new)
- backend/application/ports/conversation.py (modified)
- backend/adapters/postgres/conversation.py (modified)
- backend/adapters/postgres/schema.py (modified)
- backend/api/deps.py (modified)
- backend/api/routers/conversations.py (modified)
- backend/api/routers/proposals.py (new)
- backend/api/schemas.py (modified)
- backend/api/main.py (modified)
- backend/tests/test_conversation_contracts.py (modified)
- backend/tests/test_conversations_postgres.py (modified)
- backend/tests/test_postgres_schema.py (modified)
- backend/tests/test_proposal_persistence.py (new)
- backend/tests/test_evidence_binding.py (modified)
- backend/tests/architecture/test_conversation_boundaries.py (modified)
- frontend/openapi.json (generated)
- frontend/src/api/schema.d.ts (generated)
- frontend/src/api/proposals.ts (new)
- frontend/src/hooks/useProposal.ts (new)
- frontend/src/hooks/useReviseProposal.ts (new)
- frontend/src/hooks/useRejectProposal.ts (new)
- frontend/src/components/ui/separator.tsx (new)
- frontend/src/features/chat/DraftCard.tsx (new)
- frontend/src/features/chat/DraftCard.test.tsx (new)
- frontend/src/features/chat/ActivityTimeline.tsx (modified)
- frontend/src/features/chat/ActivityTimeline.test.tsx (modified)
- frontend/src/test/accessibility-contract.test.tsx (modified)
- _bmad-output/implementation-artifacts/3-1-create-and-revise-a-reversible-repair-draft.md (modified)
- _bmad-output/implementation-artifacts/deferred-work.md (modified)
- _bmad-output/implementation-artifacts/sprint-status.yaml (modified)
- evidence/story-1.11/gate-a-readiness-report.json (regenerated per AR28; not story-specific evidence)

## Change Log

| Date | Change |
|---|---|
| 2026-08-18 | Story created. Seven decisions and two honest gaps recorded; ledger routed (closes nothing, re-annotates `:172-176`, corrects the retro's Story 3.1 premise and two Story 2.7 premises). |
| 2026-08-18 | Implemented Task 1: application-owned RFC 8785 canonicalization and governed contract digests. |
| 2026-08-18 | Implemented Task 2: frozen reversible-proposal contract family and transport fixture. |
| 2026-08-18 | Implemented Task 3: governed scheduling-draft capability and policy wiring. |
| 2026-08-18 | Implemented Task 4: named draft output and untrusted/trusted outcome seam. |
| 2026-08-18 | Implemented Task 5: trusted draft binding, terminal wiring, visibility, and history rehydration. |
| 2026-08-18 | Implemented Task 6: governed proposal persistence and atomic draft finalization. |
| 2026-08-18 | Implemented Task 7: proposal reads, idempotent revisions, and terminal rejection. |
| 2026-08-18 | Implemented Task 8: four-case scheduling-draft evaluator coverage and NFR5/NFR28 classification. |
| 2026-08-18 | Implemented Task 9: generated proposal client surface and reviewable Draft card. |
| 2026-08-18 | Implemented Task 10: automated Draft accessibility and command-discontinuity proof. |
| 2026-08-18 | Completed Task 11 pre-Gate closure: hard fences, ledger corrections, full regression, Playwright, and migration drift check. |
| 2026-08-18 | Completed Task 11 and moved to review after Gate A passed with no blocking checks. |
