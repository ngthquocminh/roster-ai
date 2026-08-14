---
baseline_commit: 4e2b8126c9efd41ffc55fd9ac66d6c9b4710935f
---

# Story 2.7: Ground Schedule Claims in Exact Evidence

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want every schedule-specific answer tied to exact evidence,
So that I can verify the agent's facts instead of trusting a confidence score.

**This is the story every earlier Epic 2 story deferred its request path to.** Story 2.3 accepted
and persisted a turn but deliberately did not execute it. Story 2.5's Decision 1 composed the
governed capability *at the seam* and recorded the handoff by name:

> "Story 2.7 is the first story to execute a turn on a request path and inherits, together, the
> UPDATE grant + migration, the `agent_response` payload, `run_in_threadpool` for the synchronous
> `run_sync`, `create_agent_runtime()`'s missing live-model wiring, and translate.py's silent
> drops." (`sprint-status.yaml:164-168`, `2-5-…md`)

Story 2.6's own out-of-scope table names this story three times: grounding / `EvidenceRefV1`
emission / NFR12, and "Any HTTP route, `agent_run` state transition, migration"
(`2-6-…md:611-612`). `api/deps.py:98` already says it out loud: *"Story 2.7 puts the first agent
turn on a request path and finds the seam already shaped."*

**So this story does two things at once, and both are load-bearing:** it turns the assembled Epic 2
machinery into a working request, and it makes FR7/NFR12 true — no number reaches the planner that
the application did not compute itself, from an immutable version, with a locator attached.

**Unblocks:** Story 2.8 (evidence jump/return navigates the locators this story emits) and Story
2.9 (clarification/refusal are variants of the response shape this story defines).

Story 2.6 is `done` and green at this story's `baseline_commit` (`4e2b812`, `main`). Gate A is
`gate_a_passed: true`, `blocking: []`, bound to `00f8ae0`.

---

### Seven decisions were made at story creation — do not re-litigate them

#### Decision 1 — The turn executes on a **new explicit endpoint**. `POST /messages` stays byte-identical

Three shapes were considered. The two rejected ones both fail for structural reasons, not taste:

- **Execute inside `POST /messages`.** AD-22 fixes the accept-turn bundle at *message + agent-run +
  event* and Story 2.3's contract tests pin it. Folding a turn bounded by
  `agent_runtime_deadline_seconds` (default **60.0**, `settings.py:74`) into the acknowledgement
  path makes the accept latency the turn latency, and it makes `agent_queued` — the status Story
  2.3 required be rendered *literally* under UX-DR5 — a state nothing ever observes.
- **Acknowledge, then execute in a background task.** This is the tempting one, because Story 2.4
  built an SSE stream that would carry the response beautifully. It is forbidden: AD-18 says lease
  work from PostgreSQL with explicit concurrency and recovery, and Story 3.3 owns job leasing and
  fencing. A `BackgroundTasks` / thread-pool execution path is a job queue with no lease, no
  fencing epoch, and no recovery — invented here, replaced in Epic 3, and losing accepted work on
  every process restart in between.

**This story therefore adds ONE new command endpoint** under `/api/v1/conversations` that executes
an already-accepted, still-queued run and persists its outcome.

- **Mount under `/api/v1/conversations`, never `/api/v1/scenarios`.**
  `test_gate_a_mutation_audit.py:24-34` (`test_gate_a_scenario_openapi_surface_is_get_only`) filters
  `app.openapi()["paths"]` on the `/api/v1/scenarios` prefix and asserts each one's method set is
  exactly `{"get"}`. This is the same trap Story 2.3's Decision 1 documented; AR28 forbids a later
  gate weakening an earlier one, so editing that assertion is not available.
- **The `agent_run` state machine is the double-submit guard.** `agent_queued → agent_running →
  {agent_completed | agent_failed | agent_timed_out}`. A run not in `agent_queued` is refused with
  a stable problem response. **No idempotency key**: AD-8/AR8 scope keys to FR-12/16/18/19 and FR-7
  is not among them — the same reading Story 2.3 used to decide it needed none.
- `run_sync` is synchronous SQLAlchemy-adjacent work on the event loop's thread. It goes through
  `fastapi.concurrency.run_in_threadpool`, as `api/routers/conversations.py` already does for every
  SSE poll.
- **Two transactions, not one.** The accept bundle already committed in its own request. This
  endpoint opens a short site-scoped transaction to claim the run (`agent_queued → agent_running`),
  releases it for the duration of the turn, and opens a second to write the terminal status plus
  the `agent_response` event. Holding one open across a 60-second model call is precisely the
  connection-pool outage `api/deps.py:161-178` exists to prevent.

#### Decision 2 — The model never supplies a number that renders. **Application calculators produce the value through a governed tool**, and the gate verifies the citation

AD-11 (`ARCHITECTURE-SPINE.md:154`): *"Application calculators **produce or verify** every numerical
claim … against immutable snapshots."* Both branches are sanctioned. **This story takes the
`produce` branch.** FR-7's testable consequence (`prd.md:134`): *"every displayed KPI can be
recomputed from saved evidence, and an unsupported number fails the grounding gate."*

The run is constructed with a **strict structured output type** — a ShiftMind-owned
`GroundedAnswerV1` carrying prose segments and typed `ClaimProposalV1`s. A proposal **cites** a
metric result the application already computed; it never asserts a value.

1. The model calls `scheduling_compute` (Task 3) with a metric from the **closed vocabulary** and
   its arguments (task/family/window).
2. The capability computes against the pinned immutable scenario version, **paging to exhaustion**,
   and returns `{value, unit, evidence_refs, scenario_version_id, result_id}`.
3. The model composes its answer; each claim carries a `result_id`.
4. The gate **verifies the citation** — `result_id` is among this turn's tool results, the claim's
   arguments match the originating call's, the version matches the pin — and attaches the
   `EvidenceRefV1` locators the capability returned.

**Why the model does not assert its own value.** `scheduling_inspect` states it *"never computes a
metric"* (`scheduling_inspect.py:4`) and returns paged rows (`GroupQueryV1.limit` default **50**,
`scheduling_inspect_row_limit` cap **200**). A model asserting a total would routinely compute it
from the first page — Decision 4's trap, aimed at the model instead of the calculator. Under
assert-and-compare, mismatch becomes the **common** case, and a claim whose calculator value is
correct, evidenced, and version-pinned would render as a *failure*. AD-11 and AR11 (`epics.md:157`)
each name exactly three distinct failures — **missing**, **unauthorized**, **version-mismatched**.
*"The model's discarded arithmetic disagreed"* is not among them and is not promoted into one here.

**What the gate still falsifies** (AC1's failure clause remains provable): a fabricated `result_id`;
a `result_id` whose arguments do not match the claim; a result whose `scenario_version_id` differs
from the pin; and a claim with no citation at all. Each is a per-claim failure under Decision 6.
Exactly one calculation happens per metric — the capability's.

**VERIFIED AT CREATION against the installed pydantic-ai-slim 2.27.0** (executed, not read from
docs):

| Construction | `info.output_tools` | `allow_text_output` |
|---|---|---|
| `output_type=[str, DeferredToolRequests]` — today | `[]` | `True` |
| `output_type=[GroundedAnswerV1, DeferredToolRequests]` — this story | `['final_result']` | `False` |

And the fail-closed edge already works: a model that answers the strict agent in prose is retried
once, then raises `UnexpectedModelBehavior: Exceeded maximum output retries (1)`, which
`runtime.py:175-176` already maps to `AgentRuntimeError("agent runtime produced unusable output")`.
**An unstructured confident paragraph cannot reach the planner.** That is the outermost ring of the
grounding gate and it costs nothing to keep.

#### Decision 3 — Structured output is an **opt-in adapter parameter**, so every existing case and construction site keeps a byte-identical shape

This is the decision that stops the story from turning into a 40-file rewrite.

**VERIFIED:** at today's `output_type=[str, DeferredToolRequests]`, `info.output_tools` is **empty**
— the name `final_result` appears nowhere in this repository. Switching to a structured answer puts
a `ToolCallPart(tool_name='final_result')` **and** a `ToolReturnPart(tool_name='final_result')` into
`result.all_messages()`, and `agent/translate.py:169-177` + `:145-158` faithfully record both as an
owned `tool_call` part and a `tool_result` message. Three consequences follow, none of which fail
loudly:

1. `ToolRoutingEvaluator` (`evals/evaluators.py:40-46`) counts every assistant `tool_call` part —
   it would see `final_result` as a routed tool and fail every grounded case on count.
2. `runtime.py:308-318`'s `_tool_results(turn)` would gain a `final_result` entry, which is not a
   capability result.
3. `runtime.py:235`'s `output_text=str(result.output)` would become a dataclass `repr`.

So: `PydanticAIAgentRuntime.__init__` takes an **optional `answer_type`, defaulting to `None`**.
`None` reproduces today's construction exactly — the seven committed golden cases, the ~15
`PydanticAIAgentRuntime(...)` construction sites, and `evals/report.py` are untouched and must show
no behavioural change. When `answer_type` is supplied, the adapter owns all three consequences
above explicitly (a typed `answer` field on `AgentRunOutcomeV1`; the output tool excluded from
`tool_results`; `output_text` left `None` or set from the answer's prose — decide and test it, do
not leave it to `str()`).

#### Decision 4 — Calculators read through `ScenarioProjectionReader` and **must page to exhaustion**. A page is not a total

**This is the quietest trap in the story and it will not fail a test you would write yourself.**

`GroupQueryV1.limit` defaults to **50** (`ports/scenario_projection.py:35`) and
`scheduling_inspect_row_limit` caps at **200** (`settings.py:75`). A shortfall computed from the
first page of demand intervals is *a wrong number with a valid-looking evidence locator attached* —
the exact fabricated-context failure FR5 names and the fact-drift AD-4 exists to prevent. It is
strictly worse than no grounding at all, because the locator makes it look verified.

Every calculator must drain the group via `next_cursor` under an explicit bound and **raise rather
than truncate** when the bound is reached. `matching_count` and `total_count` are already on every
`*PageV1` — use them as the completeness assertion, not as decoration.

Second half of the same decision: **never re-derive facts from raw rows.** The adapter owns source
interpretation (AD-4); calculators consume `DemandIntervalV1` / `AssignmentV1` / `WorkerV1` /
`LockV1` / `ConstraintV1` and nothing beneath them. A calculator that reaches for SQL or for the
fixture JSON has become a second interpretation of source data, which is the trap Story 2.5's
creation note ranked second-quietest.

#### Decision 5 — `EvidenceRefV1` gains `schema_version`, and the two group vocabularies get **one** mapping

**(a) `schema_version`.** The spine's *Normative contract minimums* (`ARCHITECTURE-SPINE.md:314`)
say **every** contract carries `schema_version`. `EvidenceRefV1` does not
(`contracts/evidence_ref.py:29-41`) — it predates that rule being enforced, and until now it was
only ever a transient response shape. This story is the first to **persist** one, inside a durable
`agent_response` payload that Story 2.8 will later read back. Add the field.

`backend/tests/test_evidence_ref.py:66-78` pins the exact field **order**, and that file is a Gate A
check (`gate_a_checks.py:245`, `exact_evidence_target_resolution`, invariant
`normalized_scenario_reads`). Extending that assertion **strengthens** the invariant — it goes from
pinning eleven fields to pinning twelve — so AR28's "later work may not weaken any passed
invariant" is satisfied. Record the rationale in the story; do not quietly edit the assertion.

**(b) The mapping.** There are two group vocabularies and they are not the same:

| `EvidenceGroupV1` (`evidence_ref.py:18-25`) | `ScenarioFactGroupV1` (`ports/scenario_projection.py:27-29`) |
|---|---|
| `work-areas-and-tasks`, `workers`, `demand`, `baseline-assignments`, `locks`, `constraints-and-objectives` | `overview`, `tasks`, `workers`, `demand`, `assignments`, `locks`, `constraints` |

The first is the planner-facing Scenario Data group (what an Evidence link must *name*, UX-DR8); the
second is the read port's group. Define the mapping **once**, and assert it exhaustive in **both**
directions — a `Literal` member added to either side without the other must go red. Two ad-hoc
`if group == …` translations in the calculator and the renderer is how an Evidence link ends up
naming a group the planner cannot find.

#### Decision 6 — Failure is **per claim**, is a persisted state, and never retargets

AC3: *"the failure remains distinct and inspectable, safe saved content is preserved, and the agent
does not target another row or version."*

A grounded response may carry supported and failed claims **in the same message**. The failed claim
keeps its position and renders as its own distinct state naming which of AR11's three causes
applied — **missing**, **unauthorized**, **version-mismatched** — which are required to stay
distinct (`ARCHITECTURE-SPINE.md:154`, EXPERIENCE.md:165-171). The surviving claims keep their
evidence and their links. The response is not discarded.

The non-retargeting rule needs a **test, not a sentence**: assert that a claim whose locator does
not resolve in the cited version produces a failure, and that no `EvidenceRefV1` is emitted naming a
different `record_id` or a different `scenario_version_id`. "We don't do that" is not a control.

UX-DR5 fixes the copy and UX-DR32 fixes the visual treatment: no confidence score, no gauge, no
"approximately", no hedged number, no AI glow, no pulsing evidence. A number is computed and linked,
or it is a named failure. There is no third register.

#### Decision 7 — `agent_response` becomes a real `ActivityItemV1` variant. The other six discriminants stay reserved

`ActivityItemV1` is currently **flat**, with `message_id` and `text` both required
(`contracts/activity.py:31-40`) — shaped for `planner_message` alone, exactly as Story 2.3
documented. `adapters/postgres/conversation.py:281-286` raises `UnsupportedActivityPayloadError` for
any other `activity_type`, and `api/schemas.py:121-136`'s `ActivityItemOut` mirrors the flat shape.

Making `agent_response` real is a five-point change and every point is required by AC2/AC3: the
contract variant (AD-20's row: *"agent response = visible summary/evidence refs"*), the writer
(`_payload_to_json`), the reader (`_activity_from_payload`), the transport (`ActivityItemOut`), and
the renderer (`ActivityTimeline`).

**Ship exactly one new discriminant.** `clarification` is Story 2.9's, `draft` and `run_progress`
are Epic 3's, `comparison`/`approval_request` are Epic 4's. Defining a payload shape for a
discriminant this story cannot exercise is the "vocabulary that claims unproven authority" move
Story 2.3's Decision 3 and Story 2.2's risk-class handling both deliberately avoided.

The SSE reader must stay forgiving in the same direction it already is: an event type this reader
predates still ends the connection cleanly (`conversations.py:216-219`), never a partial frame.

---

## Acceptance Criteria

Restated verbatim from `epics.md:769-790`.

**AC1.** **Given** an agent response with a numerical or schedule-specific claim
**When** the response is validated for display
**Then** application calculators recompute the claim against immutable scenario/schedule/run
versions and attach one or more `EvidenceRefV1` locators
**And** unsupported or version-mismatched numbers fail the grounding gate rather than rendering
confidently. (FR7, NFR12, AR11)

**AC2.** **Given** a grounded visible response
**When** Chat renders it
**Then** each supported claim has an adjacent, conventionally identifiable Evidence link naming the
exact group, record, field/range, and version
**And** a generic message-level Sources link or confidence score is insufficient. (UX-DR5, UX-DR8,
UX-DR32)

**AC3.** **Given** evidence, calculation, or authorization failure for one claim
**When** the response outcome is persisted
**Then** the failure remains distinct and inspectable, safe saved content is preserved, and the
agent does not target another row or version
**And** the evaluation fixture records the expected evidence IDs and oracle result. (AR11, NFR27)

---

## One honest gap, raised for review rather than papered over

**AC1 says "immutable scenario/**schedule/run** versions". No schedule or run version exists yet.**

Verified by exhaustive search at creation: there is no `schedule_run`, `schedule_version`, or
baseline-pointer table anywhere under `backend/migrations/`; `RunSnapshotV1`, `ScheduleVersionV1`,
`MetricSetV1`, and `ConstraintResultV1` are named in AD-20 but exist nowhere in
`application/contracts/`. Epic 3 builds all of it. `EvidenceRefV1` already anticipates this with two
optional fields (`producing_run_version: str | None`, `baseline_schedule_version: str | None`).

**Required posture, and it is not "leave them null and say nothing":**

- `producing_run_version` stays `None` for every locator this story emits. There is no run. Do not
  synthesize one, and do not repurpose `agent_run_id` — a scheduling run version and an agent run
  are different aggregates (AD-22).
- `baseline_schedule_version` is populated **when the fixture supplies one**:
  `ScenarioOverviewV1.baseline_schedule_version` (`contracts/scenario_projection.py:33`) already
  carries it. Read it from the pinned overview; do not leave a real available binding empty.
- Record the reduction in the `SCOPE_CONTROLS`-style "NOT COVERED" form Story 2.5 established
  (`scheduling_inspect.py:36-60`), naming Epic 3 as the owner, so the claim cannot outlive its
  enforcement.

The same posture applies to `EvidenceSnapshot` and `AuditEnvelopeV1`: AD-12 gives evidence snapshots
their own aggregate, and **neither exists under `backend/` today** — Story 2.6 raised exactly this
gap and was held to *declaration only*. This story is held to the same level. The checksum trio on
`EvidenceRefV1` (`checksum_algorithm` / `checksum_schema_version` / `checksum_digest`) is real and
resolvable from `ScenarioOverviewV1` — bind it from there. Building an evidence-snapshot writer or
an audit-envelope emitter here pre-empts Epic 4 and puts an ungoverned second implementation in the
repo before its governing contract exists.

---

## Tasks / Subtasks

**This story runs in three phases with a reporting gate between A and B.** It remains ONE BMAD story
— the phases are ordering plus a decision point, not a split. The boundary is placed where the only
clean split *would* be, so that if Phase A overruns, splitting becomes a decision taken with real
numbers rather than a guess made before any code existed.

| Phase | Tasks | Delivers | Needs a route? |
|---|---|---|---|
| **A — Grounding at the seam** | 1–6 | AC1 in full, plus AC3's evaluation-fixture clause | No |
| **CHECKPOINT** | — | commit, report five numbers, apply the continue rule | — |
| **B — Request path and rendering** | 7–13 | AC2, plus AC3's persistence clause | Yes |
| **C — Close-out** | 14 | regression, fences, Gate A | — |

Phase A is testable end to end **without a route, without a migration, and without a frontend
change** — the same seam-level shape Story 2.5 proved. Do not start Phase B early because a Phase A
task is blocked; report the blockage at the checkpoint instead.

*("Checkpoint" here is the phase boundary. It is unrelated to **Gate A**, the AR28 readiness gate in
Task 14, and to the **grounding gate** in Task 4.)*

---

## Phase A — Grounding at the seam (Tasks 1–6)

### Task 1 — `EvidenceRefV1` gains `schema_version`; the group vocabularies get one mapping (AC: 1)

- [x] Add `schema_version: str = SCHEMA_VERSION` to `EvidenceRefV1` with a module-level
      `SCHEMA_VERSION = "1"`, matching `contracts/stream_cursor.py`'s house style.
- [x] Extend `backend/tests/test_evidence_ref.py:66-78`'s field-order assertion to twelve fields.
      Add a one-line comment naming the spine's *Normative contract minimums* as the reason, so a
      future reader does not mistake it for churn.
- [x] Add the `EvidenceGroupV1 ↔ ScenarioFactGroupV1` mapping in exactly one module.
- [x] Test: the mapping is exhaustive in both directions, derived from `typing.get_args` on both
      `Literal`s — not from a hand-copied list. Adding a member to either side without the other
      must fail.
- [x] Boundary: `overview` has no planner-facing evidence group. Decide and assert what the mapping
      does with it (omit it explicitly; do not let it fall through to a `KeyError` at claim time).

### Task 2 — Grounding contracts (AC: 1, 3)

- [x] New `backend/application/contracts/grounding.py`, house style per `stream_cursor.py`: `from
      __future__ import annotations`, `SCHEMA_VERSION = "1"`, frozen dataclasses only, `V1` suffix
      on every type including `Literal` aliases, a docstring that explains *why the shape is this
      shape* with AD numbers, explicit `__all__`.
- [x] `MetricV1` — the **closed** metric vocabulary (Task 3 fixes the members). It lives **here, in
      contracts**, and Task 3's capability imports it: `capability_manifest.py`'s docstring fixes the
      dependency direction as *capabilities → contracts*, and inverting it for a vocabulary would put
      an application contract behind a capability module.
- [x] `ClaimProposalV1` — what the model proposes: metric, arguments, and the **`result_id` it
      cites**. It carries **no value**: under Decision 2 the value is the capability's, and a field
      the model could fill with a number is a field that will eventually render one.
- [x] `ClaimProposalV1` is **untrusted model output** — say so in the docstring, as
      `AgentToolCallProposalV1`'s already does for tool names. The citation is the untrusted part
      now: a `result_id` is a claim *about* provenance, not proof of it, and Task 4 is what makes it
      proof.
- [x] `GroundedAnswerV1` — the strict output type: ordered segments of prose and claim proposals.
- [x] `GroundingFailureV1` — one of `missing_evidence`, `unauthorized_evidence`,
      `version_mismatch`, `calculation_failed`, `uncited_claim`, as a `Literal`. AD-11
      (`ARCHITECTURE-SPINE.md:154`) and AR11 (`epics.md:157`) each name exactly **three** causes —
      missing, unauthorized, version-mismatched — and those three must stay distinguishable and must
      not be collapsed.
- [x] The last two are this story's own additions and are **mechanical, not evaluative**:
      `calculation_failed` is the capability raising (truncation, budget, timeout), and
      `uncited_claim` is a claim node with no `result_id` or a bare numeral found in a prose segment
      (Task 4). **Neither is a judgement about whether a number "looks right"** — there is no failure
      type meaning *"the model's arithmetic disagreed"*, because under Decision 2 the model performs
      no arithmetic.
- [x] `GroundedClaimV1` — computed value, unit, `tuple[EvidenceRefV1, ...]`, and either a supported
      verdict or a `GroundingFailureV1`.
- [x] `GroundedResponseV1` — the persisted, planner-visible result: segments, claims, and the
      pinned `scenario_version_id`.
- [x] Nothing in this module imports `fastapi`, `pydantic_ai`, or `sqlalchemy`.
      `tests/architecture/test_agent_runtime_boundaries.py:380-394` parametrizes contract modules by
      name "so a future refactor that deletes them fails loudly" — **add this module to that list**.

### Task 3 — Application calculators, exposed as the `scheduling_compute` capability (AC: 1)

- [x] New `backend/application/grounding/calculators.py` (the spine names a "grounding service" at
      `ARCHITECTURE-SPINE.md:436`; this is it).
- [x] Ship a **small, real, closed** metric set that answers the primary Wednesday investigation
      question (`epics.md:734-737`, EXPERIENCE.md:253). Suggested and sufficient:
      required demand minutes for a family/task in a window; staffed minutes from baseline
      assignments in the same window; the shortfall between them; count of workers qualified for a
      task. Four is enough — do not invent a fifth to look complete.
- [x] Each calculator returns value + unit + the `EvidenceRefV1`s of the records it actually read.
      A locator for a record the calculation did not consume is a false citation.
- [x] **Page to exhaustion** (Decision 4). Drain via `next_cursor` under an explicit bound; assert
      completeness against `matching_count`; **raise** on truncation.
- [x] Test that fails on truncation: a stub reader holding more rows than one page, asserting the
      computed total covers every row. Then confirm the test is non-vacuous by checking it goes red
      against a single-page implementation.
- [x] Consume only `application/contracts/scenario_projection.py` records. No SQL, no fixture JSON,
      no re-derivation (AD-4).
- [x] Units are explicit and asserted. `AssignmentV1`/`DemandIntervalV1` carry **integer minutes**
      (AD-20's half-open `[start_minute, end_minute)`); "worker-hours" in planner copy is a
      presentation conversion at one boundary, and mixing the two is a wrong number that renders
      confidently.
- [x] Half-open interval overlap is the arithmetic here. Test the boundary cases explicitly:
      touching-but-not-overlapping (`a.end == b.start`), fully contained, partial on each side.
- [x] New `backend/application/capabilities/scheduling_compute.py`, in `scheduling_inspect.py`'s
      exact shape: `CAPABILITY_NAME`, typed error classes with `code`, a module-level `ERROR_CODES`,
      `SchedulingComputeRequestV1` / `SchedulingComputeResultV1`, a `SCOPE_CONTROLS` mapping, and a
      manifest factory that imports `default_settings` **inside** the function (`application/**`
      stays importable without process configuration).
- [x] The handler delegates to `application/grounding/calculators.py` — it does not compute. This
      mirrors `scheduling_inspect`, whose handler delegates to `use_cases/read_scenario_facts.py`.
- [x] `risk_class="inspect"`, **not `"compute"`**. AR5's `compute` class is the solver — PRD §4.8 #3,
      *"start bounded CP-SAT optimization"*, which Epic 3 owns. A read that derives a total changes
      nothing and must not claim solver-grade authority. Its own `required_feature_policy`
      (`scheduling_compute_enabled`), mirroring `scheduling_inspect_enabled`.
- [x] Register in `installed.py`'s `_INSTALLED_FACTORIES` — one line, per that module's *"One line
      per governed capability"* rule. Duplicate-name and manifest validation are already enforced
      there.
- [x] **`scheduling_inspect` shows a zero-line diff.** Its docstring's *"This capability never
      computes a metric"* stays true, and Story 2.5's boundary is preserved rather than quietly
      widened.
- [x] `result_id` is **derived, not random**: the RFC 8785 canonical-JSON SHA-256 hash of
      `(metric, canonical arguments, scenario_version_id)` — the hashing convention AR20 already
      fixes for this repository.
- [x] **Why this is load-bearing and not a detail:** golden cases drive a deterministic model double
      whose turns are *authored* (`ScriptedModelTurn`). A scripted turn must be able to **cite a
      `result_id` written into the case file**. A per-call UUID would make every grounded case
      unwritable, and the failure would surface late — after Task 6's cases are already being
      authored. A content hash is stable across runs, so a case file can name it. Same reasoning as
      the existing rule that `expected_evidence_refs` must carry no per-run UUID.
- [x] Test: two identical calls in one turn yield the same `result_id`; calls differing only in
      window or metric yield different ones.
- [x] `SchedulingComputeResultV1` is a **capability result**, not `MetricSetV1`. AR20 names
      `MetricSet` as its own contract and the *honest gap* section assigns it to Epic 3. Do not name,
      shape, or import this type as if it were that one.

### Task 4 — The grounding gate (AC: 1, 3)

- [x] New `backend/application/grounding/gate.py`. Input: a `GroundedAnswerV1` plus trusted deps.
      Output: a `GroundedResponseV1`.
- [x] Input gains this turn's **capability results**, keyed by `result_id`. The gate performs **no
      computation** — Decision 2 puts the single calculation in Task 3's capability, and a second one
      here would reintroduce exactly the divergence this design removes.
- [x] For each `ClaimProposalV1`, in order, stopping at the first failure:
      1. `result_id` present and found among this turn's results → else `uncited_claim` /
         `missing_evidence`;
      2. the claim's metric and arguments equal the originating call's → else `missing_evidence`.
         **This check is not optional bookkeeping:** a result computed for Thursday, cited on a claim
         about Friday, carries a real value and real locators attached to the wrong question, and
         nothing else in the system would notice;
      3. `result.scenario_version_id` equals the **pinned** version from trusted deps — never one
         carried on the proposal → else `version_mismatch`;
      4. attach the locators **the capability returned**. The gate never derives a locator; only the
         calculator knows which records it read.
- [x] Version mismatch reuses `scheduling_inspect.py:228-237`'s shape — do not invent a second
      convention.
- [x] **A prose segment containing a decimal digit fails the answer.** Without this the grounding
      invariant is not actually total: the model can write *"you're short about two hours"* in prose,
      bypass every claim node, and render an ungoverned number with no locator. No other task closes
      this hole.
- [x] The rule is **blunt on purpose**: reject any Unicode decimal digit in a prose segment,
      fail-closed. Every number the answer needs is a claim node, and the renderer draws windows and
      identifiers from claim arguments rather than from prose.
- [x] If Task 6's authored cases show this is too strict to write natural prose against, the
      relaxation must be a **declared allow-list with its own test** (and a comment naming what it
      admits and why) — never a quiet widening of the pattern. Record it in `SCOPE_CONTROLS` either
      way.
- [x] **Never retarget.** Test: a claim whose record does not resolve in the cited version fails,
      and no emitted `EvidenceRefV1` names a different `record_id` or `scenario_version_id`.
- [x] Test: one failed claim among three leaves the other two supported, with their evidence intact
      (AC3's "safe saved content is preserved").
- [x] Record the coverage reduction as a `SCOPE_CONTROLS`-style `Mapping[str, str]` where every
      value states what the control covers **and** what it does `NOT COVER`, asserted by a test —
      the `scheduling_inspect.py:36-60` pattern. Include the schedule/run-version gap from the
      *honest gap* section here.

### Task 5 — Opt-in structured answer on the adapter (AC: 1)

- [x] `PydanticAIAgentRuntime.__init__` accepts `answer_type: type | None = None`. `None` must
      reproduce today's construction **exactly**.
- [x] When supplied, construct `output_type=[answer_type, DeferredToolRequests]` — strict, no `str`
      (verified: `allow_text_output` becomes `False`, which is the fail-closed edge in Decision 2).
- [x] `AgentRunOutcomeV1` gains a typed optional `answer` field. Do not smuggle the answer through
      `output_text` as a `repr`.
- [x] Exclude the framework output tool from `_tool_results(turn)` (`runtime.py:308-318`).
      **Derive the name** from the agent's own output-tool set rather than hardcoding
      `"final_result"` — a hardcoded framework name in an owned adapter is the AD-19 leak this
      package exists to prevent.
- [x] Test: with `answer_type=None`, an existing golden case produces a byte-identical
      `AgentRunOutcomeV1` to today's. This is the regression fence for Decision 3.
- [x] Test: a strict-answer run whose model emits prose raises `AgentRuntimeError`, cause preserved.
- [x] `application/**` gains no `pydantic_ai` import. The answer type is an application contract
      passed *in*; the framework wiring stays in `backend/agent/`.

### Task 6 — The grounding evaluator and its golden cases (AC: 3)

- [x] New `GroundingEvaluator` implementing the existing `Evaluator` Protocol
      (`evals/evaluators.py:27-30`) — the extension point Story 2.2 shipped for exactly this.
      Story 2.2's Task 3 forbade a second evaluator and named Story 2.7 as the owner of this one.
- [x] It asserts `case.expected_evidence_refs` against the emitted locators **and** the oracle
      result (AC3's two clauses). `expected_evidence_refs` exists on `GoldenCase` (`cases.py:64`)
      and is currently **evaluated nowhere in the repository** — `deferred-work.md:115` names this
      story as the owner that closes the grounding half. Close that half; the visible-state half
      stays open and belongs to Story 2.9.
- [x] Choose and document the locator's stable string form for `expected_evidence_refs`. It must not
      contain a UUID that changes per test run, or the cases are unmaintainable.
- [x] Contribute golden cases with **non-empty** `expected_evidence_refs`, one per verified path: one
      **supported** claim; one **version-mismatch** (result carries a version other than the pin);
      one **missing-evidence** (the scripted turn cites a `result_id` no call produced); one
      **argument-mismatch** (a real result cited on a claim whose window or metric differs from the
      originating call — the failure Task 4 exists to catch, and the only one that would otherwise
      render a true number against the wrong question).
- [x] Each scripted turn cites a `result_id` **written literally into the case file**. Task 3's
      content-hash derivation is what makes that possible; if a case cannot be authored because the
      id is unpredictable, that is Task 3 regressing, not a case-authoring problem.
- [x] **Tag them `capability="scheduling_compute"`** — that is the tool they route (Task 3). Add
      `"scheduling_compute"` to `MVP_PRODUCT_CAPABILITIES` (`test_evaluation_harness.py:316`) as a
      **product** capability: it is item #1 of PRD §4.8's catalogue (*"inspect the selected scenario,
      including … coverage … evidence"*), so it is not exempt like `demonstration`.
      `test_every_capability_meets_the_nfr28_four_case_floor` is **designed** to fail on an
      unclassified capability; making it pass by classification is the intended path, not a
      workaround.
- [x] NFR28's *"≥4 per allowed capability"* is met by exactly the four cases above — **at the floor,
      deliberately**. `epics.md:1527` forbids padding. A reviewer removing one of the four takes the
      capability below the floor, and that test is what says so.
- [x] The new manifest's `evaluation_fixtures` names these four case files by path, as
      `scheduling_inspect`'s does. `generate_demonstration_report` runs every committed case and
      raises on an uninstalled capability (`report.py:186-189`) — Task 3's `installed.py`
      registration is what keeps it green.
- [x] `GroundingEvaluator` remains a **second evaluator**, now over `scheduling_compute`:
      `ToolRoutingEvaluator` keeps judging routing, and grounding is judged separately. Story 2.2's
      "no second evaluator until 2.7" fence is satisfied by adding exactly one.
- [x] **Do not pad toward NFR28's 50-case Gate B aggregate** (`epics.md:1527`). Contribute what the
      ACs need.
- [x] Extend `backend/evals/README.md` with a Story 2.7 paragraph in the existing style.
      `test_readme_documents_exact_contribution_shape_and_owners` (`:374-379`) reads that file —
      check which literals it pins before editing.
- [x] **Do not regenerate** `evidence/story-2.2/evaluation-harness-demonstration.json`. Story 2.5 and
      2.6 both recorded this rule; the file is frozen and pins case files by path and sha256.
- [x] `generate_demonstration_report` must still pass with the new cases present
      (`report.py:84-117`). It runs every committed case; a case naming an uninstalled capability
      raises by design (`:186-189`).

---

## CHECKPOINT — commit Phase A and report, then apply the continue rule

**This is a reporting gate, not an unconditional pause.** At this point AC1 is satisfied in full and
nothing yet depends on a route, a migration, or the frontend — which makes this the one moment where
splitting the story would cost nothing. The point is to *have that option priced* before Phase B
makes it expensive, not to stop work by default. An unattended run continues through it unless one
of the four named conditions below fires.

**This story stays ONE story.** Phases are ordering and a decision point inside it — one
`sprint-status.yaml` entry, one story file, one code review, one Gate A run. Splitting into two
BMAD stories was considered at creation and rejected: it costs a correct-course run against
`epics.md` and yields two stories each satisfying a fraction of the ACs. The phase boundary exists
so that decision *can* be revisited with evidence, not because it has been taken.

- [x] Commit Phase A as its own coherent commit. Phase A must be green on its own: full backend
      suite, `test_evaluation_harness.py`, and the new grounding suites.
- [x] Report these five things, as numbers, not adjectives:
      1. Which metrics shipped in the closed vocabulary, and which the ACs turned out not to need.
      2. **Whether the paging test is non-vacuous** — state that it was run against a single-page
         implementation and observed RED. Trap #1 is the whole reason this checkpoint exists; a
         paging test that was never seen to fail proves nothing.
      3. How many golden cases were contributed, by outcome type, and confirmation that
         `test_every_capability_meets_the_nfr28_four_case_floor` is still green.
      4. Anything in the *honest gap* section that turned out to be wrong when met in code.
      5. Elapsed effort on Phase A versus the estimate, and the revised estimate for Phase B.
- [x] **Then apply the continue rule.** This checkpoint is a *reporting gate*, not an unconditional
      pause — it must work in an unattended `bmad-dev-auto` / `bmad-loop` run as well as an
      interactive one. Continue straight into Phase B **unless** one of these is true, in which case
      **halt and escalate**:
      1. The paging test was never observed RED against a single-page implementation. This is
         non-negotiable: trap #1 produces a wrong number wearing a valid evidence locator, and an
         unverified guard against it is the single worst outcome available in this story.
      2. Phase A took more than roughly twice its estimate, or Phase B's revised estimate exceeds
         what remains.
      3. Something in the *honest gap* section turned out to be wrong in code — the schedule/run
         version posture in particular.
      4. Any AC1 behaviour could not be satisfied at the seam and appears to need a route.
- [x] **What halting means:** Phase A is already a coherent, acceptable deliverable — it satisfies
      AC1 in full plus AC3's evaluation-fixture clause. So the escalation is a real question with a
      real option: keep this story at Phase A and move Tasks 7–14 into a new story, or extend. That
      decision is the human's and needs the numbers above; do not take it unilaterally, and do not
      start Phase B merely to avoid raising it.

---

## Phase B — Request path and rendering (Tasks 7–13)

### Task 7 — `create_agent_runtime()` wires a real model (AC: 1) — closes `deferred-work.md:102`

- [x] `AgentRuntimeConfig.model` / `.api_key` are currently stored and never read; `self._model` is
      only ever set by the constructor kwarg. Wire them into a real PydanticAI model.
- [x] Keep the injected-`model` seam intact and winning: every existing test supplies a
      `FunctionModel` double and must keep working unchanged.
- [x] `AGENT_RUNTIME_MODEL` defaults to `"test"` (`settings.py:175`). Decide what that resolves to
      and make it explicit — a default that silently constructs a network-capable client is how a
      keyless CI run starts making live calls. `models.ALLOW_MODEL_REQUESTS = False` in the eval
      harness protects the harness, not the API.
- [x] Close the ledger entry with a note naming the commit.
- [x] **Do not** add a live-provider test. `deferred-work.md:106`'s unwrapped-transport-exception
      item stays open and needs live coverage that NFR26 keeps out of normal CI.
- [x] **Re-annotate `deferred-work.md:106` in place — do not carry it forward silently.** That item
      asks whether a raw `httpx`/`openai`/`google-genai` exception could cross the seam unwrapped
      past `except AgentRunError`. It was written when *no endpoint called `create_agent_runtime()`*,
      so the question was theoretical. This task makes a real provider client reachable from a real
      request for the first time: **the item does not close, but its exposure changes from
      hypothetical to live-and-untested.** Record that, following the in-place re-annotation
      precedent Stories 2.4 and 2.5 set for a changed premise, and restate the owner as the first
      story that adds live-provider coverage.

### Task 8 — A capability timeout stops being a retryable argument error (AC: 1) — closes `deferred-work.md:5`

- [x] `SchedulingInspectError`'s base `code` is `invalid_query`
      (`scheduling_inspect.py:63-67`), and `retryable_error_codes = frozenset({"invalid_query"})`
      (`:273`). The timeout overrun at `:222-226` raises the **base** class, so it reaches the model
      as `ModelRetry("invalid_query: inspection exceeded the 5.0s budget")`. The model "fixes"
      arguments that were never wrong, reissues the same slow query, and burns the wall-clock budget
      the timeout existed to protect.
- [x] Give the overrun its own non-retryable code, declared in `ERROR_CODES` and therefore in the
      manifest. `runtime.py:192-196` already rejects any code absent from a granted manifest, so a
      typo fails loudly.
- [x] Check `DemonstrationError` for the same generic-base-with-a-retryable-code shape and fix it if
      present — the ledger entry names it explicitly.
- [x] Test: a timed-out capability call produces a terminal failure, not a retry loop.
- [x] The ledger names Story 2.7 as an owner because this story creates the request path that can
      observe the loop. Close it.

### Task 9 — Migration: `UPDATE (status)` on `agent_run` (AC: 3)

- [x] New Alembic revision on top of `a4f92d7c8e31`. `GRANT UPDATE (status) ON agent_run TO
      shiftmind_runtime` — column-scoped, mirroring `GRANT UPDATE (resource_version) ON conversation`
      (`a4f92d7c8e31_add_durable_conversations.py:100`). Nothing else.
- [x] The `downgrade()` revokes it, matching `:104`.
- [x] **No new columns.** The terminal reason and evidence live in the `agent_response` activity
      payload (AD-20's `ActivityItemV1` row). Adding `failure_reason`/`completed_at` to `agent_run`
      duplicates that record in a second place with no acceptance benefit.
- [x] The existing `ck_agent_run_status` CHECK already admits all seven AD-7 statuses
      (`schema.py:306`) — do not touch it.
- [x] **A migration is safe for existing evidence, verified:** Story 1.11's review made the
      `schema_version` audit rule *monotone* (`evidence_binding.py:610-621` — the recorded revision
      must lie on the migration chain, not equal head). The six committed evidence files stay valid.
      This is why Story 2.5's Decision 1 objection to a migration no longer applies.
- [x] Extend `test_postgres_schema.py` / `test_identity_role_boundaries.py` in their existing shape:
      the runtime role can update `status` and still **cannot** update any other `agent_run` column,
      and still cannot `DELETE`.
- [x] `uv run --project backend alembic check` from the **repository root** — not from `backend/`;
      `deferred-work.md:117-126` records exactly that mistake and its cost.

### Task 10 — `agent_response` becomes a real activity variant (AC: 2, 3)

- [x] Make `ActivityItemV1` discriminated. `planner_message`'s serialized payload must stay
      **byte-identical** — `_payload_to_json` (`conversation.py:266-278`) writes rows that are
      already committed in developer databases and pinned by
      `test_conversation_contracts.py`/`test_conversations_postgres.py`.
- [x] `agent_response` payload per AD-20: visible summary + evidence refs. Concretely: the
      `GroundedResponseV1` segments, each claim's computed value/unit/verdict, and its
      `EvidenceRefV1[]`.
- [x] Writer and reader: extend `_payload_to_json` and `_activity_from_payload`. An unknown
      `activity_type` must still raise `UnsupportedActivityPayloadError` (`:281-286`) — the closed
      vocabulary keeps its teeth.
- [x] `ActivityItemOut` (`api/schemas.py:121-136`): `message_id` and `text` are currently required
      and are `planner_message`-only. Make the variant explicit in the published schema rather than
      loosening both fields to optional and letting the discriminant become advisory.
- [x] `sequence` stays a **JSON string** on every variant. Story 2.3's trap: a JSON number becomes an
      IEEE-754 double in the browser and poisons Story 2.4's resume cursor.
- [x] **`test_an_unrenderable_activity_variant_fails_typed_not_as_a_key_error`
      (`test_conversations_postgres.py:519-544`) uses `agent_response` as its unrenderable probe**
      and will go red the moment this story makes it renderable. Re-point it at a discriminant that
      is *still* reserved — `comparison` and `approval_request` are Epic 4's and safest — and update
      its docstring from "Seven of AD-20's eight discriminants" to six. Do **not** delete it: it is
      the only proof that an unknown payload fails typed instead of taking the timeline down with a
      `KeyError`-turned-500. The sibling at `:507-516` probes `draft` and stays green untouched.
- [x] Regenerate the published contract with the existing scripts — `npm run codegen:export` then
      `npm run codegen:types` (`frontend/package.json:15-16`). Do not hand-edit `frontend/openapi.json`
      or `frontend/src/api/schema.d.ts`.
- [x] Test: an `agent_response` event round-trips write → read → `ActivityItemOut` → SSE frame with
      its evidence refs intact, through the **same** `_activity` projection the timeline uses
      (`conversations.py:95-101`) — a frame and a timeline item that drift apart break the client's
      merge silently.

### Task 11 — The execute-turn use case and endpoint (AC: 1, 3)

- [x] New `backend/application/use_cases/execute_turn.py`, in the shape of `accept_turn.py`.
- [x] Claim the run: `agent_queued → agent_running` under `FOR UPDATE` on the RLS-filtered row,
      mirroring `accept_turn`'s serialization (`conversation.py:179-190`). A run in any other status
      is refused with a stable problem response and **no** side effect.
- [x] Compose `CapabilityGrantContextV1` and call `compose_granted_capabilities` through the
      **existing** `get_capability_registry` seam (`api/deps.py:93-101`). Grant is composed
      **before** the runtime is constructed; an ungranted capability is absent, never
      present-and-refusing (AD-2, Story 2.5 Decision 4).
- [x] Build `AgentDepsV1` from trusted server-owned values only (`capabilities/deps.py`). Distinct
      UUIDs per identity field — sharing one made every scope assertion vacuous; that was Story 2.5
      review finding 8.
- [x] `run_in_threadpool` around `run_sync`. The site-scoped transaction is **not** held across it
      (Decision 1).
- [x] Route: `POST` under `/api/v1/conversations`. **Verify** `test_gate_a_mutation_audit.py` stays
      green — mounting under `/api/v1/scenarios` turns it red.
- [x] Persist in one short second transaction: terminal `agent_run.status` + the `agent_response`
      persisted event at the next `sequence`, with `resource_version` bumped exactly as
      `accept_turn` does.
- [x] A runtime failure (`AgentRuntimeError`, `timed_out`, `budget_exhausted`) still reaches a
      **terminal** `agent_run` status and leaves the accepted conversation history durable. Keep
      this minimal: the full failure taxonomy and its visible states are **Story 2.9's** AC3, not
      this story's. Do not build a refusal or clarification variant here.
- [x] Test: two concurrent executions of one queued run produce exactly one terminal transition and
      one `agent_response` event.
- [x] Test: the endpoint requires an authenticated session and is site-scoped; a cross-site
      conversation is a non-disclosing 404, unchanged from Story 2.3.

**Two mechanical guards, because traps #7 and #8 otherwise rest on nothing but Decision 1.** Story
2.6 faced the same problem — a rule stated only in prose that no functional test could catch — and
solved it with source-level assertions (the `_RENDERERS` check and the `importlib`/`pkgutil` ban).
Do the same here. A rule with no guard is a comment.

- [x] **Guard for trap #7:** a test asserting the execute route's dependency set does **not** include
      `get_site_context`. Read it off the route's own signature or FastAPI's `dependant`, not off a
      hardcoded string. This is exactly the failure Story 2.4's Decision 1 described in prose and
      never guarded: correct at 40 ms, a connection-pool outage at 60 s.
- [x] **Guard for trap #8:** an architecture test banning `BackgroundTasks`, `asyncio.create_task`,
      and `ThreadPoolExecutor` under `backend/api/**` and `backend/application/**`. Carry ONE
      documented allow-list entry for `backend/services/run_service.py`, which legitimately holds a
      `ThreadPoolExecutor` for the legacy SQLite solve path — the `ALLOWED_LEAKS` pattern, including
      its companion test that the allow-listed entry **still exists and still matches**, so a
      half-fix goes red instead of silently widening the ban's blind spot.

### Task 12 — Conversation history is rehydrated from the persisted timeline (AC: 2) — closes `deferred-work.md:107`

> **Required, and not negotiable at implementation time.** No AC names it, but Epic 2 is titled
> *Grounded Conversational Investigation* and AC2 renders into a conversation timeline: without this
> task every message is an isolated single-turn run, so the second question a planner ever asks —
> the follow-up — cannot resolve against the first. The product's central noun would be false.
> `deferred-work.md:107` also names its owner as *"the first story that persists an `AgentTurnV1`
> and rehydrates it"*, and this is that story. It is ~30 lines and one test.

- [x] Build `AgentTurnRequestV1.history` from the conversation's **persisted `ActivityItemV1`
      timeline** — planner message text as `user`, prior `agent_response` visible summary as
      `assistant` — not from a stored raw transcript. AD-19: framework messages never become
      persisted contracts, and this keeps that true while making the product's central noun
      ("conversation") actually true for the agent.
- [x] **Out of scope:** persisting `AgentTurnV1` itself. Raw-transcript provenance is AD-12's
      envelope and belongs to Epic 4. Say so in the Dev Notes so a reviewer does not read this task
      as half of it.
- [x] This makes `to_framework_messages` (`translate.py:61-105`) reachable with owned records for the
      first time. The ledger item is about its **silent drops**: an unrecognized
      `AgentMessageV1.role` and an unrecognized `AgentPartV1.kind` fall through with no `else`. Fix
      both — raise, or drop with an explicit and tested decision — and close the entry.
- [x] Bound the rehydrated history explicitly. An unbounded transcript is an unbounded token bill
      against a budget AD-7 says the application owns.
- [x] `backend/agent/translate.py` has carried a zero-line-diff fence since Story 2.1 and **this
      task is the first authorized break of it.** Nothing else in that file changes.

### Task 13 — Chat renders the grounded response (AC: 2)

- [x] `ActivityTimeline.tsx` currently renders `item.text` for every item (`:22`). Branch on
      `activity_type` and render the `agent_response` variant.
- [x] Each **supported** claim renders its computed value with an **adjacent** `EvidenceLink`.
      `EvidenceLink` already exists (`components/primitives/EvidenceLink.tsx`) and has **no
      non-fixture call site** — this is its first real consumer. Its label is already
      `Evidence: {group} {record}{, fieldOrRange}, fixture {version}`, which is exactly UX-DR8's
      requirement; pass the planner-facing group name from Task 1's mapping, not the port's.
- [x] Adjacency is structural, not decorative: the link is inside the claim's own element. A single
      message-level Sources list fails AC2 explicitly.
- [x] `onActivate`/`href`: **Story 2.8 owns navigation.** Do not build jump/return, origin keys,
      focus restoration, or the exception panels here. Note in a comment that
      `deferred-work.md:68` flags an inert `EvidenceLink` with neither prop — decide what this story
      passes and make it deliberate.
- [x] A **failed** claim renders its distinct state naming the cause, keeps its position, and
      renders no number. Sibling supported claims still render normally.
- [x] No confidence score, no gauge, no percentage, no "approximately", no AI glow, no gradient, no
      pulsing evidence (UX-DR5, UX-DR32). Assert the absence — `index.test.ts` and
      `accessibility-contract.test.tsx` establish that pattern.
- [x] Accessibility: the response block is distinguishable by author/type label (EXPERIENCE.md:85);
      the Evidence link is keyboard-operable with a visible focus ring and a self-describing
      accessible name. Extend the existing jsdom a11y suites; **do not** add new tooling.
- [x] Chat code stays in `frontend/src/features/chat/`.
      `frontend/src/features/scenario-data/**` must show a **zero-line diff** — its directory is
      audited for mutation affordances by `scenarioDataBoundaries.test.ts`.
- [x] Wire the execute call after send. Keep `agent_queued` visible between the two calls; the
      existing `runStatusLabel` (`ChatView.tsx:24-27`) already renders it literally.
- [x] The stream merge is by `activity_id` (`useConversationStream.ts:281-283`) — the
      `agent_response` arriving from both the SSE frame and the timeline refetch must render **once**
      (UX-DR6). Test it; that dedup is the one Story 2.4 built and this is its first real exercise.

## Phase C — Close-out (Task 14)

### Task 14 — Regression, fences, and Gate A (AC: 1, 2, 3)

- [x] **Re-derive baselines; do not trust the numbers below.** At `00f8ae0` (Story 2.6 post-review,
      clean tree): backend **705 passed / 1 skipped / 7 deselected** (postgres included), frontend
      **55 files / 322 tests**, Playwright **46 passed**, `alembic check` zero diff. The single skip
      is `test_evidence_binding.py`'s clean-tree self-skip, which is why a dirty-tree run reports
      704/2 instead — the skip count tracks tree state.
- [x] Full backend suite, postgres suite, frontend vitest, typecheck, lint, Playwright.
- [x] **Zero-line diff, verified per path, not assumed:** `backend/services/**`, `backend/domain/**`,
      `backend/engine/**`, `backend/llm/**`, `backend/ingest/**`, `backend/store/**`,
      `backend/application/ports/scenario_catalogue.py`,
      `backend/adapters/postgres/scenario_catalogue.py`,
      `backend/tests/test_gate_a_mutation_audit.py`, `frontend/src/features/scenario-data/**`.
      `ALLOWED_LEAKS` stays untouched — `deferred-work.md:130-147` keeps its owner.
- [x] **No evidence file is owed.** No AC here carries a measured threshold, and NFR35's four rows
      belong to Stories 1.4, 1.5, 2.4 and 3.5 (`requirements-inventory.md:71`). Do not invent one.
- [x] **Gate A must still be re-run per AR28** (`docs/GATE-A-RUNBOOK.md`). Expect the two-commit
      dance Stories 2.5 and 2.6 used: the gate cannot be run twice in a row because
      `gate_a_readiness.main()` dirties `evidence/` (`deferred-work.md:97`). Commit the code, then
      measure, then generate, then commit the evidence **separately**
      (`docs/EVIDENCE-CONVENTION.md`). Confirm `gate_a_passed: true`, `blocking: []`.
- [x] Update `deferred-work.md`: **close** `:5` (Task 8), `:102` (Task 7), `:107` (Task 12);
      **partially close** `:115` (Task 6) with the visible-state half restated and reassigned;
      **re-annotate** `:106` (Task 7) without closing it;
      leave `:6`, `:7`, `:8`, `:106`, `:130-147` open and untouched.
- [x] Record any new deferred item this story creates in the same file, with an owner and a revisit
      trigger.

### Review Findings

*Code review 2026-08-13 against `4e2b812..31204a1` (66 files, +5643/−148). Three adversarial layers
(Blind Hunter, Edge Case Hunter, Acceptance Auditor); no layer failed. Every finding below was
re-verified against the working tree before rating — severity is the consequence at a real call
site, not the worst reading of a diff hunk.*

*Fences and traps are clean and independently confirmed: all Task 14 zero-diff paths verified empty
by `git diff --name-only`; traps 2–6 and 8–11 not stepped in; trap 7 genuinely guarded off FastAPI's
`dependant` rather than a string; exactly one new `ActivityItemV1` discriminant; Gate A bound to
`a3bbebf` with `gate_a_passed: true`, `blocking: []`, evidence committed separately as `d346cb7`;
`evidence/story-2.2/evaluation-harness-demonstration.json` not regenerated. The `scheduling_inspect.py`
zero-diff conflict resolves in the story's favour — it is untouched at the Phase A commit `7cd1108`
and modified only by Task 8 in Phase B, exactly as written.*

**AC verdicts: AC2 satisfied. AC1 and AC3 partially satisfied** — the produce-then-cite mechanism is
real, the gate never recomputes, and per-claim distinctness/preservation/non-retargeting are
implemented *and* tested. What is not established is that a correct number can actually be produced
and proven on the shipped data.

#### Decision needed

- [x] [Review][Patch] **[HIGH] [DECIDED] Three of the four metrics cannot return a supported claim on the only seeded fixture** — `scheduling_compute.py:137,171` passes `max_rows=resolved.budget_limit`, which is `settings.scheduling_inspect_row_limit` = **200**; `calculators.py:123` raises `CalculationLimitError` as soon as `matching_count > max_rows`. Measured, not inferred: `data/contract/sample_tiny_input.projection-v1.json` has **1547 demand rows** and **0 baseline-assignment rows**. So `required_demand_minutes` and `shortfall_minutes` always raise (1547 > 200) → `CalculationFailedError`, which is not in `retryable_error_codes`, so the run dies; `staffed_minutes` returns `value=0, evidence_refs=()` and is then failed by the gate (see next finding). Only `qualified_worker_count` (10 workers) can succeed. `GroupQueryV1.filters` exists and the demand adapter publishes `("family", "task_id")` filter keys, but `_drain` never populates them — it drains the whole group and filters in Python. Every backend test drives ≤3-row stubs, so nothing goes red. **AC1's primary Wednesday investigation question is unanswerable on shipped data.** **Chosen approach (Minh, 2026-08-13) — option 1 of three:** push `task_id` (and `family` when supplied) into `GroupQueryV1.filters`, and give `scheduling_compute` its own row bound sized for demand (~400) instead of borrowing `scheduling_inspect_row_limit`. Both halves are required, measured on the fixture: `task_id` alone leaves 218–295 rows and still breaches 200 for five of six tasks; `task_id + family` leaves 53–197, but `family` is optional in `ClaimArgumentsV1` so it cannot be relied on. Filter pushdown is the structurally correct half because the adapter computes `matching_count = len(filtered)` (`adapters/postgres/scenario_projection.py:447`) — the very number `_drain`'s bound tests. **The window is deliberately NOT pushed down:** `DEMAND_FILTERS` offers only `start_minute_gte`/`end_minute_lte`, which express containment, not overlap; using them would silently drop partially-overlapping rows that `interval_overlap_minutes` correctly counts, turning a fail-closed bug into a wrong-number bug. Adding overlap filter keys (`start_minute_lt`/`end_minute_gt`) to the adapter would drop row counts to single digits and is the right end state, but it widens the published `GroupQueryKeysV1` contract that `scheduling_inspect` also consumes — an AD-4 adapter decision this story is not scoped for. Recorded in `deferred-work.md` with an owner.
- [x] [Review][Patch] **[HIGH] [DECIDED] An application-side condition is reported as model fabrication, and a truthful zero cannot render** — `gate.py:120` fails any claim whose result carries no evidence refs (`if not result.evidence_refs: return _failed(proposal, "missing_evidence")`). A calculator that legitimately matches nothing returns `value=0, evidence_refs=()` — `qualified_worker_count` for a task nobody is qualified on, `staffed_minutes` against the 0-row baseline-assignments group. The one answer that is provably right renders to the planner as *Claim unavailable: missing evidence*. **The framing that resolved this (Minh, 2026-08-13):** `evidence_refs` is produced entirely by the calculator — trusted application code. The model cannot influence it: `ClaimProposalV1` is value-free and carries only a `result_id` to *cite*, never the refs themselves. So `len(refs) == 0` is a fact about the **trusted** side's output, and routing it to `missing_evidence` blames the untrusted party for the trusted party's behaviour. That is not just poor naming — it **violates AC3's "the failure remains distinct and inspectable"**, because one label now spans both sides of the trust boundary and a reader of a failed claim cannot tell whether the model lied or the application broke. The correct class already exists and has **no producer anywhere in `gate.py`**: `GroundingFailureV1.calculation_failed`, which Task 2 defined as mechanical rather than evaluative. (The `calculation_failed` strings in `scheduling_compute.py` are capability `ERROR_CODES` — a different vocabulary that happens to share the token.)

  **Chosen approach:** route by cause, using proof the calculator already observes but discards. `_drain` asserts `len(items) == matching_count` (`calculators.py:133`); carry that count through `CalculatedMetricV1` and `SchedulingComputeResultV1` so the gate can distinguish a proven empty set from an unexplained one:

  ```
  refs empty ∧ matching_count == 0  → supported, value = 0   (empty set proven)
  refs empty ∧ matching_count  > 0  → calculation_failed      (rows consumed, no locator emitted = application bug)
  ```

  This loosens nothing: a truncating calculator (trap #1) still fails — it simply fails under its own name instead of masquerading as model fabrication. It gives `calculation_failed` its first producer, and it strengthens AC3 rather than weakening it. The same reasoning applies to `gate.py:97`, where a *calculator-produced* locator that fails to resolve is reported as `missing_evidence`; that branch moves to `calculation_failed` too. `unauthorized_evidence` and `version_mismatch` are two of AR11's three named causes and stay exactly as they are. **Finding "[Review][Patch] `GroundingFailureV1.calculation_failed` has no producer" is folded into this item and is not a separate patch.**
- [x] [Review][Patch] **[HIGH] [DECIDED] The model is handed the computed value the design says it must not have** — `scheduling_compute_module()` (`scheduling_compute.py:194-203`) sets no `model_facing_text_field`, so `_render_result` (`capability_tools.py:28-40`) falls through to `asdict(value)` and returns the entire `SchedulingComputeResultV1` — `value`, `unit`, `result_id`, and every `EvidenceRefV1` including checksums — into the transcript. This contradicts `grounding.py`'s "proposals are deliberately value-free" and `deps.py:34`'s "The model sees only the separately rendered representation". The structural invariant still holds (`ClaimProposalV1` has no value field), so this is not a grounding breach on its own — but it makes the prose-digit crash below near-certain in production, because a model shown "90" will write "90" in prose. **Chosen approach (Minh, 2026-08-14) — flip the default rather than work around it.** Two weaker options were considered and rejected *because* they patch the rendering layer instead of the type boundary. Declaring `model_facing_text_field="result_id"` was rejected: that field's declared semantic is "this result **is** essentially a string, here it is" (`demonstration.text` literally is the result string), so stuffing a content hash into it is the same mechanism-wearing-a-disguise that Story 2.6's own review removed when it deleted the structural sniff. Adding an optional projection callable was rejected for a deeper reason: it leaves the default at `asdict` — fail-open — so safety would depend on every future module author remembering to declare one, in a repo whose entire posture is fail-closed. The `asdict` fallback was never a designed default; Story 2.6's review recorded it verbatim as "scheduling leaves it `None` and keeps `asdict`", i.e. status quo carried forward.

  **The actual error is one layer up:** `SchedulingComputeResultV1` is made to serve two consumers with different trust needs — the gate needs the whole truth (`value`, `refs`, `version`, `result_id`), the model needs only a receipt — and the mismatch is then papered over at render time. So: **make the model-facing projection a required, explicit declaration on `CapabilityModuleV1` and delete the `asdict` fallback**, with `validate_module` refusing a module that declares nothing (a mechanical guard, matching this story's other guards). `demonstration` keeps projecting its bare `text` string — mandatory, since the seven frozen Story 2.2 golden cases and the sha256-pinned demonstration evidence would otherwise change bytes. `scheduling_inspect` declares its full result explicitly; no behaviour change, since the model genuinely needs `items`/`next_cursor`/`truncated`/counts. `scheduling_compute` declares:

  ```python
  @dataclass(frozen=True)
  class SchedulingComputeModelViewV1:
      result_id: str
      metric:    MetricV1
      unit:      GroundingUnitV1
      matched:   Literal["none", "some"]
  ```

  No `value`, no `evidence_refs`. **`matched` is deliberately qualitative rather than the `matching_count` first proposed** — a count is a quantity, and handing the model any quantity recreates this very defect with a different number, plus "there are 8 demand rows" is itself an unlocated quantitative claim. `matching_count` still travels the trusted path to the gate for the D2 decision; it simply does not reach the model. This costs nothing on the trusted side because the sink captures the raw handler return *before* rendering (`capability_tools.py:104-106`), so narrowing the model's view cannot starve the gate.

  **Emergent invariant, and the main prize:** the model receives no quantity from any tool, so a numeral appearing in a prose segment can only be fabricated. That converts `UncitedNumericProseError` from a routine event (the model echoing a number it was just shown) into a genuine and rare fabrication signal — the prose ban stops firing on reasonable behaviour. It is also assertable: a test can require every module's model-facing projection to carry no numeric field. (Precisely: the rule is "no *quantity*", not "no digit characters" — `result_id` is hex; a hash reaching prose is caught by the ban and misleads no one.)
- [x] [Review][Patch] **[HIGH] [DECIDED] Demand `unit` is ignored, so `volume` rows are multiplied into "minutes"** — `calculators.py:238-242` computes `overlap_minutes * row.amount` for every matched demand row and labels the sum `"minutes"` unconditionally (`:274`). `DemandIntervalV1.unit` is `Literal["volume", "headcount"]` (`contracts/scenario_projection.py:94`) and is never read. A volume row (cartons) yields minutes×cartons presented as an authoritative, checksummed, evidence-cited minute figure — trap #1's failure mode reached through units instead of paging, and Task 3 named this explicitly ("mixing the two is a wrong number that renders confidently"). `ProjectionStub` (`test_scheduling_compute.py`) emits only `"headcount"`. **Measured, and it reframes the finding: `volume` is 1541 of 1547 demand rows; the 6 `headcount` rows are all family `indirect`.** So the whole of outbound and inbound demand — the flagship Wednesday question — is volume, and the metric is dimensionally wrong for 99.6% of the data rather than for an edge case.

  **A rate conversion is not available at this layer, and not merely because a field is missing.** The projection does carry a rate, but at `QualificationRefV1.rate` — *per worker, per task* (`contracts/scenario_projection.py:59-62`). Converting volume to minutes therefore depends on **who performs the work**: the same 500 units is 40 minutes for one worker and 60 for another. "Required minutes" is thus not a property of demand at all; it is a function of an assignment, which is a solver question owned by Epic 3 and CP-SAT. For the 6 headcount rows (`amount=1.0` over `[300, 810)`) the metric is perfectly well-defined — minutes × headcount. For volume rows the quantity is not well-defined at the read model, so this is a boundary, not a bug to patch in place.

  **Chosen approach (Minh, 2026-08-14) — split the vocabulary along the dimension:** `required_headcount_minutes` (headcount rows only, `unit="minutes"`) and `required_demand_volume` (volume rows only, `unit="units"`, one new member on `GroundingUnitV1`). Both are dimensionally sound, both computable from the projection alone, both carry real locators. `staffed_minutes` and `shortfall_minutes` stay on the headcount side, since comparing required against staffed is meaningful only within one dimension. Rejected: filtering to headcount only, or raising on volume rows — both are honest and fail-closed, but they turn 99.6% of the shipped data into an unanswerable region, whereas the split still gives the planner a real, evidenced, verifiable number for outbound demand (in units rather than minutes). `SCOPE_CONTROLS` records volume→minutes conversion as NOT COVERED with Epic 3 named as owner and the per-worker-rate reason stated, so the boundary carries its justification. Cheap now — `MetricV1` is a closed vocabulary this story created, with no consumer beyond its own four golden cases; after Epic 3 it would not be.
- [x] [Review][Patch] **[HIGH] [DECIDED] The four golden cases are a self-fulfilling oracle** — `evals/grounding.py:39-59` builds the "trusted" results map as `results[proposal.result_id] = SchedulingComputeResultV1(..., value=60, ...)`, keyed off whatever id the case cites, with a hand-built `EvidenceRefV1` literal, and branches on `case.expected_grounding_outcome` to decide what to inject (omit it for `missing_evidence`, `UUID(int=999)` for `version_mismatch`). The real `scheduling_compute` handler does run, returns `value=0, evidence_refs=()` against the harness reader, and that output is **discarded**. Consequences: `supported.json`'s `expected_evidence_refs` is matched against a locator the harness itself wrote, not one any calculator produced; the three failure cases carry `expected_evidence_refs` that `GroundingEvaluator` never compares (`evaluators.py` compares refs only when `expected_failure is None`); `missing-evidence.json`'s `ffff…` id is decorative. Only argument-mismatch falsifies from case data. AC3's "the evaluation fixture records the expected evidence IDs and oracle result" is met nominally — the oracle cannot detect a wrong calculation, which is the one thing NFR12 needs it to detect.

  **This is not a peer of the other findings — it is why several of them exist.** Had the four cases driven the real calculator over real rows, both of the severe defects above would have surfaced during Phase A: the 200-row bound would have breached on realistic data, and `overlap × amount` over a `volume` row would have produced a visibly absurd number that whoever authored the case file had to copy in by hand. The two worst defects in this story survived *because* the oracle never touches the calculator. The charitable reading of why it was written this way: the harness reader returns empty pages, so a real result is `value=0, evidence_refs=()`, which the pre-D2 gate failed as `missing_evidence` — meaning no case could be authored as `supported`, and fabrication was the way around that.

  **Chosen approach (Minh, 2026-08-14):** seed the eval harness with a small deterministic projection carrying real rows (3–5 demand rows for one task and window), and **delete the fabrication in `grounding.py`** so `calculate_metric` genuinely runs and the oracle compares against locators the calculator itself emitted. `version_mismatch` is then produced by pinning `deps` to a version other than the fixture's, and `missing_evidence` simply by a scripted turn citing a `result_id` no call produced — neither needs injection. Deliberately a small synthetic fixture rather than `sample_tiny_input`'s 1547 rows, so `expected_evidence_refs` stays hand-authorable and the case files stay readable; the four cases retag away from `sample_tiny_input:v1`, which is unencumbered since they are this story's own new cases and not part of Story 2.2's frozen set. `GroundingEvaluator` must also compare `expected_evidence_refs` on the failure branches, not only when `expected_failure is None`, and `test_grounding_cases_have_literal_result_ids_nonempty_refs_and_oracles` should assert the ids equal `derive_result_id(...)` rather than merely `len(...) == 64`, so a hashing regression goes red.
- [x] [Review][Patch] **[HIGH] [DECIDED] The capability grant is tautological, and the `consequential` demonstration module reaches live planners** — `conversations.py:190-192` builds `feature_policy = frozenset(module.required_feature_policy for module in installed_modules())`, so `registry.py:58`'s `module.required_feature_policy in context.feature_policy` can never be false. This is the only production construction site of `CapabilityGrantContextV1` in the repo, so the policy dimension of the grant is dead on the one path that uses it, and `revoked_conversation_ids` is left at its empty default so conversation revocation never applies. Concretely: `demonstration_module` is in `_INSTALLED_FACTORIES` with `required_role="planner"`, `risk_class="consequential"`, `approval_policy="exact_action"` — a `NON_PRODUCT_CAPABILITIES` harness module granted on every live turn, whose `ApprovalRequired` produces `suspended`, which `terminal_status` maps to `agent_failed`. In fairness on severity: demonstration's handler only joins strings, so this is not a data exposure — it is wasted turns, plus an approval path this story explicitly declined to build (Task 11: "Do not build a refusal or clarification variant here"). The principle it breaks is AD-2's "an ungranted capability is absent, never present-and-refusing".

  **Chosen approach (Minh, 2026-08-14):** build `feature_policy` from `Settings`. The policy names already say the intent — `scheduling_compute_enabled`, `scheduling_inspect_enabled` — they were simply never wired to a source; the mechanism has been correct since Story 2.5 and only lacked a supplier. `settings` is already injected into the route. Defaults: `scheduling_compute_enabled=True`, `scheduling_inspect_enabled=True`, **`demonstration_enabled=False`**. A separately declared "non-product capability" property was considered and rejected as unnecessary: the `False` default achieves the same exclusion through the mechanism that already exists rather than adding a second, parallel one — and it **preserves Story 2.6's proof**, since demonstration stays installed and grantable when the flag is on, so the add/remove-a-governed-module demonstration still holds with the harness and tests enabling it explicitly. Add a mechanical guard asserting `feature_policy` is **not** derived from `installed_modules()`, in the shape of this story's trap #7/#8 guards, or this exact line grows back. `revoked_conversation_ids` stays at its empty default and goes to the ledger instead: no revocation data source exists yet, and wiring one now would be a mechanism with no user.
- [x] [Review][Patch] **[SETTLED BY ANALYSIS] `shortfall_minutes` filters demand by family but staffing not at all** — `calculators.py:232-251,271`. `matched_demand` honours `arguments.family`; `matched_assignments` cannot, because assignments carry no family. `max(0, required - staffed)` therefore subtracts all-family staffed minutes from outbound-only required minutes and reports the difference as a grounded, cited shortfall. **The second option originally offered here — resolving an assignment's family through its task — is impossible, and the D1 measurement proves it:** task `1E5596F1…` carries 197 `inbound`, 53 `outbound` and 6 `indirect` demand rows, so family is not a function of `task_id`. It is a property of the demand row alone and `AssignmentV1` does not carry it. **Therefore, one sound resolution only: reject the `family` argument on metrics that touch assignments (`staffed_minutes`, `shortfall_minutes`), which are per-task and family-agnostic; keep `family` on the demand-only metrics (`required_headcount_minutes`, `required_demand_volume`), where it is well defined.** Raised as a decision, closed by analysis rather than by asking.

#### Patch

- [x] [Review][Patch] **[HIGH] Any non-`AgentRuntimeError` escapes the route, 500s the request, and strands the run in `agent_running` forever** [backend/api/routers/conversations.py:227-249] — the route catches only `AgentRuntimeError`. `ground_answer` raises `UncitedNumericProseError(ValueError)` for any decimal digit in prose (`gate.py:150`) and `rehydrate_history` raises `ValueError` on an unknown variant (`execute_turn.py:90`); neither is caught. `_finish` never runs, so the run sits at `agent_running` — and Decision 1's own guard means `claim_queued_run` will refuse it forever. There is no reaper. `_finish` itself is also unguarded (`conversation.py` raises `RuntimeError`/`AgentRunNotQueuedError`), so the same hole exists on the finalize side. The story's own fail-closed rule is thus the single most likely path to a non-terminal run, contradicting Task 11's "a runtime failure still reaches a **terminal** `agent_run` status".
- [x] [Review][Patch] **`qualified_worker_count` ignores the window and family it hashes into `result_id`** [backend/application/grounding/calculators.py:200-214] — `_window` is never called on this branch, so the count is horizon-wide, yet `derive_result_id` folds those arguments into the hash and the gate's `result.arguments != proposal.arguments` check passes them as verified. "How many qualified pickers on Wednesday 09:00–17:00" returns the whole-week count, stamped supported. Reject window/family for this metric or honour them.
- [x] [Review][Patch] **Evidence labels never show the minute range, and claim arguments are never rendered** [frontend/src/features/chat/ActivityTimeline.tsx:9-15,27] — `fieldOrRange` returns `reference.field` first, and `calculators.py:254,261` always sets `field="amount"`/`field="task_id"` *alongside* the minutes. The `780–1020 minutes` branch is only reachable from the test fixture, which sets `field: null`. `ClaimSegment` renders `{claim.value} {claim.unit}` and drops `claim.arguments` entirely — so, combined with the prose digit ban, a rendered answer cannot state which task or window the number belongs to. Task 4 explicitly said "the renderer draws windows and identifiers from claim arguments".
- [x] [Review][Patch] **No test binds a real calculator result to the gate** [backend/tests/test_grounding_gate.py] — the gate suite hand-constructs `SchedulingComputeResultV1`; `test_scheduling_compute.py` never calls `ground_answer`. The one seam AC1 rests on (calculator → `result_id` → gate → supported claim carrying the calculator's own locators) is exercised nowhere end to end. `test_grounding_cases_have_literal_result_ids_nonempty_refs_and_oracles` only asserts `len(result_id) == 64`, so a `derive_result_id` regression cannot turn the cases red — the exact late-surfacing failure Task 3 warned about.
- [x] [Review][Patch] **`useSendMessage` has no `onError`/`onSettled`, so a failed execute wedges the timeline** [frontend/src/hooks/useSendMessage.ts:10-27] — `setQueryData` has already appended the optimistic activity and set `latest_agent_run_status: "agent_queued"`; invalidation lives only in `onSuccess`. If `executeTurn` rejects — 409, any 500 above, or a dropped connection — the timeline never refetches and shows a queued turn that will never resolve. No rollback, no retry, no resume. The whole LLM turn is also bound to one HTTP request lifetime with no handling for proxy timeouts.
- [x] [Review][Patch] **Failed and timed-out runs persist an empty response that renders as a blank ShiftMind bubble** [backend/application/use_cases/execute_turn.py:58-62] — `visible_response` returns `GroundedResponseV1(segments=())` for every non-completed outcome, and `ActivityTimeline.tsx:44` renders the author label with no content. `test_runtime_failure_still_finalizes_the_claimed_run` asserts the status but never the visible content. Also feeds the history bug below.
- [x] [Review][Patch] **`_drain` can spin on empty-but-advancing cursors, and `limit=0` misreports the bound** [backend/application/grounding/calculators.py:100-141] — `seen_cursors` catches only repeats and `next_cursor <= cursor` only catches non-advance, so a reader returning `items=()` with a strictly increasing cursor loops without bound; `len(items) > max_rows` never fires because `limit` is clamped to `max_rows - len(items)`. There is no iteration cap, and `scheduling_compute`'s timeout check runs only *after* `calculate_metric` returns. Separately, when `len(items) == max_rows` with a non-null cursor, `limit` becomes `0` and the caller reports "projection cursor did not advance" instead of the bound it actually hit.
- [x] [Review][Patch] **SQL NULL semantics silently drop events from rehydrated history** [backend/adapters/postgres/conversation.py:319] — `persisted_event.c.agent_run_id != agent_run_id` evaluates to NULL for any row with a NULL `agent_run_id`, excluding it. History is built from whatever survives, with no signal anything was skipped.
- [x] [Review][Patch] **`derive_result_id` claims RFC 8785 canonicalization it does not implement** [backend/application/capabilities/scheduling_compute.py:108-119] — the docstring says "RFC-8785 canonical SHA-256"; the body is `json.dumps(..., sort_keys=True, separators=(",", ":"))`, which is neither JCS number serialization nor UTF-16 code-unit key ordering. Task 3 mandated RFC 8785 specifically because AR20 fixes it as this repository's hashing convention, and `EvidenceRefV1.checksum_schema_version` is `"rfc8785-v1"`. Either implement it or correct the claim.
- [x] [Review][Patch] **`GroundingFailureV1.calculation_failed` has no producer** [backend/application/contracts/grounding.py:25-31] — **folded into the D2 decision above**, which gives it its first producer. Not a separate patch.
- [x] [Review][Patch] **Task 5's byte-identical regression fence was not built as specified** [backend/tests/test_agent_runtime_adapter.py] — Task 5 required "with `answer_type=None`, an existing golden case produces a byte-identical `AgentRunOutcomeV1` to today's". The test asserts four fields against a one-line `FunctionModel` — not a golden case, not an outcome comparison. This is the declared regression fence for Decision 3. Separately, `AgentRunOutcomeV1` gained **two** fields (`answer` *and* `grounded_response`) where Task 5 declared one.
- [x] [Review][Patch] **Capability error vocabularies changed without a `capability_version` bump** [backend/application/capabilities/scheduling_inspect.py:66, demonstration.py:22-24] — `SchedulingInspectError.code` moved from `"invalid_query"` to `"inspection_failed"` and `ERROR_CODES` gained entries; `DemonstrationError.code` moved to `"demonstration_failed"`. Both manifests still advertise an unchanged `capability_version`, so no consumer can detect the change — and the behaviour genuinely changed: a generic inspect failure used to be retryable and now terminates the run. Correct per Task 8; the version is the omission.
- [x] [Review][Patch] **The 409 refusal branch is implemented but untested** [backend/tests/test_conversations_api.py] — `conversations.py:198-204` returns the problem response, but the test double's `claim_queued_run` never raises `AgentRunNotQueuedError`, so Task 11's "refused with a stable problem response and **no** side effect" is unproven at the route. The postgres race test does prove the repository-level refusal and the one-transition/one-event invariant.
- [x] [Review][Patch] **`isdecimal()` misses numeral forms the scope control claims to cover** [backend/application/grounding/gate.py:149] — `SCOPE_CONTROLS` states the rule "COVERS every Unicode decimal digit" and exempts only spelled-out quantities, but `isdecimal()` is `False` for `²`, `⑤`, `Ⅳ`, `½`. Either widen the check or narrow the declared claim; per Task 4, any relaxation must be a declared allow-list with its own test.
- [x] [Review][Patch] **`stable_evidence_ref` emits `None` into the oracle string on a half-specified interval** [backend/evals/evaluators.py:110-117] — an `EvidenceRefV1` with exactly one of `start_minute`/`end_minute` set (both are independently `int | None`) produces `"amount:None-4320"`, which can never match an authored expectation and yields an unreadable diff.
- [x] [Review][Patch] **Task 13's accessibility assertions landed in the component test, not the a11y suite** [frontend/src/features/chat/ActivityTimeline.test.tsx] — Task 13 said "extend the existing jsdom a11y suites"; `accessibility-contract.test.tsx` shows a zero diff. The focus-ring check is also a Tailwind class-string match (`toContain("focus-visible:ring-3")`) rather than a behavioural assertion.
- [x] [Review][Patch] **The ledger does not match what Task 14 claims** [_bmad-output/implementation-artifacts/deferred-work.md] — Task 14 required `:115` be *partially closed* with the visible-state half restated and reassigned. The entry is byte-unchanged and still asserts two things that are now false: "`expected_evidence_refs` is evaluated nowhere in the repo" and "Task 3 explicitly forbids shipping a second evaluator". The in-place precedent was followed for `:102`, `:106` and `:107` but not here. Task 7's closure also reads "commit pending" where the commit (`7cd1108`/`a3bbebf`) is knowable.

- [x] [Review][Patch] **Float values reach the UI unrounded in a feature whose premise is exactness** [frontend/src/features/chat/ActivityTimeline.tsx:27] — `DemandIntervalV1.amount` is `float` and `ClaimSegment` renders `{claim.value} {claim.unit}` verbatim, so `90.00000000000001` is reachable, cited and checksummed. **This was initially dismissed on a false premise** — "the fixture exhibits no float amounts" — which the D1/D4 measurement disproved: every demand row carries a float `amount` (e.g. `2.1518`), so the whole fixture is float. Reinstated as a patch; low severity but real, and it lands squarely in a feature whose entire claim is exactness.

#### Deferred

- [x] [Review][Defer] **No recovery for a run stranded in `agent_running`** [backend/adapters/postgres/conversation.py:310-314] — deferred, pre-existing scope boundary: a client disconnect, worker death, or process restart between claim and finish leaves the row unrecoverable; there is no reaper and no `claimed_at` to build one from. AD-18 assigns durable leasing, fencing, and worker recovery to Epic 3, and the story's own out-of-scope table names it. The *patchable* half — exceptions on the happy path — is listed above.
- [x] [Review][Defer] **A revoked membership turns a queued run into a permanent non-disclosing 404** [backend/adapters/postgres/conversation.py:293-307] — deferred, pre-existing: the claim query inner-joins `membership … revoked_at IS NULL`, so revoking a membership after `accept_turn` queued a run yields `None` → a bare 404 indistinguishable from "no such run", with no path that ever drains the queued row. Membership lifecycle is not this story's.
- [x] [Review][Defer] **Duplicate live memberships raise `MultipleResultsFound` → 500** [backend/adapters/postgres/conversation.py:305] — deferred, pre-existing: the claim query ends in `.one_or_none()`; two non-revoked memberships for one user/site crash rather than resolving. No constraint currently forbids the duplicate.
- [x] [Review][Defer] **Per-request LLM provider construction and per-item `TypeAdapter` rebuilds** [backend/agent/runtime.py:399-421, backend/api/routers/conversations.py:116-119] — deferred, performance only: `get_agent_runtime_factory` is a per-request dependency, so every `/execute` builds a fresh provider and HTTP client with no pooling or shutdown hook; `_activity` constructs a `TypeAdapter` per timeline item (up to 200) and per SSE frame, and the adapter rebuilds one per payload round-trip. Correct, just wasteful; no AC touches it.
- [x] [Review][Defer] **Any site member can execute another member's queued run** [backend/adapters/postgres/conversation.py:299-303] — deferred, pre-existing: `claim_queued_run` filters on `conversation_id` and `agent_run_id` only, with site isolation from RLS, so within a site any authenticated member can trigger execution — and the LLM spend — of a run queued by someone else. `deps.actor_id` comes from the originating message, so the audit trail attributes it to the author who did not start it. Single active membership makes this unreachable in this milestone.

- [x] [Review][Defer] **Calculators cannot push a time window into the projection** [backend/adapters/postgres/scenario_projection.py:355-361] — deferred, **new item arising from the D1 decision**: `DEMAND_FILTERS` publishes only `start_minute_gte`/`end_minute_lte`, which express containment, not overlap, so the window cannot be pushed down without adding `start_minute_lt`/`end_minute_gt` to the adapter — which widens the `GroupQueryKeysV1` contract that `scheduling_inspect` also reads, an AD-4 decision outside this story. Recorded in `deferred-work.md` with owner and trigger.
- [x] [Review][Defer] **`revoked_conversation_ids` is a grant dimension with no data source** [backend/api/routers/conversations.py:190-196] — deferred, **new item arising from the D6 decision**: `compose_granted_capabilities` branches on it, but nothing in the schema records a revoked conversation, so wiring it now would be a mechanism with no user and no test able to distinguish it from the default. Its sibling defect (`feature_policy`) was fixed instead precisely because that one had a real supplier available in `Settings`. Recorded in `deferred-work.md` with owner and trigger.

#### Dismissed as noise (5)

Recorded so a future review does not re-raise them — note that a sixth, unrounded float rendering, was **un-dismissed** during decision review once the fixture measurement disproved its dismissal premise, and is now a patch above: the inert `onActivate={() => undefined}` is deliberate, commented, and exactly what Task 13 asked to be decided; the background-work ban not scanning `run_in_threadpool` is correct, since Decision 1 *mandates* that primitive; `ALLOWED_LEAKS`'s self-comparison is accompanied by real verification at `test_execute_turn_boundaries.py:61-64`; the persisted segment union is safely resolvable because both variants carry distinct `kind` Literals; the malformed-`agent_response` `KeyError` needs a payload shape the writer never produced and no legacy row can hold.

---

## Dev Notes

### What this story is, and what it is not

| In scope | Out of scope | Owner |
|---|---|---|
| Grounding gate, calculators behind the `scheduling_compute` capability, `EvidenceRefV1` emission (FR7, NFR12) | Evidence **jump/return**, origin keys, focus restoration, exception panels | Story 2.8 |
| First agent execution on a request path | Clarification, refusal, injection, the full failure taxonomy | Story 2.9 |
| `agent_response` activity variant + renderer | The other six `ActivityItemV1` discriminants | 2.9 / Epic 3 / Epic 4 |
| `UPDATE (status)` grant on `agent_run` | Durable job lease, fencing, worker recovery | Epic 3 (AD-18) |
| Locators bound to scenario version + checksum | `producing_run_version`, `MetricSetV1`, `ComparisonV1` | Epic 3 |
| History rehydrated from persisted activity | Persisting `AgentTurnV1`; `AuditEnvelopeV1`; `EvidenceSnapshot` | Epic 4 (AD-12) |
| `GroundingEvaluator` + its golden cases | A second evaluator for refusal/injection | Story 2.9 |

**One migration. One new route. One new capability. No new dependency.** The capability is
`scheduling_compute` (Task 3) — a governed module registered in `installed.py`, not a helper
function; `scheduling_inspect` shows a zero-line diff. PydanticAI 2.27.0 is already a repository lock
(`ARCHITECTURE-SPINE.md:271`, `backend/pyproject.toml`), so AR27's add-and-lock-at-the-gate ceremony
is **not** owed. If you find yourself reaching for a new *package*, stop — a new capability was
priced at creation, a new dependency was not.

### The traps, ranked by how quietly they fail

1. **Computing a total from one page** (Decision 4). Produces a wrong number wearing a valid
   evidence locator. No test you would write yourself goes red. This is the worst outcome available
   in this story, because grounding that lies is worse than no grounding.
2. **Two ad-hoc group-name translations** instead of Task 1's single mapping. The Evidence link
   names a group the planner cannot find in Scenario Data; nothing in the backend notices.
3. **Accepting a citation without checking its arguments** (Task 4, step 2). The model calls
   `scheduling_compute` for Thursday, receives a correct value with correct locators, and cites it on
   a claim about Friday. Every part is genuine except the pairing. The number renders, the Evidence
   link resolves to real rows, and the planner verifies it successfully — against the wrong
   question. This is the only remaining way for a fully grounded response to be false, which is why
   Task 6 contributes a case for it specifically.
4. **Retargeting on a miss.** Picking the nearest row, or the current version, when the cited one
   does not resolve. Reads as helpful, is the exact thing AR11 forbids, and is invisible unless
   asserted.
5. **Mounting the new route under `/api/v1/scenarios`.** Turns
   `test_gate_a_mutation_audit.py:24-34` red — loud, which is why it is ranked here and not higher,
   but it will cost an hour and AR28 forbids editing the assertion.
6. **Forgetting that structured output introduces `final_result`** (Decision 3). Fails as a
   confusing tool-count mismatch across seven previously-green golden cases, an hour after you
   thought the adapter change was done.
7. **Holding the site-scoped transaction across `run_sync`.** Correct at 40 ms, an outage at 60 s —
   `api/deps.py:161-178` documents exactly this and Story 2.4's Decision 1 is the precedent, stated
   in prose there and never guarded. Task 11's dependency-set assertion is the guard here.
8. **Building a background executor** because "queued" implies async (Decision 1). Would fail as an
   architecture violation no *functional* test detects — which is why Task 11 adds the
   `BackgroundTasks`/`create_task`/`ThreadPoolExecutor` ban with its documented allow-list entry.
9. **Adding `failure_reason`/`completed_at` columns to `agent_run`** because a terminal state
   "obviously" needs them. Duplicates the activity payload, widens a migration, and buys nothing an
   AC asks for.
10. **Deleting the postgres test that probes `agent_response` as an unrenderable variant** instead
    of re-pointing it (Task 10). It goes red for a legitimate reason, and the cheapest way to make it
    green is to remove the repo's only proof that an unknown activity payload fails typed rather
    than as a 500 mid-timeline.
11. **Re-adding a recompute-and-compare step "to be safe."** It reads like defence in depth and is
    the opposite: the gate holds no second value to compare against, so the only way to have one is
    to make the model produce it — which restores the manufactured-failure mode Decision 2 removed,
    where a correct, evidenced, version-pinned number renders as a failure because a discarded
    arithmetic guess disagreed. AD-11 sanctions `produce` **or** `verify`; this story took
    `produce`, and one calculation per metric is the invariant.

### Existing conventions to match, not reinvent

- **Contract style** — `contracts/stream_cursor.py` is the model: `from __future__ import
  annotations`, `SCHEMA_VERSION = "1"`, frozen dataclasses only, `V1` suffix on every type including
  `Literal` aliases, a docstring explaining *why the shape is this shape* with AD numbers, explicit
  `__all__`.
- **Scope-as-data** — `scheduling_inspect.py:36-60`: a `Mapping[str, str]` where every value names
  what the control covers **and** what it does `NOT COVER`, asserted by a test. Use it for Task 4's
  reduction and the schedule/run-version gap.
- **Deferred settings import** — `scheduling_inspect.py:126-130`: `from settings import
  default_settings` **inside** the factory, never at module scope. `application/**` must be
  importable without process configuration.
- **Error shape** — exception classes carrying a `code` class attribute plus a module-level
  `ERROR_CODES` tuple the manifest declares.
- **Non-disclosure** — one status, one code, one byte-identical body for every rejection cause
  (`conversations.py:137-149`). An unauthorized evidence target must not be distinguishable from a
  missing one *to a prober*, even though the two are distinct *to an authorized planner*. Both
  requirements are real; they are resolved by scoping, not by collapsing them.
- **Test doubles** — `build_model_double(case)` with `models.ALLOW_MODEL_REQUESTS = False` at module
  scope. Nothing here may reach a network or skip itself; Story 1.11 established that a skipped test
  is not a passed test.
- **Distinct UUIDs per identity field** in `AgentDepsV1` fixtures (Story 2.5 review finding 8).

### Latest technical information (executed against the installed lock at story creation)

- `output_type=[str, DeferredToolRequests]` → `info.output_tools == []`, `allow_text_output is True`.
  **`final_result` appears nowhere in this repository today.**
- `output_type=[GroundedAnswerV1, DeferredToolRequests]` → `info.output_tools == ['final_result']`,
  `allow_text_output is False`, and `all_messages()` gains both a `ToolCallPart` and a
  `ToolReturnPart` named `final_result`.
- A strict-answer agent whose model emits prose retries **once**, then raises
  `UnexpectedModelBehavior("Exceeded maximum output retries (1)")` → already mapped by
  `runtime.py:175-176` to `AgentRuntimeError`. **No re-verification is owed on any of the above.**
- `Tool.from_schema(...)`, `ApprovalRequired`, `ModelRetry`, `RunContext`, `DeferredToolRequests`,
  `ToolDenied`, `CancellationToken` are all already exercised by `runtime.py`/`capability_tools.py`;
  none of their behaviour changes here.
- `alembic check` must be run from the **repository root** (`deferred-work.md:117-126`).
- Python floor is 3.10 (`>=3.10,<3.13`); the venv is 3.10.9. Avoid 3.11+ syntax.

### Project Structure Notes

- `backend/application/contracts/grounding.py` — **new**. Register it in
  `tests/architecture/test_agent_runtime_boundaries.py:380-394`'s contract-module list.
- `backend/application/grounding/{calculators,gate}.py` — **new** package. The spine's
  Capability → Architecture Map names *"scheduling capability module, scenario projection,
  **grounding service**"* for FR-5–FR-8 (`ARCHITECTURE-SPINE.md:436`), so this is a named home, not
  an invention. `application/` is AR26's structural seed directory.
- `backend/application/use_cases/execute_turn.py` — **new**, beside `accept_turn.py`.
- `backend/migrations/versions/<rev>_grant_agent_run_status_update.py` — **new**, on top of
  `a4f92d7c8e31`.
- Backend acceptance suites sit in `backend/tests/`; architecture guards sit in
  `backend/tests/architecture/` per Story 2.1's recorded AR26 variance (one rootdir, one
  `conftest.py`).
- Frontend chat code stays in `frontend/src/features/chat/`.

### References

- `_bmad-output/planning-artifacts/epics.md:769-790` — Story 2.7 ACs; `:792-813` (2.8) and
  `:815-841` (2.9) — the two fences
- `epics.md:157` (AR11), `:186` (UX-DR5), `:192` (UX-DR8), `:240` (UX-DR32), `:1527` (never pad the
  dataset)
- `prds/prd-ShiftMind-2026-07-21/prd.md:133-134` (FR-7 and its testable consequence), `:127` (FR-5),
  `:265`, `:325` (grounding release gate)
- `requirements-inventory.md:33` (NFR12), `:48` (NFR27), `:49` (NFR28), `:50` (NFR29), `:71` (NFR35
  allocation — none of it is this story's)
- `ARCHITECTURE-SPINE.md:150-154` (AD-11), `:174-178` (AD-15), `:204-208` (AD-20), `:210-214`
  (AD-21), `:216-220` (AD-22), `:222-226` (AD-23), `:312-319` (Normative contract minimums and the
  `EvidenceRefV1` required shape), `:436` (grounding service)
- `ux-designs/…/EXPERIENCE.md:85-86` (message block, Evidence link), `:146-173` (Evidence Navigation
  and the exception table), `:60-73` (voice — the copy rules), `:192` (accessibility floor)
- `2-5-…md` / `sprint-status.yaml:154-168` — Decision 1 and the five-item handoff to this story;
  `sprint-status.yaml:104-111` — the audit/evidence declaration-only precedent
- `2-6-…md:611-620` — the out-of-scope table naming this story three times
- `deferred-work.md:5` (retryable timeout), `:102` (`create_agent_runtime`), `:107` (translate.py
  drops), `:115` (`expected_evidence_refs` evaluated nowhere), `:97` (the double-run Gate A trap),
  `:130-147` (the AD-1 leak this story must **not** close), `:68` (inert `EvidenceLink`)
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`, `docs/AGENT-RUNTIME-DECISION.md`
- Code: `application/contracts/{evidence_ref,activity,agent_runtime,scenario_projection,capability_manifest}.py`,
  `application/ports/scenario_projection.py`, `application/capabilities/{registry,deps,module,scheduling_inspect,installed}.py`,
  `application/use_cases/{accept_turn,read_scenario_facts}.py`,
  `agent/{runtime,capability_tools,translate}.py`, `api/{deps,schemas}.py`,
  `api/routers/conversations.py`, `adapters/postgres/{conversation,schema}.py`,
  `evals/{cases,evaluators,report,doubles}.py`, `evals/README.md`,
  `frontend/src/features/chat/{ActivityTimeline,ChatView}.tsx`,
  `frontend/src/components/primitives/EvidenceLink.tsx`,
  `frontend/src/hooks/useConversationStream.ts`, `frontend/src/api/conversations.ts`

## Dev Agent Record

### Agent Model Used

### Debug Log References

- Task 1 RED: `uv run --frozen pytest tests/test_evidence_ref.py -q` failed at collection because the mapping module did not exist.
- Task 1 GREEN/regression: focused suite 8 passed; full backend suite 705 passed, 2 skipped, 7 deselected.
- Task 2 RED: grounding contract suite failed at collection because `application.contracts.grounding` did not exist.
- Task 2 GREEN/regression: focused contract/architecture suites 19 passed; full backend suite 709 passed, 2 skipped, 7 deselected.
- Task 3 RED: scheduling-compute suite failed at collection because the capability module did not exist; a one-page mutation later produced 60 instead of the correct 90 and failed as required.
- Task 3 GREEN/regression: calculator/capability/conformance suites 44 passed; full backend suite 727 passed, 2 skipped, 7 deselected. `scheduling_inspect.py` has zero diff.
- Task 4 RED: grounding-gate suite failed at collection because the gate module did not exist.
- Task 4 GREEN/regression: 11 focused gate checks passed; full backend suite 738 passed, 2 skipped, 7 deselected.
- Task 5 RED: adapter suite showed the missing `answer` field and rejected the new `answer_type` constructor parameter.
- Task 5 GREEN/regression: 13 focused adapter checks passed; full backend suite 742 passed, 2 skipped, 7 deselected.
- Task 6 RED: evaluation harness initially rejected structured case turns and counted the framework output tool as a second routed capability.
- Task 6 GREEN/regression: evaluation harness 25 passed, 1 deselected; full backend suite 743 passed, 2 skipped, 7 deselected. Demonstration evidence was not regenerated.
- Phase A checkpoint: 4 metrics shipped; 3 are not exercised by the four AC oracle cases. Paging mutation observed RED (60 vs 90). 4 golden cases: 1 supported, 1 version-mismatch, 1 missing-evidence, 1 argument-mismatch; NFR28 floor green. Honest-gap assumptions contradicted by code: 0. Elapsed implementation time: approximately 25 minutes against a 30-minute working estimate; revised Phase B estimate: 45 minutes. Halt conditions triggered: 0.
- Task 7 RED: adapter tests observed `NoneType` instead of configured TestModel/OpenRouter model instances.
- Task 7 GREEN/regression: 15 focused adapter checks passed; full backend suite 745 passed, 2 skipped, 7 deselected. No live-provider test was added.
- Task 8 RED: focused suites could not import the required timeout and dedicated invalid-repeat errors.
- Task 8 GREEN/regression: 87 focused capability/conformance checks passed (1 expected group skip); full backend suite 746 passed, 2 skipped, 7 deselected.
- Task 9 RED: the schema test failed because the revision did not exist; the first full regression then exposed the intentionally changed Alembic head expectation.
- Task 9 GREEN/regression: Alembic check reports no new operations; PostgreSQL suite 44 passed; full backend suite 748 passed, 2 skipped, 7 deselected.
- Task 10 RED: the first transport round-trip rejected an owned `GroundedResponseV1` as an untyped dictionary.
- Task 10 GREEN/regression: 49 focused conversation checks passed; full backend suite 749 passed, 2 skipped, 7 deselected; generated frontend typecheck passed.
- Task 11 RED: the execute route, run claim/finalization repository operations, and detached-work guards did not exist.
- Task 11 GREEN/regression: 63 focused runtime/conversation/architecture checks passed; the PostgreSQL race test proved one claim, one terminal transition, and one response event; Gate A mutation audit stayed green.
- Task 12 RED: execute-turn supplied an empty history and reverse translation silently accepted unknown discriminants.
- Task 12 GREEN/regression: 19 focused history/runtime checks passed; persisted visible activities rehydrate into a 100-activity owned-history window and unknown roles/parts fail explicitly; the deferred item is closed.
- Task 13 RED: the timeline assumed every activity had `text`, no execute client existed, and SSE listened only for planner messages.
- Task 13 GREEN/regression: frontend 56 files / 325 tests and typecheck passed; supported and failed claims, adjacent accessible evidence, queued-between-calls state, agent-response SSE, and identity dedup are covered; scenario-data has zero diff from the Phase A commit.
- Phase B full backend regression: 761 passed, 2 skipped, 7 deselected.
- Task 14 clean-tree baselines: backend 762 passed, 1 skipped, 7 deselected; PostgreSQL 45 passed; frontend 56 files / 325 tests; Playwright 46 passed; Alembic zero diff; lint clean apart from three pre-existing Fast Refresh warnings.
- Task 14 deterministic evaluation: 11/11 authoritative double cases passed, 100% tool routing, explicitly demonstration-only and not release-gate eligible.
- Gate A regeneration bound to `a3bbebf`: all eight readiness checks passed, `gate_a_passed: true`, `blocking: []`; generated report committed separately as `d346cb7`.

### Implementation Plan

- Phase A follows the story's seam-first order: strengthen evidence contracts, add value-free grounding contracts, compute through one governed capability, verify citations in a separate gate, add opt-in strict adapter output, then prove the seam with deterministic golden cases.

### Completion Notes List

- Task 1: versioned `EvidenceRefV1` per the normative contract minimum and added the single exhaustive projection-to-evidence group mapping; `overview` deliberately maps to no visible evidence group.
- Task 2: added frozen, versioned, framework-free contracts for value-free claim proposals, ordered strict answers, computed claims, and per-claim persisted failure states.
- Task 3: shipped the four-metric closed vocabulary through `scheduling_compute`, exhaustive bounded paging, half-open minute arithmetic, exact consumed-row locators, and deterministic content-addressed result IDs.
- Task 4: added fail-closed citation verification with argument/version checks, exact target resolution, Unicode-decimal prose rejection, distinct per-claim failures, and no-retarget preservation.
- Task 5: made structured answers opt-in, kept default text outcomes unchanged, returned typed owned answers without repr leakage, and filtered framework output tools by the agent-derived name.
- Task 6: added the independent grounding evaluator and exactly four scheduling-compute cases covering supported, version-mismatch, missing-evidence, and argument-mismatch outcomes with stable locator IDs.
- Task 7: wired explicit test/OpenRouter/Google runtime models from the owned configuration, kept injected doubles authoritative, and updated the deferred-work exposure record.
- Task 8: separated retryable argument errors from terminal capability/timeout failures in both governed modules and closed the retry-loop ledger item.
- Task 9: added the single column-scoped agent-run status grant/revoke revision and verified all other columns plus DELETE remain denied.
- Task 10: made planner-message/agent-response explicit discriminated variants, persisted and rehydrated grounded claims, preserved string sequences, re-pointed the reserved-variant guard, and regenerated OpenAPI/types.
- Task 11: added a conversation-scoped execute endpoint with short RLS claim/finalize transactions, runtime execution outside transactions, trusted grant/dependency composition, terminal failure handling, and mechanical detached-work guards.
- Task 12: rehydrated a bounded owned history from persisted visible activities only; raw framework transcripts and `AgentTurnV1` persistence remain deliberately deferred to Epic 4.
- Task 13: rendered grounded responses with structurally adjacent evidence controls, visible per-claim failures, dual-event SSE handling, and a send-then-execute client flow that exposes the queued state.
- Task 14: re-derived every baseline, verified every zero-diff fence, regenerated Gate A from fresh clean-tree JUnit artifacts, and recorded no story-specific evidence because no measured AC requires one.

### File List

- _bmad-output/implementation-artifacts/2-7-ground-schedule-claims-in-exact-evidence.md
- _bmad-output/planning-artifacts/sprint-change-proposal-2026-08-13.md
- backend/application/contracts/evidence_ref.py
- backend/application/contracts/grounding.py
- backend/application/contracts/agent_runtime.py
- backend/agent/runtime.py
- backend/application/grounding/__init__.py
- backend/application/grounding/evidence_groups.py
- backend/application/grounding/calculators.py
- backend/application/grounding/gate.py
- backend/application/capabilities/installed.py
- backend/application/capabilities/scheduling_compute.py
- backend/application/capabilities/scheduling_inspect.py
- backend/application/capabilities/demonstration.py
- backend/tests/test_evidence_ref.py
- backend/tests/test_grounding_contracts.py
- backend/tests/test_scheduling_compute.py
- backend/tests/test_scheduling_inspect.py
- backend/tests/test_demonstration_capability.py
- backend/migrations/versions/c7d6e5f4a3b2_grant_agent_run_status_update.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_identity_role_boundaries.py
- backend/tests/test_evidence_binding.py
- backend/application/contracts/activity.py
- backend/adapters/postgres/conversation.py
- backend/api/schemas.py
- backend/api/routers/conversations.py
- backend/tests/test_conversation_contracts.py
- backend/tests/test_conversations_api.py
- backend/tests/test_conversation_stream_api.py
- backend/tests/test_conversations_postgres.py
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- backend/tests/test_grounding_gate.py
- backend/tests/test_agent_runtime_adapter.py
- backend/evals/cases.py
- backend/evals/doubles.py
- backend/evals/evaluators.py
- backend/evals/grounding.py
- backend/evals/report.py
- backend/evals/README.md
- backend/evals/golden/scheduling_compute/supported.json
- backend/evals/golden/scheduling_compute/version-mismatch.json
- backend/evals/golden/scheduling_compute/missing-evidence.json
- backend/evals/golden/scheduling_compute/argument-mismatch.json
- backend/tests/test_evaluation_harness.py
- _bmad-output/implementation-artifacts/deferred-work.md
- backend/tests/test_capability_conformance.py
- backend/tests/architecture/test_agent_runtime_boundaries.py
- backend/application/ports/conversation.py
- backend/application/capabilities/deps.py
- backend/application/use_cases/execute_turn.py
- backend/adapters/postgres/short_transaction_projection.py
- backend/agent/capability_tools.py
- backend/agent/translate.py
- backend/api/deps.py
- backend/tests/architecture/test_execute_turn_boundaries.py
- backend/tests/test_execute_turn_use_case.py
- frontend/src/api/conversations.ts
- frontend/src/hooks/useSendMessage.ts
- frontend/src/hooks/useSendMessage.test.tsx
- frontend/src/hooks/useConversationStream.ts
- frontend/src/features/chat/ActivityTimeline.tsx
- frontend/src/features/chat/ActivityTimeline.test.tsx
- evidence/story-1.11/gate-a-readiness-report.json
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

| Date | Change |
|---|---|
| 2026-08-12 | Story created; seven creation decisions recorded, one honest gap raised, framework behaviour verified against the installed 2.27.0 lock. |
| 2026-08-12 | Restructured into Phase A / CHECKPOINT / Phase B / Phase C so the split boundary is built in rather than remembered; evaluator + golden cases moved into Phase A as Task 6; mechanical guards added for traps #7 and #8, which until now rested on prose alone; Task 12 (history rehydration) confirmed required rather than optional; `deferred-work.md:106` scheduled for in-place re-annotation because Task 7 makes it reachable. |
| 2026-08-12 | Gate changed from an unconditional stop to a reporting gate with four named halt conditions, so it works in an unattended `bmad-dev-auto` / `bmad-loop` run; restated in both the story and `sprint-status.yaml` that this remains ONE BMAD story and the phases are not a split. |
| 2026-08-13 | Decision 2 amended before implementation (correct-course, zero code written): the model now **cites** an application-computed `result_id` instead of asserting a value; calculators ship as the governed `scheduling_compute` capability; the gate **verifies citations** rather than recomputing; prose segments may carry no bare numerals. Tasks 2, 3, 4, 6 and the traps list updated to match. No AC, PRD, epic, architecture, or UX change — AD-11's `produce` branch and AR11's three named failures are satisfied as written. See `sprint-change-proposal-2026-08-13.md`. |
| 2026-08-13 | Phase B completed: configured runtime construction, stable capability failures, column-scoped status grant, durable response activity, request-path execution, persisted-history rehydration, and grounded chat rendering. |
| 2026-08-13 | Task 14 completed: full regression and fences passed; Gate A regenerated from clean-tree measurements and passed with no blockers; story moved to review. |
