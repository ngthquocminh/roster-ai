---
baseline_commit: 4e2b8126c9efd41ffc55fd9ac66d6c9b4710935f
---

# Story 2.7: Ground Schedule Claims in Exact Evidence

Status: ready-for-dev

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

- [ ] Add `schema_version: str = SCHEMA_VERSION` to `EvidenceRefV1` with a module-level
      `SCHEMA_VERSION = "1"`, matching `contracts/stream_cursor.py`'s house style.
- [ ] Extend `backend/tests/test_evidence_ref.py:66-78`'s field-order assertion to twelve fields.
      Add a one-line comment naming the spine's *Normative contract minimums* as the reason, so a
      future reader does not mistake it for churn.
- [ ] Add the `EvidenceGroupV1 ↔ ScenarioFactGroupV1` mapping in exactly one module.
- [ ] Test: the mapping is exhaustive in both directions, derived from `typing.get_args` on both
      `Literal`s — not from a hand-copied list. Adding a member to either side without the other
      must fail.
- [ ] Boundary: `overview` has no planner-facing evidence group. Decide and assert what the mapping
      does with it (omit it explicitly; do not let it fall through to a `KeyError` at claim time).

### Task 2 — Grounding contracts (AC: 1, 3)

- [ ] New `backend/application/contracts/grounding.py`, house style per `stream_cursor.py`: `from
      __future__ import annotations`, `SCHEMA_VERSION = "1"`, frozen dataclasses only, `V1` suffix
      on every type including `Literal` aliases, a docstring that explains *why the shape is this
      shape* with AD numbers, explicit `__all__`.
- [ ] `MetricV1` — the **closed** metric vocabulary (Task 3 fixes the members). It lives **here, in
      contracts**, and Task 3's capability imports it: `capability_manifest.py`'s docstring fixes the
      dependency direction as *capabilities → contracts*, and inverting it for a vocabulary would put
      an application contract behind a capability module.
- [ ] `ClaimProposalV1` — what the model proposes: metric, arguments, and the **`result_id` it
      cites**. It carries **no value**: under Decision 2 the value is the capability's, and a field
      the model could fill with a number is a field that will eventually render one.
- [ ] `ClaimProposalV1` is **untrusted model output** — say so in the docstring, as
      `AgentToolCallProposalV1`'s already does for tool names. The citation is the untrusted part
      now: a `result_id` is a claim *about* provenance, not proof of it, and Task 4 is what makes it
      proof.
- [ ] `GroundedAnswerV1` — the strict output type: ordered segments of prose and claim proposals.
- [ ] `GroundingFailureV1` — one of `missing_evidence`, `unauthorized_evidence`,
      `version_mismatch`, `calculation_failed`, `uncited_claim`, as a `Literal`. AD-11
      (`ARCHITECTURE-SPINE.md:154`) and AR11 (`epics.md:157`) each name exactly **three** causes —
      missing, unauthorized, version-mismatched — and those three must stay distinguishable and must
      not be collapsed.
- [ ] The last two are this story's own additions and are **mechanical, not evaluative**:
      `calculation_failed` is the capability raising (truncation, budget, timeout), and
      `uncited_claim` is a claim node with no `result_id` or a bare numeral found in a prose segment
      (Task 4). **Neither is a judgement about whether a number "looks right"** — there is no failure
      type meaning *"the model's arithmetic disagreed"*, because under Decision 2 the model performs
      no arithmetic.
- [ ] `GroundedClaimV1` — computed value, unit, `tuple[EvidenceRefV1, ...]`, and either a supported
      verdict or a `GroundingFailureV1`.
- [ ] `GroundedResponseV1` — the persisted, planner-visible result: segments, claims, and the
      pinned `scenario_version_id`.
- [ ] Nothing in this module imports `fastapi`, `pydantic_ai`, or `sqlalchemy`.
      `tests/architecture/test_agent_runtime_boundaries.py:380-394` parametrizes contract modules by
      name "so a future refactor that deletes them fails loudly" — **add this module to that list**.

### Task 3 — Application calculators, exposed as the `scheduling_compute` capability (AC: 1)

- [ ] New `backend/application/grounding/calculators.py` (the spine names a "grounding service" at
      `ARCHITECTURE-SPINE.md:436`; this is it).
- [ ] Ship a **small, real, closed** metric set that answers the primary Wednesday investigation
      question (`epics.md:734-737`, EXPERIENCE.md:253). Suggested and sufficient:
      required demand minutes for a family/task in a window; staffed minutes from baseline
      assignments in the same window; the shortfall between them; count of workers qualified for a
      task. Four is enough — do not invent a fifth to look complete.
- [ ] Each calculator returns value + unit + the `EvidenceRefV1`s of the records it actually read.
      A locator for a record the calculation did not consume is a false citation.
- [ ] **Page to exhaustion** (Decision 4). Drain via `next_cursor` under an explicit bound; assert
      completeness against `matching_count`; **raise** on truncation.
- [ ] Test that fails on truncation: a stub reader holding more rows than one page, asserting the
      computed total covers every row. Then confirm the test is non-vacuous by checking it goes red
      against a single-page implementation.
- [ ] Consume only `application/contracts/scenario_projection.py` records. No SQL, no fixture JSON,
      no re-derivation (AD-4).
- [ ] Units are explicit and asserted. `AssignmentV1`/`DemandIntervalV1` carry **integer minutes**
      (AD-20's half-open `[start_minute, end_minute)`); "worker-hours" in planner copy is a
      presentation conversion at one boundary, and mixing the two is a wrong number that renders
      confidently.
- [ ] Half-open interval overlap is the arithmetic here. Test the boundary cases explicitly:
      touching-but-not-overlapping (`a.end == b.start`), fully contained, partial on each side.
- [ ] New `backend/application/capabilities/scheduling_compute.py`, in `scheduling_inspect.py`'s
      exact shape: `CAPABILITY_NAME`, typed error classes with `code`, a module-level `ERROR_CODES`,
      `SchedulingComputeRequestV1` / `SchedulingComputeResultV1`, a `SCOPE_CONTROLS` mapping, and a
      manifest factory that imports `default_settings` **inside** the function (`application/**`
      stays importable without process configuration).
- [ ] The handler delegates to `application/grounding/calculators.py` — it does not compute. This
      mirrors `scheduling_inspect`, whose handler delegates to `use_cases/read_scenario_facts.py`.
- [ ] `risk_class="inspect"`, **not `"compute"`**. AR5's `compute` class is the solver — PRD §4.8 #3,
      *"start bounded CP-SAT optimization"*, which Epic 3 owns. A read that derives a total changes
      nothing and must not claim solver-grade authority. Its own `required_feature_policy`
      (`scheduling_compute_enabled`), mirroring `scheduling_inspect_enabled`.
- [ ] Register in `installed.py`'s `_INSTALLED_FACTORIES` — one line, per that module's *"One line
      per governed capability"* rule. Duplicate-name and manifest validation are already enforced
      there.
- [ ] **`scheduling_inspect` shows a zero-line diff.** Its docstring's *"This capability never
      computes a metric"* stays true, and Story 2.5's boundary is preserved rather than quietly
      widened.
- [ ] `result_id` is **derived, not random**: the RFC 8785 canonical-JSON SHA-256 hash of
      `(metric, canonical arguments, scenario_version_id)` — the hashing convention AR20 already
      fixes for this repository.
- [ ] **Why this is load-bearing and not a detail:** golden cases drive a deterministic model double
      whose turns are *authored* (`ScriptedModelTurn`). A scripted turn must be able to **cite a
      `result_id` written into the case file**. A per-call UUID would make every grounded case
      unwritable, and the failure would surface late — after Task 6's cases are already being
      authored. A content hash is stable across runs, so a case file can name it. Same reasoning as
      the existing rule that `expected_evidence_refs` must carry no per-run UUID.
- [ ] Test: two identical calls in one turn yield the same `result_id`; calls differing only in
      window or metric yield different ones.
- [ ] `SchedulingComputeResultV1` is a **capability result**, not `MetricSetV1`. AR20 names
      `MetricSet` as its own contract and the *honest gap* section assigns it to Epic 3. Do not name,
      shape, or import this type as if it were that one.

### Task 4 — The grounding gate (AC: 1, 3)

- [ ] New `backend/application/grounding/gate.py`. Input: a `GroundedAnswerV1` plus trusted deps.
      Output: a `GroundedResponseV1`.
- [ ] Input gains this turn's **capability results**, keyed by `result_id`. The gate performs **no
      computation** — Decision 2 puts the single calculation in Task 3's capability, and a second one
      here would reintroduce exactly the divergence this design removes.
- [ ] For each `ClaimProposalV1`, in order, stopping at the first failure:
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
- [ ] Version mismatch reuses `scheduling_inspect.py:228-237`'s shape — do not invent a second
      convention.
- [ ] **A prose segment containing a decimal digit fails the answer.** Without this the grounding
      invariant is not actually total: the model can write *"you're short about two hours"* in prose,
      bypass every claim node, and render an ungoverned number with no locator. No other task closes
      this hole.
- [ ] The rule is **blunt on purpose**: reject any Unicode decimal digit in a prose segment,
      fail-closed. Every number the answer needs is a claim node, and the renderer draws windows and
      identifiers from claim arguments rather than from prose.
- [ ] If Task 6's authored cases show this is too strict to write natural prose against, the
      relaxation must be a **declared allow-list with its own test** (and a comment naming what it
      admits and why) — never a quiet widening of the pattern. Record it in `SCOPE_CONTROLS` either
      way.
- [ ] **Never retarget.** Test: a claim whose record does not resolve in the cited version fails,
      and no emitted `EvidenceRefV1` names a different `record_id` or `scenario_version_id`.
- [ ] Test: one failed claim among three leaves the other two supported, with their evidence intact
      (AC3's "safe saved content is preserved").
- [ ] Record the coverage reduction as a `SCOPE_CONTROLS`-style `Mapping[str, str]` where every
      value states what the control covers **and** what it does `NOT COVER`, asserted by a test —
      the `scheduling_inspect.py:36-60` pattern. Include the schedule/run-version gap from the
      *honest gap* section here.

### Task 5 — Opt-in structured answer on the adapter (AC: 1)

- [ ] `PydanticAIAgentRuntime.__init__` accepts `answer_type: type | None = None`. `None` must
      reproduce today's construction **exactly**.
- [ ] When supplied, construct `output_type=[answer_type, DeferredToolRequests]` — strict, no `str`
      (verified: `allow_text_output` becomes `False`, which is the fail-closed edge in Decision 2).
- [ ] `AgentRunOutcomeV1` gains a typed optional `answer` field. Do not smuggle the answer through
      `output_text` as a `repr`.
- [ ] Exclude the framework output tool from `_tool_results(turn)` (`runtime.py:308-318`).
      **Derive the name** from the agent's own output-tool set rather than hardcoding
      `"final_result"` — a hardcoded framework name in an owned adapter is the AD-19 leak this
      package exists to prevent.
- [ ] Test: with `answer_type=None`, an existing golden case produces a byte-identical
      `AgentRunOutcomeV1` to today's. This is the regression fence for Decision 3.
- [ ] Test: a strict-answer run whose model emits prose raises `AgentRuntimeError`, cause preserved.
- [ ] `application/**` gains no `pydantic_ai` import. The answer type is an application contract
      passed *in*; the framework wiring stays in `backend/agent/`.

### Task 6 — The grounding evaluator and its golden cases (AC: 3)

- [ ] New `GroundingEvaluator` implementing the existing `Evaluator` Protocol
      (`evals/evaluators.py:27-30`) — the extension point Story 2.2 shipped for exactly this.
      Story 2.2's Task 3 forbade a second evaluator and named Story 2.7 as the owner of this one.
- [ ] It asserts `case.expected_evidence_refs` against the emitted locators **and** the oracle
      result (AC3's two clauses). `expected_evidence_refs` exists on `GoldenCase` (`cases.py:64`)
      and is currently **evaluated nowhere in the repository** — `deferred-work.md:115` names this
      story as the owner that closes the grounding half. Close that half; the visible-state half
      stays open and belongs to Story 2.9.
- [ ] Choose and document the locator's stable string form for `expected_evidence_refs`. It must not
      contain a UUID that changes per test run, or the cases are unmaintainable.
- [ ] Contribute golden cases with **non-empty** `expected_evidence_refs`, one per verified path: one
      **supported** claim; one **version-mismatch** (result carries a version other than the pin);
      one **missing-evidence** (the scripted turn cites a `result_id` no call produced); one
      **argument-mismatch** (a real result cited on a claim whose window or metric differs from the
      originating call — the failure Task 4 exists to catch, and the only one that would otherwise
      render a true number against the wrong question).
- [ ] Each scripted turn cites a `result_id` **written literally into the case file**. Task 3's
      content-hash derivation is what makes that possible; if a case cannot be authored because the
      id is unpredictable, that is Task 3 regressing, not a case-authoring problem.
- [ ] **Tag them `capability="scheduling_compute"`** — that is the tool they route (Task 3). Add
      `"scheduling_compute"` to `MVP_PRODUCT_CAPABILITIES` (`test_evaluation_harness.py:316`) as a
      **product** capability: it is item #1 of PRD §4.8's catalogue (*"inspect the selected scenario,
      including … coverage … evidence"*), so it is not exempt like `demonstration`.
      `test_every_capability_meets_the_nfr28_four_case_floor` is **designed** to fail on an
      unclassified capability; making it pass by classification is the intended path, not a
      workaround.
- [ ] NFR28's *"≥4 per allowed capability"* is met by exactly the four cases above — **at the floor,
      deliberately**. `epics.md:1527` forbids padding. A reviewer removing one of the four takes the
      capability below the floor, and that test is what says so.
- [ ] The new manifest's `evaluation_fixtures` names these four case files by path, as
      `scheduling_inspect`'s does. `generate_demonstration_report` runs every committed case and
      raises on an uninstalled capability (`report.py:186-189`) — Task 3's `installed.py`
      registration is what keeps it green.
- [ ] `GroundingEvaluator` remains a **second evaluator**, now over `scheduling_compute`:
      `ToolRoutingEvaluator` keeps judging routing, and grounding is judged separately. Story 2.2's
      "no second evaluator until 2.7" fence is satisfied by adding exactly one.
- [ ] **Do not pad toward NFR28's 50-case Gate B aggregate** (`epics.md:1527`). Contribute what the
      ACs need.
- [ ] Extend `backend/evals/README.md` with a Story 2.7 paragraph in the existing style.
      `test_readme_documents_exact_contribution_shape_and_owners` (`:374-379`) reads that file —
      check which literals it pins before editing.
- [ ] **Do not regenerate** `evidence/story-2.2/evaluation-harness-demonstration.json`. Story 2.5 and
      2.6 both recorded this rule; the file is frozen and pins case files by path and sha256.
- [ ] `generate_demonstration_report` must still pass with the new cases present
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

- [ ] Commit Phase A as its own coherent commit. Phase A must be green on its own: full backend
      suite, `test_evaluation_harness.py`, and the new grounding suites.
- [ ] Report these five things, as numbers, not adjectives:
      1. Which metrics shipped in the closed vocabulary, and which the ACs turned out not to need.
      2. **Whether the paging test is non-vacuous** — state that it was run against a single-page
         implementation and observed RED. Trap #1 is the whole reason this checkpoint exists; a
         paging test that was never seen to fail proves nothing.
      3. How many golden cases were contributed, by outcome type, and confirmation that
         `test_every_capability_meets_the_nfr28_four_case_floor` is still green.
      4. Anything in the *honest gap* section that turned out to be wrong when met in code.
      5. Elapsed effort on Phase A versus the estimate, and the revised estimate for Phase B.
- [ ] **Then apply the continue rule.** This checkpoint is a *reporting gate*, not an unconditional
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
- [ ] **What halting means:** Phase A is already a coherent, acceptable deliverable — it satisfies
      AC1 in full plus AC3's evaluation-fixture clause. So the escalation is a real question with a
      real option: keep this story at Phase A and move Tasks 7–14 into a new story, or extend. That
      decision is the human's and needs the numbers above; do not take it unilaterally, and do not
      start Phase B merely to avoid raising it.

---

## Phase B — Request path and rendering (Tasks 7–13)

### Task 7 — `create_agent_runtime()` wires a real model (AC: 1) — closes `deferred-work.md:102`

- [ ] `AgentRuntimeConfig.model` / `.api_key` are currently stored and never read; `self._model` is
      only ever set by the constructor kwarg. Wire them into a real PydanticAI model.
- [ ] Keep the injected-`model` seam intact and winning: every existing test supplies a
      `FunctionModel` double and must keep working unchanged.
- [ ] `AGENT_RUNTIME_MODEL` defaults to `"test"` (`settings.py:175`). Decide what that resolves to
      and make it explicit — a default that silently constructs a network-capable client is how a
      keyless CI run starts making live calls. `models.ALLOW_MODEL_REQUESTS = False` in the eval
      harness protects the harness, not the API.
- [ ] Close the ledger entry with a note naming the commit.
- [ ] **Do not** add a live-provider test. `deferred-work.md:106`'s unwrapped-transport-exception
      item stays open and needs live coverage that NFR26 keeps out of normal CI.
- [ ] **Re-annotate `deferred-work.md:106` in place — do not carry it forward silently.** That item
      asks whether a raw `httpx`/`openai`/`google-genai` exception could cross the seam unwrapped
      past `except AgentRunError`. It was written when *no endpoint called `create_agent_runtime()`*,
      so the question was theoretical. This task makes a real provider client reachable from a real
      request for the first time: **the item does not close, but its exposure changes from
      hypothetical to live-and-untested.** Record that, following the in-place re-annotation
      precedent Stories 2.4 and 2.5 set for a changed premise, and restate the owner as the first
      story that adds live-provider coverage.

### Task 8 — A capability timeout stops being a retryable argument error (AC: 1) — closes `deferred-work.md:5`

- [ ] `SchedulingInspectError`'s base `code` is `invalid_query`
      (`scheduling_inspect.py:63-67`), and `retryable_error_codes = frozenset({"invalid_query"})`
      (`:273`). The timeout overrun at `:222-226` raises the **base** class, so it reaches the model
      as `ModelRetry("invalid_query: inspection exceeded the 5.0s budget")`. The model "fixes"
      arguments that were never wrong, reissues the same slow query, and burns the wall-clock budget
      the timeout existed to protect.
- [ ] Give the overrun its own non-retryable code, declared in `ERROR_CODES` and therefore in the
      manifest. `runtime.py:192-196` already rejects any code absent from a granted manifest, so a
      typo fails loudly.
- [ ] Check `DemonstrationError` for the same generic-base-with-a-retryable-code shape and fix it if
      present — the ledger entry names it explicitly.
- [ ] Test: a timed-out capability call produces a terminal failure, not a retry loop.
- [ ] The ledger names Story 2.7 as an owner because this story creates the request path that can
      observe the loop. Close it.

### Task 9 — Migration: `UPDATE (status)` on `agent_run` (AC: 3)

- [ ] New Alembic revision on top of `a4f92d7c8e31`. `GRANT UPDATE (status) ON agent_run TO
      shiftmind_runtime` — column-scoped, mirroring `GRANT UPDATE (resource_version) ON conversation`
      (`a4f92d7c8e31_add_durable_conversations.py:100`). Nothing else.
- [ ] The `downgrade()` revokes it, matching `:104`.
- [ ] **No new columns.** The terminal reason and evidence live in the `agent_response` activity
      payload (AD-20's `ActivityItemV1` row). Adding `failure_reason`/`completed_at` to `agent_run`
      duplicates that record in a second place with no acceptance benefit.
- [ ] The existing `ck_agent_run_status` CHECK already admits all seven AD-7 statuses
      (`schema.py:306`) — do not touch it.
- [ ] **A migration is safe for existing evidence, verified:** Story 1.11's review made the
      `schema_version` audit rule *monotone* (`evidence_binding.py:610-621` — the recorded revision
      must lie on the migration chain, not equal head). The six committed evidence files stay valid.
      This is why Story 2.5's Decision 1 objection to a migration no longer applies.
- [ ] Extend `test_postgres_schema.py` / `test_identity_role_boundaries.py` in their existing shape:
      the runtime role can update `status` and still **cannot** update any other `agent_run` column,
      and still cannot `DELETE`.
- [ ] `uv run --project backend alembic check` from the **repository root** — not from `backend/`;
      `deferred-work.md:117-126` records exactly that mistake and its cost.

### Task 10 — `agent_response` becomes a real activity variant (AC: 2, 3)

- [ ] Make `ActivityItemV1` discriminated. `planner_message`'s serialized payload must stay
      **byte-identical** — `_payload_to_json` (`conversation.py:266-278`) writes rows that are
      already committed in developer databases and pinned by
      `test_conversation_contracts.py`/`test_conversations_postgres.py`.
- [ ] `agent_response` payload per AD-20: visible summary + evidence refs. Concretely: the
      `GroundedResponseV1` segments, each claim's computed value/unit/verdict, and its
      `EvidenceRefV1[]`.
- [ ] Writer and reader: extend `_payload_to_json` and `_activity_from_payload`. An unknown
      `activity_type` must still raise `UnsupportedActivityPayloadError` (`:281-286`) — the closed
      vocabulary keeps its teeth.
- [ ] `ActivityItemOut` (`api/schemas.py:121-136`): `message_id` and `text` are currently required
      and are `planner_message`-only. Make the variant explicit in the published schema rather than
      loosening both fields to optional and letting the discriminant become advisory.
- [ ] `sequence` stays a **JSON string** on every variant. Story 2.3's trap: a JSON number becomes an
      IEEE-754 double in the browser and poisons Story 2.4's resume cursor.
- [ ] **`test_an_unrenderable_activity_variant_fails_typed_not_as_a_key_error`
      (`test_conversations_postgres.py:519-544`) uses `agent_response` as its unrenderable probe**
      and will go red the moment this story makes it renderable. Re-point it at a discriminant that
      is *still* reserved — `comparison` and `approval_request` are Epic 4's and safest — and update
      its docstring from "Seven of AD-20's eight discriminants" to six. Do **not** delete it: it is
      the only proof that an unknown payload fails typed instead of taking the timeline down with a
      `KeyError`-turned-500. The sibling at `:507-516` probes `draft` and stays green untouched.
- [ ] Regenerate the published contract with the existing scripts — `npm run codegen:export` then
      `npm run codegen:types` (`frontend/package.json:15-16`). Do not hand-edit `frontend/openapi.json`
      or `frontend/src/api/schema.d.ts`.
- [ ] Test: an `agent_response` event round-trips write → read → `ActivityItemOut` → SSE frame with
      its evidence refs intact, through the **same** `_activity` projection the timeline uses
      (`conversations.py:95-101`) — a frame and a timeline item that drift apart break the client's
      merge silently.

### Task 11 — The execute-turn use case and endpoint (AC: 1, 3)

- [ ] New `backend/application/use_cases/execute_turn.py`, in the shape of `accept_turn.py`.
- [ ] Claim the run: `agent_queued → agent_running` under `FOR UPDATE` on the RLS-filtered row,
      mirroring `accept_turn`'s serialization (`conversation.py:179-190`). A run in any other status
      is refused with a stable problem response and **no** side effect.
- [ ] Compose `CapabilityGrantContextV1` and call `compose_granted_capabilities` through the
      **existing** `get_capability_registry` seam (`api/deps.py:93-101`). Grant is composed
      **before** the runtime is constructed; an ungranted capability is absent, never
      present-and-refusing (AD-2, Story 2.5 Decision 4).
- [ ] Build `AgentDepsV1` from trusted server-owned values only (`capabilities/deps.py`). Distinct
      UUIDs per identity field — sharing one made every scope assertion vacuous; that was Story 2.5
      review finding 8.
- [ ] `run_in_threadpool` around `run_sync`. The site-scoped transaction is **not** held across it
      (Decision 1).
- [ ] Route: `POST` under `/api/v1/conversations`. **Verify** `test_gate_a_mutation_audit.py` stays
      green — mounting under `/api/v1/scenarios` turns it red.
- [ ] Persist in one short second transaction: terminal `agent_run.status` + the `agent_response`
      persisted event at the next `sequence`, with `resource_version` bumped exactly as
      `accept_turn` does.
- [ ] A runtime failure (`AgentRuntimeError`, `timed_out`, `budget_exhausted`) still reaches a
      **terminal** `agent_run` status and leaves the accepted conversation history durable. Keep
      this minimal: the full failure taxonomy and its visible states are **Story 2.9's** AC3, not
      this story's. Do not build a refusal or clarification variant here.
- [ ] Test: two concurrent executions of one queued run produce exactly one terminal transition and
      one `agent_response` event.
- [ ] Test: the endpoint requires an authenticated session and is site-scoped; a cross-site
      conversation is a non-disclosing 404, unchanged from Story 2.3.

**Two mechanical guards, because traps #7 and #8 otherwise rest on nothing but Decision 1.** Story
2.6 faced the same problem — a rule stated only in prose that no functional test could catch — and
solved it with source-level assertions (the `_RENDERERS` check and the `importlib`/`pkgutil` ban).
Do the same here. A rule with no guard is a comment.

- [ ] **Guard for trap #7:** a test asserting the execute route's dependency set does **not** include
      `get_site_context`. Read it off the route's own signature or FastAPI's `dependant`, not off a
      hardcoded string. This is exactly the failure Story 2.4's Decision 1 described in prose and
      never guarded: correct at 40 ms, a connection-pool outage at 60 s.
- [ ] **Guard for trap #8:** an architecture test banning `BackgroundTasks`, `asyncio.create_task`,
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

- [ ] Build `AgentTurnRequestV1.history` from the conversation's **persisted `ActivityItemV1`
      timeline** — planner message text as `user`, prior `agent_response` visible summary as
      `assistant` — not from a stored raw transcript. AD-19: framework messages never become
      persisted contracts, and this keeps that true while making the product's central noun
      ("conversation") actually true for the agent.
- [ ] **Out of scope:** persisting `AgentTurnV1` itself. Raw-transcript provenance is AD-12's
      envelope and belongs to Epic 4. Say so in the Dev Notes so a reviewer does not read this task
      as half of it.
- [ ] This makes `to_framework_messages` (`translate.py:61-105`) reachable with owned records for the
      first time. The ledger item is about its **silent drops**: an unrecognized
      `AgentMessageV1.role` and an unrecognized `AgentPartV1.kind` fall through with no `else`. Fix
      both — raise, or drop with an explicit and tested decision — and close the entry.
- [ ] Bound the rehydrated history explicitly. An unbounded transcript is an unbounded token bill
      against a budget AD-7 says the application owns.
- [ ] `backend/agent/translate.py` has carried a zero-line-diff fence since Story 2.1 and **this
      task is the first authorized break of it.** Nothing else in that file changes.

### Task 13 — Chat renders the grounded response (AC: 2)

- [ ] `ActivityTimeline.tsx` currently renders `item.text` for every item (`:22`). Branch on
      `activity_type` and render the `agent_response` variant.
- [ ] Each **supported** claim renders its computed value with an **adjacent** `EvidenceLink`.
      `EvidenceLink` already exists (`components/primitives/EvidenceLink.tsx`) and has **no
      non-fixture call site** — this is its first real consumer. Its label is already
      `Evidence: {group} {record}{, fieldOrRange}, fixture {version}`, which is exactly UX-DR8's
      requirement; pass the planner-facing group name from Task 1's mapping, not the port's.
- [ ] Adjacency is structural, not decorative: the link is inside the claim's own element. A single
      message-level Sources list fails AC2 explicitly.
- [ ] `onActivate`/`href`: **Story 2.8 owns navigation.** Do not build jump/return, origin keys,
      focus restoration, or the exception panels here. Note in a comment that
      `deferred-work.md:68` flags an inert `EvidenceLink` with neither prop — decide what this story
      passes and make it deliberate.
- [ ] A **failed** claim renders its distinct state naming the cause, keeps its position, and
      renders no number. Sibling supported claims still render normally.
- [ ] No confidence score, no gauge, no percentage, no "approximately", no AI glow, no gradient, no
      pulsing evidence (UX-DR5, UX-DR32). Assert the absence — `index.test.ts` and
      `accessibility-contract.test.tsx` establish that pattern.
- [ ] Accessibility: the response block is distinguishable by author/type label (EXPERIENCE.md:85);
      the Evidence link is keyboard-operable with a visible focus ring and a self-describing
      accessible name. Extend the existing jsdom a11y suites; **do not** add new tooling.
- [ ] Chat code stays in `frontend/src/features/chat/`.
      `frontend/src/features/scenario-data/**` must show a **zero-line diff** — its directory is
      audited for mutation affordances by `scenarioDataBoundaries.test.ts`.
- [ ] Wire the execute call after send. Keep `agent_queued` visible between the two calls; the
      existing `runStatusLabel` (`ChatView.tsx:24-27`) already renders it literally.
- [ ] The stream merge is by `activity_id` (`useConversationStream.ts:281-283`) — the
      `agent_response` arriving from both the SSE frame and the timeline refetch must render **once**
      (UX-DR6). Test it; that dedup is the one Story 2.4 built and this is its first real exercise.

## Phase C — Close-out (Task 14)

### Task 14 — Regression, fences, and Gate A (AC: 1, 2, 3)

- [ ] **Re-derive baselines; do not trust the numbers below.** At `00f8ae0` (Story 2.6 post-review,
      clean tree): backend **705 passed / 1 skipped / 7 deselected** (postgres included), frontend
      **55 files / 322 tests**, Playwright **46 passed**, `alembic check` zero diff. The single skip
      is `test_evidence_binding.py`'s clean-tree self-skip, which is why a dirty-tree run reports
      704/2 instead — the skip count tracks tree state.
- [ ] Full backend suite, postgres suite, frontend vitest, typecheck, lint, Playwright.
- [ ] **Zero-line diff, verified per path, not assumed:** `backend/services/**`, `backend/domain/**`,
      `backend/engine/**`, `backend/llm/**`, `backend/ingest/**`, `backend/store/**`,
      `backend/application/ports/scenario_catalogue.py`,
      `backend/adapters/postgres/scenario_catalogue.py`,
      `backend/tests/test_gate_a_mutation_audit.py`, `frontend/src/features/scenario-data/**`.
      `ALLOWED_LEAKS` stays untouched — `deferred-work.md:130-147` keeps its owner.
- [ ] **No evidence file is owed.** No AC here carries a measured threshold, and NFR35's four rows
      belong to Stories 1.4, 1.5, 2.4 and 3.5 (`requirements-inventory.md:71`). Do not invent one.
- [ ] **Gate A must still be re-run per AR28** (`docs/GATE-A-RUNBOOK.md`). Expect the two-commit
      dance Stories 2.5 and 2.6 used: the gate cannot be run twice in a row because
      `gate_a_readiness.main()` dirties `evidence/` (`deferred-work.md:97`). Commit the code, then
      measure, then generate, then commit the evidence **separately**
      (`docs/EVIDENCE-CONVENTION.md`). Confirm `gate_a_passed: true`, `blocking: []`.
- [ ] Update `deferred-work.md`: **close** `:5` (Task 8), `:102` (Task 7), `:107` (Task 12);
      **partially close** `:115` (Task 6) with the visible-state half restated and reassigned;
      **re-annotate** `:106` (Task 7) without closing it;
      leave `:6`, `:7`, `:8`, `:106`, `:130-147` open and untouched.
- [ ] Record any new deferred item this story creates in the same file, with an owner and a revisit
      trigger.

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

### Completion Notes List

### File List

## Change Log

| Date | Change |
|---|---|
| 2026-08-12 | Story created; seven creation decisions recorded, one honest gap raised, framework behaviour verified against the installed 2.27.0 lock. |
| 2026-08-12 | Restructured into Phase A / CHECKPOINT / Phase B / Phase C so the split boundary is built in rather than remembered; evaluator + golden cases moved into Phase A as Task 6; mechanical guards added for traps #7 and #8, which until now rested on prose alone; Task 12 (history rehydration) confirmed required rather than optional; `deferred-work.md:106` scheduled for in-place re-annotation because Task 7 makes it reachable. |
| 2026-08-12 | Gate changed from an unconditional stop to a reporting gate with four named halt conditions, so it works in an unattended `bmad-dev-auto` / `bmad-loop` run; restated in both the story and `sprint-status.yaml` that this remains ONE BMAD story and the phases are not a split. |
| 2026-08-13 | Decision 2 amended before implementation (correct-course, zero code written): the model now **cites** an application-computed `result_id` instead of asserting a value; calculators ship as the governed `scheduling_compute` capability; the gate **verifies citations** rather than recomputing; prose segments may carry no bare numerals. Tasks 2, 3, 4, 6 and the traps list updated to match. No AC, PRD, epic, architecture, or UX change — AD-11's `produce` branch and AR11's three named failures are satisfied as written. See `sprint-change-proposal-2026-08-13.md`. |
