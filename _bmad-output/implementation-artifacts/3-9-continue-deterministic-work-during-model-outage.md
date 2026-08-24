---
baseline_commit: d833cf15c0d37c2be3e63a169c7df16a388a82cb
---

# Story 3.9: Continue Deterministic Work During Model Outage

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want saved work and manual optimization to remain usable when the model is unavailable,
So that conversational assistance is never the recovery or scheduling authority.

**This is a degraded-mode and proof story, not a new-capability story.** Nothing in it adds a
planner capability that does not already exist. It makes the peer surfaces behave correctly when
`AgentRuntime` or its provider fails, and it converts three architectural claims that are currently
only prose into tests that can go red:

1. Chat degrades to **read-only-plus-deterministic** instead of looking broken (AC1).
2. The deterministic solver path is **structurally independent** of `AgentRuntime` (AC2).
3. Telemetry export failure **neither authorizes nor blocks** product work (AC3).

**Half of FR8 already shipped and must not be rebuilt.** Story 1.7's third AC already proved
Scenario Data stays fully available with "no AgentRuntime dependency invoked" (`epics.md:522-527`,
tagged `FR8, partial`). Cite it; do not re-prove it.

**`epics.md:333` makes AC3 load-bearing for a later epic:** *"NFR10's telemetry independence is
already proven by Story 3.9."* Epic 5 does not re-prove it. If AC3 ships as prose, NFR10 has no
proof anywhere in the repository.

**Depends on, and consumes:** Story 2.1's `AgentProviderError` (already the by-type provider-outage
classifier); Story 2.9's `failed_outcome_for_exception` / `terminal_outcome` mapping, which already
turns a provider outage into a durable `TerminalOutcomeV1(reason="provider_error")`; Story 2.3/2.4's
conversation timeline and SSE replay; Story 3.1's `DraftCard` (revise/reject); Story 3.6's
`useStartScheduleRun` and the `POST /api/v1/schedule-runs` command; Story 3.7's `RunsTable` and its
Retry path; Story 1.6's `InlineAlert`, `StatusBadge`, `EmptyState` primitives.

**Unblocks:** Story 3.12 (the repair browser journey includes the outage path); Epic 5 (which
inherits NFR10 as proven).

**Scope summary:** One new backend read route (`GET /api/v1/agent-availability`) plus its
application use case. One new frontend hook and one new Chat degraded-mode surface. One new
architecture test module. Two new behavioral test groups (provider-outage request path,
telemetry-failure independence). **No migration. No new persisted contract.** No change to any
solver, proposal, or run command.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions.

| Fact | Where it is written |
|---|---|
| **Model outage disables only `AgentRuntime`.** "authenticated Scenario Data, saved results, and the manual deterministic solver path retain the same site, version, idempotency, and audit controls" | AD-15, final sentence (`ARCHITECTURE-SPINE.md:174-179`) |
| **No telemetry system authorizes or blocks product work.** PostgreSQL owns product/workflow state and append-only audit; CloudWatch owns AWS diagnosis; sanitized OTel/Logfire owns *optional* AI traces | AD-12, final sentences (`ARCHITECTURE-SPINE.md:156-160`) |
| FR8's own wording: "identify agent features as unavailable while preserving authenticated access to Scenario Data, saved results, provenance, and the manual deterministic solver workflow" | `epics.md:39` |
| NFR10: "Model-provider or Logfire failure must cause zero product-state corruption and zero authoritative-audit loss while supported manual and deterministic workflows remain available" | `epics.md:93` |
| **Required Chat outage behavior, verbatim:** "Model outage disables only composer/agent actions and links to Scenario Data, Runs/manual optimization, and saved Results." | `EXPERIENCE.md:123` (State Patterns → Chat → Error/unavailable) |
| **Required Runs outage behavior, verbatim:** "Model outage does not disable manual deterministic run." | `EXPERIENCE.md:125` |
| **Required Results outage behavior, verbatim:** "Model summary outage leaves deterministic result/evidence intact." | `EXPERIENCE.md:126` |
| **Approved outage copy, and the forbidden alternative:** *"Agent unavailable. Scenario Data, saved results, and manual optimization are still available."* vs. **"ShiftMind is offline."** | `EXPERIENCE.md:66` (Voice and Tone table) |
| **A full application API outage is NOT described as a model outage.** "Saved browser-visible content may remain read-only with a stale label; no offline writes or approvals are queued." | `EXPERIENCE.md:128` |
| **Evidence links keep resolving during an outage** because evidence navigation is application-owned; "No new agent claims are generated." | `EXPERIENCE.md:171` (Exception behavior → Model outage) |
| Flow 4's five steps are the acceptance walkthrough: Chat inline alert + durable conversation + disabled composer → Scenario Data → Runs' manual Run optimization → Run progress → Results | `EXPERIENCE.md:262-270` |
| Flow 4's failure path: **"manual solver is also unavailable → separate solver/service error, no conflation with model outage, no lost saved result"** | `EXPERIENCE.md:270` |
| `AgentProviderError` exists specifically so "the request path can classify a provider outage by TYPE" — never by string-matching a message | `backend/application/ports/agent_runtime.py:42-53` |
| A provider outage is **already durably persisted**, not surfaced as an HTTP error: `failed_outcome_for_exception` maps `AgentProviderError` → `AgentRunOutcomeV1(status="failed", failure_reason="provider_error", failure_source="agent")`, and `terminal_outcome` renders it as `TerminalOutcomeV1(status="failed", reason="provider_error", detail="The provider failed before the turn completed.")` | `backend/application/use_cases/execute_turn.py:137-141, 226-232, 249-252` |
| The `agent_run` table stores **`status` only** — there is no `failure_reason` column. The reason lives in the persisted activity event's `TerminalOutcomeV1` payload, exposed as `TerminalOutcomeActivityOut.outcome` | `backend/adapters/postgres/schema.py:298-309`; `backend/api/schemas.py:188-190` |
| `TimelineOut` already carries `latest_agent_run_status: str \| None`; the seven admitted statuses are fixed by `ck_agent_run_status` | `backend/api/schemas.py:230-236`; `schema.py:308` |
| The adapter's model resolution can fail **without any network call**: `_configured_model` raises `ValueError` for a model string that is neither `"test"` nor `"<provider>:<model-name>"` | `backend/agent/runtime.py:445-467` |
| `create_agent_runtime` reads only `agent_runtime_*` settings — never `llm_provider`/`llm_model` (two seams, two configurations, AD-19) | `backend/agent/runtime.py:470-500`; `backend/settings.py:86-95` |
| **Instrumentation is constructed content-disabled with no parameter to turn content on**, and the Logfire SDK is deliberately absent — "Story 5.1 owns telemetry export". `tracer_provider` is injectable and "does not change what is emitted" | `backend/agent/runtime.py:118-133`, and the `__init__` docstring at `:107-110` |
| `logfire` is already in `FORBIDDEN_ROOT_MODULES` for domain/application code | `backend/tests/architecture/test_agent_runtime_boundaries.py:53` |
| **A schedule run can only be started from an existing proposal.** `start_schedule_run` requires `body.proposal_id` and takes **no agent dependency** — its dependencies are the capability registry, proposal repo, scenario catalogue, and run repo | `backend/api/routers/schedule_runs.py:345-361` |
| **`proposal_repository.create_draft` is called from exactly one place: `application/use_cases/finalize_agent_run.py:55`.** The proposals router exposes only read / revise / reject — there is **no** proposal-creation route | Verified by grep; `backend/api/routers/proposals.py:99-141` |
| The two existing Run-optimization entry points are `DraftCard`'s button (`frontend/src/features/chat/DraftCard.tsx:308-318`, `variant="secondary"`) and `RunsTable`'s Retry on a retryable row (`frontend/src/components/runs/RunsTable.tsx:101-136`). Both call the same `useStartScheduleRun` mutation | Read directly |
| UX-DR35's Send-vs-Run-optimization visual discontinuity is already shipped and asserted; `Run optimization` is `variant="secondary"`, Send is primary | `deferred-work.md:204,210` (closed by Story 3.6) |
| `Composer` today has **no disabled-by-outage path**: `disabled={!draft.trim() \|\| isPending}` only (`:84`). Its failure `InlineAlert` retains the draft and links to Scenario Data (`:69-84`) | `frontend/src/features/chat/Composer.tsx:84, 69-84` |
| `ScenarioRuns` has **no Run optimization CTA of its own** — only Refresh, the stale label, `RunsTable`, and the pager | `frontend/src/routes/ScenarioRuns.tsx` (read in full) |
| Problem details are RFC 7807 via `api/problems.py:problem_response(status, code, title, detail)`; `getErrorStatus` / `getErrorCode` are the only sanctioned client-side accessors | `backend/api/problems.py:7-23`; `frontend/src/lib/errors.ts:44-62` |
| `USER_ERROR_COPY` is the fixed copy registry — components must render only its values so exception text never reaches JSX | `frontend/src/lib/errors.ts:1-30` |
| **There is no `AuditEnvelopeV1` implementation anywhere.** Audit is Epic 4's; `enqueue_compute` already carries `"NOT COVERED: audit:owned_by_epic_4"` | Verified by grep; `backend/application/use_cases/enqueue_compute.py:34` |
| `NOT COVERED: <area>:<reason>` markers in a `SCOPE_CONTROLS`-style mapping are the project's convention for a declared, deliberate absence | `backend/application/capabilities/scheduling_compute.py:40-90`; `backend/application/use_cases/enqueue_compute.py:25-40` |
| Manual assistive-technology verification is **descoped**; automated coverage is the only accepted accessibility proof. Durable state transitions announce through a **polite** live region | `EXPERIENCE.md:185-195` (Accessibility Floor) |
| Story 1.7 already proved the Scenario Data half of FR8 — "the full read-only view remains available because it calls the application scenario-read service directly **And** no AgentRuntime dependency is invoked" | `epics.md:522-527` |

### `docs/DOMAIN-MODEL.md` — read, and it does not bind this story

Per the standing rule, `docs/DOMAIN-MODEL.md` is cited rather than re-derived. **This story adds no
metric, reads no demand row, and computes no assignment-derived value.** It changes availability
signalling, control enablement, and test coverage only. No `family` argument is passed anywhere by
this story's new code, and no demand-vs-assignment comparison is introduced. §5's checklist
therefore has nothing to apply to — but if the dev agent finds itself reaching for a metric, stop:
that is out of scope and a sign the outage surface has been over-built.

---

## Acceptance Criteria

Verbatim from `epics.md:1067-1080`.

1. **Given** AgentRuntime or its provider is unavailable **When** the planner opens Chat **Then**
   durable conversation history remains visible, the composer/agent actions are disabled with narrow
   outage copy, and links to Scenario Data, Runs/manual optimization, and saved Results remain active
   **And** the full workspace is not described as offline. (FR8, UX-DR5, UX-DR25)

2. **Given** a selected fixture during model outage **When** the planner starts the existing manual
   deterministic solver flow **Then** it uses the same scenario projection, run snapshot, trusted
   site/version checks, budgets, job recovery, idempotency, CP-SAT engine, and evidence model
   **And** it does not invoke AgentRuntime. (FR8, AR15)

3. **Given** Logfire export is disabled or fails **When** manual or agent-originated deterministic
   work executes **Then** product state, solver behavior, saved results, CloudWatch diagnosis, and
   authoritative audit remain correct **And** telemetry failure neither authorizes nor blocks work.
   (NFR10, AR12)

---

## Decisions — resolved so the dev agent does not have to guess

### Decision A — Availability is reported by a new `GET /api/v1/agent-availability` route that makes **no provider network call**

AC1 fires "when the planner opens Chat" — *before* any send. Nothing in the repository can answer
"is the agent available?" today. Three candidate mechanisms, and why the third wins:

| Mechanism | Rejected because |
|---|---|
| Live provider probe (a real model call on Chat open) | Buys a model call, a new latency path, and a new failure mode per Chat open. AD-7 makes budgets application configuration; a probe outside any `AgentBudgetV1` is unbudgeted model spend. |
| Timeline-derived only (no new route) | Free, and the durable evidence is genuinely there. But a **brand-new conversation has no timeline**, so during a real outage the composer would render enabled — exactly the state AC1 forbids. |
| **Config validity + last observed provider failure (ADOPTED)** | Answers on open, costs one indexed read, and every input is either trusted configuration or persisted evidence — which AD-6 already makes authoritative. |

**Ship:** `GET /api/v1/agent-availability?scenario_id=<uuid>`, site-scoped like every other `/api/v1`
route, returning

```json
{ "available": false, "reason": "provider_error", "observed_at": "2026-08-24T04:11:09Z" }
```

`reason` is a closed set: `null` when available, otherwise `"not_configured"` or `"provider_error"`.

* **`not_configured`** — building the runtime raises. Call `create_agent_runtime(settings=settings)`
  inside a `try`; `_configured_model`'s `ValueError` (`runtime.py:449-453`) is the definitive,
  network-free "this deployment cannot reach a model" signal. `observed_at` is the request time.
* **`provider_error`** — the most recent terminal agent-run activity for this **site** carries
  `reason == "provider_error"` and is **newer than `agent_availability_recency_seconds`** (new
  setting, default `120.0`, positive-validated at process start exactly like the seven ceilings in
  Story 3.6 Decision 4). `observed_at` is that activity's timestamp.
* Otherwise `available: true, reason: null, observed_at: null`.

**The recency window is the whole point, not a hedge.** Read Trap 1 before implementing it.

Scope by **site**, not conversation: a provider outage is not per-conversation, and scoping to the
conversation would leave a new conversation blind — the exact hole that killed the timeline-only
option. `scenario_id` is required so the route resolves under the existing site-context dependency
and cannot be probed cross-site.

The route calls `create_agent_runtime` **only** to discover constructability, and never calls
`run_turn`. Say so in a comment; a future reader will otherwise "optimize" it into a probe.

### Decision B — Exactly one control is disabled in Chat; the deterministic ones stay **enabled**

This is the highest-value decision in the story. The naive implementation disables everything inside
Chat during an outage and **destroys AC2**, because the only Run-optimization control the planner can
reach lives on a `DraftCard` *inside the Chat timeline*.

| Control | During outage | Why |
|---|---|---|
| `Composer` Send + textarea | **DISABLED** | It is the agent action. `EXPERIENCE.md:123`, `:84`. |
| `DraftCard` → **Run optimization** | **ENABLED — do not touch** | The deterministic path. `EXPERIENCE.md:125`: "Model outage does not disable manual deterministic run." Disabling it fails AC2. |
| `DraftCard` → Revise / Reject | **ENABLED** | Proposal commands on `/proposals/{id}/revisions` and `/rejection`. Neither calls the agent. |
| `New conversation` | **ENABLED** | A durable PostgreSQL write with no agent call. Disabling it would describe the workspace as offline (AC1's **And**). |
| Evidence links, `ActivityTimeline`, `ConversationList`, timeline replay | **UNCHANGED** | `EXPERIENCE.md:171`: existing structured links keep resolving because evidence navigation is application-owned. |

Nothing outside Chat changes behavior. `ScenarioData`, `ScenarioRuns`, `ScenarioResults`,
`RunsTable`, and `useStartScheduleRun` are **not edited by this story** — their independence is
*proven* by AC2's tests, not created by new code. If the dev agent finds itself editing
`schedule_runs.py`, `enqueue_compute.py`, or `lease_worker.py`, the scope has been misread.

### Decision C — The outage surface is one `InlineAlert` above the composer, with a **Check again** action

Reuse `InlineAlert` (Story 1.6). Do **not** use `ReconnectBanner` — that primitive means "the event
stream dropped", a different state, and `EXPERIENCE.md:128` requires an API outage and a model
outage to stay distinguishable.

Copy is fixed, and derives from the approved row at `EXPERIENCE.md:66`:

* **title:** `Agent unavailable`
* **description:** `Scenario Data, saved results, and manual optimization are still available.`
* **action:** three real controls — Scenario Data (`/scenarios/:id/data`), Runs
  (`/scenarios/:id/runs`), and a `Check again` button that refetches availability.

Add these to `USER_ERROR_COPY` as an `agentUnavailable` entry rather than inlining strings, per
`errors.ts`'s stated rule. **Forbidden strings:** "offline", "ShiftMind is down", "try again later",
any spinner, any ETA, any anthropomorphic waiting (UX-DR5).

The composer's disabled textarea carries `aria-describedby` pointing at the alert's description, per
the Accessibility Floor's "errors are associated with affected controls". The alert renders in a
**polite** live region — never assertive: an outage the planner navigated into is not a destructive
transition, and `:190` forbids repeated chatter.

"Saved Results" is reached through Runs, not by a fourth link: `Results` requires a selected run
(`EXPERIENCE.md:42`), and a link to a disabled tab is a dead end — the same failure mode
`ChatView`'s existing `ErrorState` comment already calls out for 404s.

### Decision D — AC2's "existing manual deterministic solver flow" is the **existing** control on an **already-saved** proposal. Do not add proposal creation.

AC2 says *"starts the **existing** manual deterministic solver flow."* That flow is
`useStartScheduleRun` → `POST /api/v1/schedule-runs`, reached from `DraftCard` or `RunsTable` Retry.
It is fully functional during an outage because it takes no agent dependency
(`schedule_runs.py:350-361`).

**Do not add a manual proposal-creation route.** `create_draft` has exactly one caller
(`finalize_agent_run.py:55`), and FR9–FR11 — turning intent into a reversible draft — are Story
3.1's, already shipped through the agent. A new creation command would be a new authority surface
needing its own idempotency scope, capability grant, and validation, and AC2 does not ask for one.
See **Gap 1** for the honest consequence, which must be recorded, not papered over.

### Decision E — AC3 is proven at the **instrumentation seam that exists**, and its unimplemented clauses are marked NOT COVERED

The Logfire SDK is deliberately not installed (`runtime.py:126`, Story 5.1 owns export). AC3's
literal "Logfire export is disabled or fails" therefore has no SDK to disable. Drive the real seam:
`PydanticAIAgentRuntime`'s injectable `tracer_provider` (`runtime.py:118-133`).

Two proof cases, both using the deterministic model double and `opentelemetry-sdk` — already a
declared dev dependency and imported hard, never `importorskip`, by
`test_agent_runtime_adapter.py:614-620`:

1. **Export fails.** A `SimpleSpanProcessor` wrapping an exporter whose `export` raises. Run a turn.
   Assert the owned `AgentRunOutcomeV1`, the persisted activity, and the timeline are **identical**
   to the same turn with a working exporter. A raising exporter must not become an
   `AgentRuntimeError`.
2. **Export disabled.** `tracer_provider=None` (the constructor's own no-tracer branch). Assert the
   same outcome, and assert the deterministic path — `POST /api/v1/schedule-runs` → run row →
   `GET /schedule-runs/{id}/result` — is unaffected.

**Marked NOT COVERED, with owners, because no implementation exists to assert against:**

* `audit:owned_by_epic_4` — there is no `AuditEnvelopeV1` writer anywhere. AC3's "authoritative
  audit remain correct" cannot be proven. Reuse the exact marker string already in
  `enqueue_compute.py:34`.
* `diagnosis:cloudwatch_owned_by_epic_6` — no CloudWatch adapter exists.

Record both in the ledger and in Completion Notes. **Do not invent an audit or a CloudWatch double
to make AC3 look green** — a test asserting a fake's behavior proves nothing, which is exactly the
circularity `deferred-work.md:138` records removing from the Gate A suite.

### Decision F — AC2's independence is proven **structurally and behaviorally**, in a new architecture module

`tests/architecture/test_solver_boundaries.py` proves the opposite direction (solver libraries stay
inside `engine/`). Add `tests/architecture/test_model_outage_boundaries.py`, following that module's
`ast`-walking `_imports` idiom:

1. **Structural.** No module on the manual solver path imports `agent.*` or
   `application.ports.agent_runtime` — an exact allow-set of paths (`api/routers/schedule_runs.py`,
   `application/use_cases/enqueue_compute.py`, `application/capabilities/scheduling_compute.py`,
   `worker/lease_worker.py`, everything under `engine/`), declared as a frozen tuple so a new
   importer cannot silently join, exactly as `LEGACY_ENGINE_IMPORTERS` does at `:12`.
2. **Detector self-test.** A test proving the detector observes a forbidden import when handed one —
   mirroring `test_import_detector_can_observe_a_forbidden_boundary` at `:68`. Without it a broken
   matcher passes vacuously.
3. **Behavioral.** With `get_agent_runtime_factory` overridden by a factory that **raises on
   construction**, the whole manual flow still succeeds end to end. A structural test proves nobody
   imports the port; only this proves nobody reaches it at runtime.

---

## Traps — each one has cost a review cycle in this repository's history

**Trap 1 — The latch deadlock.** If `available: false` is derived from "the last agent run failed
with `provider_error`" *without* a recency bound, the composer is disabled → the planner cannot
attempt a turn → no newer outcome is ever written → **Chat is permanently disabled after one
transient failure**. The bounded recency window (Decision A) and the `Check again` action are both
required, and each closes a different half. Test the expiry explicitly: an activity older than the
window must report `available: true`.

**Trap 2 — Disabling `Run optimization` because it lives in Chat.** It is the deterministic path.
Disabling it breaks AC2 and contradicts `EXPERIENCE.md:125` verbatim. Assert it stays enabled while
the composer is disabled, **in the same test** — separate tests pass while the combination is wrong,
which is the failure mode Story 3.6's review finding at `:838` records.

**Trap 3 — Conflating an API outage with a model outage.** `EXPERIENCE.md:128` forbids it. If
`/agent-availability` itself fails (network down, 502, 401), that is **not** evidence of a model
outage. On an availability-query error the composer stays **enabled** and no outage alert renders —
fail *open* here, because failing closed would let one broken read disable the agent for a working
provider. This is the one place in the story where fail-open is correct; say so in a comment or a
reviewer will flag it as a fail-closed violation.

**Trap 4 — String-matching the failure reason.** `execute_turn.py:236-244` documents an earlier
revision that tested `"provider call failed" in str(exc)` and would have silently reclassified every
outage the day that literal was reworded. Read `reason == "provider_error"` off the typed
`TerminalOutcomeV1`; never parse `detail`.

**Trap 5 — Reading a `failure_reason` column that does not exist.** `agent_run` stores `status`
only (`schema.py:298-309`). The reason is in the activity payload. A query against
`agent_run.failure_reason` will not run against the real schema.

**Trap 6 — Letting the availability query gate the timeline.** Durable history must render even
while availability is pending or errored (AC1's first clause). Availability drives *control
enablement only*. Never put the timeline behind its loading state, and never render a skeleton over
saved content — `DESIGN.md:145`: "reconnecting state does not cover saved content."

**Trap 7 — A raising span exporter escaping as a run failure.** OTel swallows exporter errors by
design, but `SimpleSpanProcessor` exports on the calling thread. If the test observes an
`AgentRuntimeError`, that is a real AC3 defect in the adapter — fix the adapter, do not weaken the
test.

**Trap 8 — Adding `logfire` to satisfy AC3's wording.** It is in `FORBIDDEN_ROOT_MODULES`
(`test_agent_runtime_boundaries.py:53`) and Story 5.1 owns export. Importing it turns that
architecture test red.

---

## Honest Gaps — recorded, not solved here

### Gap 1 — During an outage with no saved draft, no new run can be started

`create_draft` has one caller, and it is inside the agent turn (Decision D). So a planner who hits an
outage **before** any draft exists for the scenario has nothing to run: Runs is empty, and the only
Run-optimization controls are attached to proposals and to retryable run rows.

This is a real limitation of FR8 as currently built, not a bug this story introduces. The story
handles it honestly rather than hiding it: the Chat alert links to Runs, and Runs' existing empty
copy ("No runs yet for this scenario.") already states the truth without promising a control that is
not there. **Do not add a Run-optimization CTA to `ScenarioRuns` that cannot resolve a proposal** —
a control that always errors is worse than its absence, and `EXPERIENCE.md:125`'s "when permitted"
qualifier is exactly this case.

**Owner / revisit trigger:** the first story that needs a planner-authored draft without an agent
turn. Ledger entry required.

### Gap 2 — AC3's audit and CloudWatch clauses have no implementation to assert against

Per Decision E: no `AuditEnvelopeV1` writer (Epic 4), no CloudWatch adapter (Epic 6). AC3 is proven
for product state, solver behavior, and saved results; the other two clauses ship as declared
`NOT COVERED` markers with owners. State this plainly in Completion Notes — a reviewer reading
`epics.md:333`'s "NFR10 is already proven by Story 3.9" needs to know precisely which parts are.

### Gap 3 — `available: true` is an absence of evidence, not a proof of reachability

By design (Decision A): no network probe. So `available: true` means "correctly configured, and no
provider failure observed recently" — not "the provider answered just now." A provider that goes
down between the availability read and the send produces an enabled composer and a failed turn,
which then surfaces the alert on the next read. That is the honest behavior, and it is the reason the
`Composer`'s existing draft-retaining failure alert (`Composer.tsx:69-84`) must be kept, not replaced.

---

## Tasks / Subtasks

- [x] **Task 1 — Availability use case and route (AC: #1)**
  - [x] `backend/application/use_cases/agent_availability.py`: a frozen `AgentAvailabilityV1`
        (`available: bool`, `reason: Literal["not_configured","provider_error"] | None`,
        `observed_at: datetime | None`) and a function taking the runtime factory, the conversation
        repository, the site id, and the recency window. **Not** in `application/contracts/` — it is
        never persisted and crosses no adapter boundary (AD-20 governs persisted contracts).
  - [x] Resolve `not_configured` by calling the injected factory inside `try`, catching `Exception`,
        and never calling `run_turn`. Comment why.
  - [x] Resolve `provider_error` from the newest terminal agent-run activity for the site whose
        typed `reason == "provider_error"` and whose timestamp is within the window. Add the
        repository read method if none fits; keep it site-scoped.
  - [x] `GET /api/v1/agent-availability` under the existing site-context and session dependencies.
        `scenario_id: UUID` required. Declare `_PROBLEM_RESPONSES` like its peers.
  - [x] `agent_availability_recency_seconds: float = 120.0` in `settings.py`, positive-validated at
        process start via the existing `_positive_float` helper and added to the validated-names
        list at `settings.py:39-44`.
  - [x] Regenerate the OpenAPI-derived frontend types.

- [x] **Task 2 — Backend tests for availability (AC: #1)**
  - [x] `not_configured` when the factory raises; `provider_error` when a recent terminal outcome
        carries it; `available: true` when the same activity is **older than the window** (Trap 1);
        `available: true` when the newest failure is `invalid_output` or `budget_exhausted`, not a
        provider error (Trap 4).
  - [x] Cross-site isolation: a `provider_error` at another site does not mark this site unavailable.
  - [x] The route never calls `run_turn` — assert against a factory whose runtime raises if
        `run_turn` is reached.

- [x] **Task 3 — Chat degraded mode (AC: #1)**
  - [x] `frontend/src/hooks/useAgentAvailability.ts` — a thin TanStack Query wrapper, `enabled` on a
        present `scenarioId`, no business logic (the established hook shape).
  - [x] `agentUnavailable` entry in `USER_ERROR_COPY` with Decision C's exact copy.
  - [x] `ChatView`: render the `InlineAlert` above `Composer` when and only when the query has
        resolved `available: false`. Never while pending or errored (Traps 3 and 6). Timeline,
        conversation list, `New conversation`, and every `DraftCard` control are untouched.
  - [x] `Composer`: new optional `disabledReason?: string` prop. When set, the textarea and Send are
        disabled and `aria-describedby` points at the alert description. **Preserve the existing
        draft-retaining failure alert and the synchronous `inFlight` latch** — neither is replaced.
  - [x] Verify by reading the rendered output that no forbidden string ("offline", ETA, spinner)
        appears.

- [x] **Task 4 — Frontend tests (AC: #1)**
  - [x] Composer disabled **and** `DraftCard`'s Run optimization still enabled, asserted in one test
        (Trap 2).
  - [x] Durable timeline renders while availability is pending, and while availability errors, with
        no alert and an enabled composer (Traps 3, 6).
  - [x] All three controls present and active; `Check again` refetches.
  - [x] `available: true` renders no alert at all.
  - [x] Extend `frontend/src/test/accessibility-contract.test.tsx`: the disabled composer is the
        **real** submit control (not a decoy — the defect recorded at
        `accessibility-contract.test.tsx:433`), it is associated with the alert, and the alert
        announces politely.

- [x] **Task 5 — AC2 independence proof (AC: #2)**
  - [x] `backend/tests/architecture/test_model_outage_boundaries.py` with Decision F's three tests:
        structural allow-set, detector self-test, behavioral end-to-end with a raising runtime
        factory.
  - [x] The behavioral test must traverse the real path — start the run, advance it, read
        `/schedule-runs/{id}/result` — and assert idempotent replay still returns the original
        semantic result with the runtime factory raising throughout.
  - [x] Assert the distinctness `EXPERIENCE.md:270` requires: a **solver/service** failure surfaces
        its own problem code, never the model-outage surface.

- [x] **Task 6 — AC3 telemetry independence (AC: #3)**
  - [x] Decision E's two cases (raising exporter; no tracer provider), asserting identical owned
        outcomes and identical persisted activity.
  - [x] One case driving the deterministic run path with a raising exporter installed, asserting the
        run row, result, and evidence are unaffected.
  - [x] Add the `NOT COVERED: audit:owned_by_epic_4` and
        `NOT COVERED: diagnosis:cloudwatch_owned_by_epic_6` markers where AC3's scope is declared,
        following the `SCOPE_CONTROLS` convention.

- [x] **Task 7 — Ledger and notes**
  - [x] Ledger entries for Gap 1 (no agent-free draft creation), Gap 2 (audit/CloudWatch NOT
        COVERED), Gap 3 (`available: true` is not a reachability proof), each with an owner/revisit
        trigger in the file's established format.
  - [x] Completion Notes must state exactly which clauses of NFR10 are proven and which are marked
        NOT COVERED, because `epics.md:333` lets Epic 5 rely on this story.
  - [x] **No evidence file.** Following Story 3.6 Decision 8: this story measures no threshold and
        publishes no report, so `docs/EVIDENCE-CONVENTION.md`'s generation pipeline does not apply.
        Do not hand-write one.

---

## Dev Notes

### Files this story touches

**New:** `backend/application/use_cases/agent_availability.py`; one API router module beside
`health.py` (or the nearest fitting existing router); `backend/tests/architecture/test_model_outage_boundaries.py`;
`frontend/src/hooks/useAgentAvailability.ts`; test files for each.

**Modified:** `backend/settings.py` (one setting + validation); the conversation repository (one
site-scoped read, if nothing existing fits); `frontend/src/lib/errors.ts` (one copy entry);
`frontend/src/features/chat/ChatView.tsx`; `frontend/src/features/chat/Composer.tsx` (one prop);
`frontend/src/test/accessibility-contract.test.tsx`; `frontend/src/api/schema.d.ts` (regenerated);
`_bmad-output/implementation-artifacts/deferred-work.md`.

**Explicitly NOT modified — editing any of these means the scope was misread:**
`api/routers/schedule_runs.py`, `application/use_cases/enqueue_compute.py`,
`application/capabilities/scheduling_compute.py`, `worker/lease_worker.py`, anything under
`engine/`, `agent/runtime.py`, `frontend/src/routes/ScenarioRuns.tsx`,
`frontend/src/components/runs/RunsTable.tsx`, `frontend/src/features/chat/DraftCard.tsx`,
`frontend/src/hooks/useStartScheduleRun.ts`.

### Project Structure Notes

Every placement follows an existing sibling: use cases in `application/use_cases/`, routers in
`api/routers/` with `_PROBLEM_RESPONSES` and `Depends(get_site_context)`, architecture proofs in
`tests/architecture/`, hooks as thin TanStack Query wrappers in `frontend/src/hooks/`, primitives
reused from `components/primitives/`. Absolute imports from the backend root; `@/` on the frontend.
No new dependency in either manifest — `opentelemetry-sdk` is already a declared dev dependency.

`AgentAvailabilityV1` deliberately does **not** go in `application/contracts/`. AD-20 governs
versioned schemas that cross adapters or get persisted; this one is a request-scoped read model. If
a later story persists it, that promotion is a contract change, not a refactor.

### Testing standards

Backend `pytest` from `backend/`; frontend Vitest + React Testing Library. Provider outages are
driven by **overriding `get_agent_runtime_factory`** — the established seam, used throughout
`test_conversations_api.py` (see its fake runtimes at `:216-259` and the outage parametrization at
`:594-608`). Never patch `pydantic_ai`, and never reach a live provider: CI is keyless and
`agent_runtime_model` defaults to `"test"`.

Two behaviors must be asserted **in combination**, not separately — composer-disabled *with*
Run-optimization-enabled (Trap 2), and timeline-visible *with* availability-pending (Trap 6).
Story 3.6's review finding at `3-6-...md:838` records the exact failure mode: "the test still passes
if you only test them separately."

### References

- `epics.md:1059-1080` — Story 3.9 and its three ACs (verbatim source)
- `epics.md:39` (FR8), `:93` (NFR10), `:186` (UX-DR5), `:226` (UX-DR25), `:333` (Epic 5's reliance)
- `epics.md:505-527` — Story 1.7, which already owns FR8's Scenario Data half
- `ARCHITECTURE-SPINE.md:174-179` — AD-15, including the model-outage sentence
- `ARCHITECTURE-SPINE.md:156-160` — AD-12, including "No telemetry system authorizes or blocks product work"
- `ARCHITECTURE-SPINE.md:78-83` (AD-6), `:132-137` (AD-8), `:198-203` (AD-19), `:204-209` (AD-20)
- `EXPERIENCE.md:66` (approved copy), `:84` (composer), `:120-128` (State Patterns), `:171` (model-outage exception), `:185-195` (Accessibility Floor), `:262-270` (Flow 4)
- `DESIGN.md:141-145` — Status badge, Inline alert, Reconnect banner
- `docs/DOMAIN-MODEL.md` — read; does not bind this story (see the Facts section)
- `backend/application/ports/agent_runtime.py:42-53` — `AgentProviderError`
- `backend/application/use_cases/execute_turn.py:137-141, 226-232, 235-252` — reason mapping, by type
- `backend/agent/runtime.py:107-133` (instrumentation), `:445-467` (`_configured_model`), `:470-500` (factory)
- `backend/api/routers/schedule_runs.py:345-421` — the agent-free run command
- `backend/application/use_cases/finalize_agent_run.py:55` — the only `create_draft` caller
- `backend/tests/architecture/test_solver_boundaries.py` — the `_imports` idiom and allow-set convention
- `backend/tests/architecture/test_agent_runtime_boundaries.py:53` — `FORBIDDEN_ROOT_MODULES`
- `_bmad-output/implementation-artifacts/3-6-start-explicit-bounded-optimization.md` — Decisions 4, 8; review findings at `:609`, `:838`
- `_bmad-output/implementation-artifacts/deferred-work.md:138, 204, 210`

---

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

- Implement each numbered task in story order using red-green-refactor.
- Keep availability network-free: runtime construction plus recent typed, site-scoped terminal evidence.
- Prove model and telemetry independence at existing seams without changing deterministic run code.
- Run focused checks after each task and the canonical full regression suites before completion.

### Debug Log References

- Task 1 RED: `test_agent_availability.py` failed collection because the availability use case did not exist.
- Task 1 GREEN: 30 focused availability/settings tests passed; canonical backend regression passed (1200 passed, 2 skipped, 7 deselected).
- A root-directory pytest invocation imported the spike suite's top-level `conftest`; the canonical story-required invocation from `backend/` passed, including the allegedly failing cleanup test.
- Task 2 RED: the exact recency-cutoff case failed because the use case treated an activity at the cutoff as newer than the window.
- Task 2 GREEN: strict recency, non-provider reasons, expiry, and cross-site isolation passed (35 focused; 1205 backend regression tests passed, 2 skipped, 7 deselected).
- Task 3 RED: ChatView could not resolve the missing availability hook and Composer left the real controls enabled.
- Task 3 GREEN: 22 focused tests and the full frontend suite (77 files, 515 tests) passed; typecheck passed; lint passed with three pre-existing Fast Refresh warnings.
- Task 4 RED proof: deliberately hiding the saved timeline during outage made the combined composer-disabled/Run-optimization-enabled test fail because the real deterministic control disappeared.
- Task 4 GREEN: 53 focused tests and the full frontend suite (77 files, 521 tests) passed; typecheck and lint passed (three pre-existing Fast Refresh warnings).
- Task 5 RED/self-test: the AST detector observed a synthetic `application.ports.agent_runtime` import; the raising runtime factory remained armed throughout the behavioral flow.
- Task 5 GREEN: four model-outage boundary tests and the full backend suite passed (1209 passed, 2 skipped, 7 deselected).
- Task 6 RED: the scope-marker guard failed before the two declared absences existed; the first semantic timeline comparison also exposed a random fake planner-message identity that required normalization rather than weakening product assertions.
- Task 6 GREEN: raising-exporter, disabled-export, and deterministic-run telemetry cases passed; full backend regression passed (1212 passed, 2 skipped, 7 deselected).
- Task 7: ledger validation found all three named gaps and their owner/revisit triggers; the final scope audit found no forbidden-file edits and confirmed no Story 3.9 evidence file exists.
- Final regression: backend passed 1212 tests (2 skipped, 7 deselected); frontend passed 521 tests across 77 files; OpenAPI regeneration, typecheck, lint, production build, and `git diff --check` passed. Lint retained three pre-existing Fast Refresh warnings and Vite retained its existing bundle-size advisory.

### Completion Notes List

- Task 1: Added a frozen request-scoped availability read model, network-free use case, site-scoped terminal-outcome read, authenticated GET route, positive recency setting, and regenerated OpenAPI artifacts.
- Task 2: Covered configuration failure, recent/expired provider evidence, strict cutoff behavior, non-provider failures, cross-site isolation, and the no-`run_turn` route invariant.
- Task 3: Added the thin availability API/query hook, fixed outage copy, polite inline alert with Scenario Data/Runs/refetch controls, fail-open query-error behavior, and disabled/associated composer controls while preserving deterministic controls.
- Task 4: Proved the timeline survives pending/error availability reads, the saved Draft's Run optimization remains enabled beside a disabled composer, recovery controls remain active, refetch works, healthy availability renders no alert, and the real controls satisfy the polite live-region accessibility contract.
- Task 5: Proved the exact manual-solver module set has no AgentRuntime imports, exercised the real start/lease/solve/result path with a construction-raising runtime factory, preserved one semantic run across replay, and kept solver-service failure distinct from model outage.
- Task 6: Proved optional trace export failure changes neither agent-owned outcome nor persisted activity/timeline nor deterministic run/result/evidence, and declared audit (Epic 4) plus CloudWatch diagnosis (Epic 6) honestly NOT COVERED.
- Task 7: Recorded all three deferred gaps with owners and revisit triggers. NFR10 is proven for zero product-state corruption under disabled/failing optional trace export, continued availability of supported manual/deterministic workflows during model-provider outage, unchanged agent-originated persisted activity, and unchanged deterministic run/result/evidence; telemetry neither authorizes nor blocks work. NFR10's **zero authoritative-audit loss** clause is **NOT COVERED** (`audit:owned_by_epic_4`) because no authoritative audit writer exists, and AC3's CloudWatch-diagnosis clause is **NOT COVERED** (`diagnosis:cloudwatch_owned_by_epic_6`) because no CloudWatch adapter exists. No evidence file was created.

### File List

- `_bmad-output/implementation-artifacts/3-9-continue-deterministic-work-during-model-outage.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/adapters/postgres/conversation.py`
- `backend/api/main.py`
- `backend/api/routers/agent_availability.py`
- `backend/application/ports/conversation.py`
- `backend/application/use_cases/agent_availability.py`
- `backend/settings.py`
- `backend/tests/test_agent_availability.py`
- `backend/tests/architecture/test_model_outage_boundaries.py`
- `backend/tests/test_conversations_api.py`
- `backend/tests/test_settings.py`
- `frontend/openapi.json`
- `frontend/src/api/agentAvailability.ts`
- `frontend/src/api/schema.d.ts`
- `frontend/src/components/primitives/InlineAlert.tsx`
- `frontend/src/features/chat/ChatView.test.tsx`
- `frontend/src/features/chat/ChatView.tsx`
- `frontend/src/features/chat/Composer.test.tsx`
- `frontend/src/features/chat/Composer.tsx`
- `frontend/src/hooks/useAgentAvailability.ts`
- `frontend/src/lib/errors.ts`
- `frontend/src/test/accessibility-contract.test.tsx`

## Change Log

- 2026-08-24: Implemented network-free agent availability, Chat degraded mode, deterministic model-outage boundaries, telemetry-independence proofs, accessibility coverage, and deferred-gap ledger entries; moved Story 3.9 to review.
