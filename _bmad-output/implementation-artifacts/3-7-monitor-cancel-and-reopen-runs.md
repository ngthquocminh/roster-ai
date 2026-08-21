---
baseline_commit: 6d5a5c9
---

# Story 3.7: Monitor, Cancel, and Reopen Runs

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want a Runs workspace and progress cards,
So that I can leave Chat, monitor accepted work, cancel when valid, and reopen one exact result.

**Planner-visible outcome: the second one since Story 3.1.** This is the story that makes the Story 3.4
cancellation command reachable to the planner. Stories 3.2–3.5 were all `[Technical Enabler]` with no
planner-facing surface; Story 3.6 shipped the Run optimization control and command; this story ships the
**Runs workspace** table that lists all runs for the scenario, renders their literal terminal states, and
makes Cancel/Retry actions available where valid.

**Depends on, and consumes:** Story 3.4's `/api/v1/schedule-runs/{run_id}/cancellation` command and the
`cancellation_requested` status value; Story 3.5's `/api/v1/schedule-runs/{run_id}` and `/events` GET
routes plus `run.queued.v1`, `run.running.v1`, and terminal events; Story 3.6's Run optimization control
and `POST /api/v1/schedule-runs` command; Story 1.6's `WorkspaceTabPlaceholder`, `Badge` components, and
the shared loading/empty/alert states; Story 3.1's `ProposalV1` and `proposal_version`; Story 2.2's
`PersistedEventV1` timeline; the `ScheduleRunStatusV1` closed graph from AD-7.

**Unblocks:** Story 3.8 (the comparison needs a completed candidate to read), Story 3.9 (the model
outage story links to Runs/manual optimization from Chat), Story 3.10–3.12 (the proof stories need
planner-reachable runs to drive).

**Scope summary:** One new `GET /api/v1/schedule-runs` collection route. One new React component
(RunsTable.tsx) and two UI components (RunStatusBadge, ProgressCard). One new hook (`useScheduleRuns`).
API client export in `scheduleRuns.ts`. **No new migration.** No new capability module. No evidence
file. **No backend logic changes** — the route is a simple list query against existing tables.

**This story is:**

1. **the first planner-visible Runs surface.** `frontend/src/routes/ScenarioRuns.tsx` is today a
   `WorkspaceTabPlaceholder`; this story replaces it with a functional table.
2. **the story that makes the Story 3.4 cancellation command reachable.** The Cancel control is new
   here; its route already exists (done by 3.4).
3. **the story that displays the literal terminal states** (completed, infeasible, timed-out, cancelled,
   failed) as distinct text without percentage, ETA, or invented states (AC3).
4. **the first story to add a `Retry` action.** Running the same proposal again creates a new run ID;
   this story exposes that action in the UI.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** requires this pass before decisions. None of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| `ScheduleRunStatusV1` closed graph has exactly these terminal states: `solver_completed`, `solver_infeasible`, `solver_timed_out`, `solver_cancelled`, `solver_failed`. Non-terminal states are `solver_queued`, `solver_running`, `cancellation_requested` | AD-7 (`ARCHITECTURE-SPINE.md:84-131`, `ScheduleRun` state machine `:106-122`) |
| `PersistedEventV1` carries `stream_id` (the schedule_run_id), `event_type`, `created_at`, `payload`, and `producing_run_version`. Every run state change emits an event | Story 2.2's proof story; `application/contracts/activity.py:PersistedEventV1` |
| Proposal and baseline versions identify exact inputs to the solver and are immutable; stale versions mark affected work stale and disable consequential actions | AD-9 (`ARCHITECTURE-SPINE.md:138-142`); Story 3.1/3.6 decisions |
| **The Run optimization command is idempotent.** Replaying the same proposal and expected version returns the same semantic run ID and response | Story 3.6 AC3 |
| Terminal states are **mutually exclusive**; a terminal run cannot transition to another state | AD-7 state machine |
| Cancellation is **cooperative** — the worker observes the `cancellation_requested` flag; nothing pre-empts the solver mid-turn | AD-6 (`ARCHITECTURE-SPINE.md:82`) |
| **Literal status text without anthropomorphic language, confidence scores, or invented states** (no percentage, no ETA, no feasibility forecast) | UX-DR5 (`epics.md:186`); UX-DR10 (`epics.md:193`); `EXPERIENCE.md` Voice and Tone table |
| `scenario_version` and `proposal_version` are immutable; they identify the **exact inputs and configuration** used for a run | AD-9; Story 3.1 decision |
| `baseline_schedule_version` is the operational baseline at the time the run was accepted. Story 3.1 Decision 7 records it **stays None today** and the field is "produced or verified by application calculators" — Story 3.8 produces it | Story 3.1 creation notes (sprint-status.yaml:237-250) |
| Only a terminal feasible run may be promoted to baseline; all other terminal states reject approval and remain non-promotable | FR17 (`epics.md:248`); Story 4.1 acceptance boundary |
| Keyboard operability and row navigation are proved by automated accessibility tests, not manual verification | `EXPERIENCE.md` Accessibility Floor (`:196`) |
| Frontend shared UI primitives (loading states, empty state, error alerts, badges) are from Story 1.6's fixture catalogue and are **reused, never reimplemented** | Story 1.6 architecture decision |

`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments. **This story touches no metric,
no demand row, and no assignment** — it reads and displays immutable run records. Cited for completeness
and deliberately not re-derived.

---

## Acceptance Criteria

Verbatim from `epics.md:1014-1029`.

1. **Given** runs for the selected scenario **When** the planner opens Runs **Then** a stable
   newest-first table shows run ID, exact literal status, accepted/updated time, scenario/proposal/baseline
   versions, and safe actions **And** row navigation, Cancel, Retry, and identifier-copy controls are
   separately labelled and keyboard-operable. (FR13, FR16, UX-DR17, UX-DR21)

2. **Given** no runs, loading, list failure, or model outage **When** Runs renders **Then** it uses the
   shared loading, empty, and alert states from the Story 1.6 primitives without hiding saved data
   **And** manual deterministic Run optimization remains available when permitted. (FR8, UX-DR23,
   UX-DR25)

3. **Given** a run reaches a literal terminal state **When** its progress card or row renders **Then**
   completed, infeasible, timed-out, cancelled, and failed are textually and structurally distinct with
   only valid next actions **And** no percentage, ETA, feasibility, or promotion control is invented.
   (NFR13, UX-DR10, UX-DR13)

---

## Architecture compliance guardrails

**Route design.** The new `GET /api/v1/schedule-runs` list route lives in `api/routers/schedule_runs.py`
(the same module that Story 3.4 added). Response shape: paginated `ScheduleRunOut[]` with optional
`?scenario_id` filter and `?limit`/`?cursor` for pagination. No idempotency key (reads are safe).

**Table schema reads.** The query reads from `schedule_run` and joins `persisted_event` (for timeline),
`proposal` (for version), and `proposal_version` (for accepted parameters). All tables are immutable at
read time or carry versioning; no writes are made.

**Terminal status rendering.** AC3 requires five visually and textually distinct terminal states:
- `completed` — solver finished, feasible schedule available
- `infeasible` — solver finished, no feasible schedule exists
- `timed_out` — solver wall-time exceeded
- `cancelled` — planner or system cancelled the run
- `failed` — solver or worker error

No percentage, ETA, feasibility forecast, or confidence score appears. No invented state like "Optimizing"
or "Almost done" renders. The `run.running.v1` and `run.queued.v1` states show as non-terminal progress
(e.g., "In progress" with timestamp, not a spinner or bar).

**Version display.** Columns are: Run ID (copyable), Status (literal text), Accepted time, Updated time,
Scenario version, Proposal version, Baseline version (or "—" if None). Each version is a stable
identifier the planner can cite; displayed as-is, never summarized or rounded.

**Actions.** Valid actions depend on terminal state:
- `solver_completed` (feasible): Show "Retry", "View Results", "Approve as baseline" (Story 4.1 owns
  approval logic; 3.7 simply renders it)
- `solver_completed` (stale baseline): Show "Retry", "View Results", approve disabled with "Stale
  baseline" label
- `solver_infeasible`, `solver_timed_out`, `solver_failed`: Show "Retry", "View Results"
- `solver_cancelled`: Show "Retry"
- `solver_queued`, `solver_running`: Show "Cancel" (calls Story 3.4 route), "View Progress"
- `cancellation_requested`: Show "View Progress" (worker may still finish; cancel is idempotent if
  replayed)

**Cancel button guard.** The Cancel control is shown only for non-terminal states and only if the user
has permission. Clicking Cancel calls `POST /api/v1/schedule-runs/{run_id}/cancellation` (Story 3.4
route) and rerenders the run status from the response. **Do not** speculatively disable the button; let
the server respond with a problem if the run is stale or terminal.

**Retry action.** Clicking Retry re-activates the same proposal through the Run optimization control
(Story 3.6). It is **not** a new route call; it is a gesture that selects the proposal in Chat and
activates the existing Run optimization flow. Proposal_id and expected_version are read from the run
record.

**Keyboard and accessibility.** The table is navigable by keyboard (arrow keys to move rows, Enter to
open, Space/Enter to activate action buttons). Row focus is announced. Status text is announced
(e.g., "Completed, feasible schedule" for `solver_completed`). The literal state name is part of the
announcement, not hidden. Copy-to-clipboard is a separate button with labelled `aria-label` and
`title`. Automated WCAG checks (axe, semantic, browser) must pass; manual assistive-technology
verification is out of scope.

**Error handling.** If the list query fails or the model is unavailable (Story 3.9 model outage), show
the Story 1.6 alert state with "Runs data is unavailable" and offer a retry button. Do not hide saved
run records or hide links to Scenario Data. The Runs workspace remains interactive even if the model is
down.

---

## Implementation notes

### Backend

**Route signature:** `GET /api/v1/schedule-runs?scenario_id={uuid}&limit={int}&cursor={str}`

**Query logic:**
1. Validate `scenario_id` exists and planner has access (site scope via session actor)
2. Query `schedule_run` WHERE `scenario_id = {id}` ORDER BY `created_at DESC` LIMIT `{limit}`
3. Join `persisted_event` on `stream_id = schedule_run_id` to fetch latest event (for updated_at, payload)
4. Join `proposal` and `proposal_version` to fetch proposal/scenario versions
5. Return paginated list with `next_cursor` if more rows exist

**Response model (in `api/schemas.py`):**
```python
class ScheduleRunOut(BaseModel):
    id: UUID
    status: str  # literal from ScheduleRunStatusV1
    created_at: datetime
    updated_at: datetime  # from persisted_event.created_at (latest)
    scenario_version_id: UUID | None
    proposal_id: UUID
    proposal_version: int
    baseline_schedule_version_id: UUID | None  # None today (Story 3.1 Decision 7)
    reason: str | None  # solver reason (e.g., "infeasible", "timed_out")
    resource_version: int  # for idempotent cancel
```

### Frontend

**Component: `RunsTable.tsx`**
- Accepts `runs: ScheduleRunOut[]`, `isLoading: bool`, `error: Error | null`
- Renders a table with columns: ID (copyable), Status, Accepted, Updated, Versions, Actions
- Status cell uses `RunStatusBadge` component
- Actions cell renders buttons conditionally based on status
- Sorting by "Newest first" is default and hardcoded (no user-selectable sort)
- Rows are keyboard-navigable

**Component: `RunStatusBadge.tsx`**
- Displays literal status text in a visually distinct container
- Maps `solver_completed` → green + "Completed", `solver_cancelled` → gray + "Cancelled", etc.
- No progress bar, spinner, or percentage
- Announced via `aria-label` for accessibility

**Component: `ProgressCard.tsx` (if rendering in-progress runs)**
- Shows run ID, timestamp, and "In progress" text
- No spinner animation (matches EXPERIENCE.md Voice and Tone)
- Reads from `run.running.v1` or `run.queued.v1` persisted events

**Hook: `useScheduleRuns.ts`**
```typescript
function useScheduleRuns(scenarioId: string, enabled = true) {
  return useQuery({
    queryKey: ["scheduleRuns", scenarioId],
    queryFn: () => api.listScheduleRuns({ scenario_id: scenarioId }),
    enabled,
  });
}
```

**Route update: `ScenarioRuns.tsx`**
Replace the `WorkspaceTabPlaceholder` with:
```typescript
export function ScenarioRuns() {
  const { scenarioId = "" } = useParams();
  const { data, isLoading, error } = useScheduleRuns(scenarioId);

  if (error) return <AlertState error={error} />;
  if (isLoading) return <SkeletonTable />;
  if (!data?.length) return <EmptyState />;

  return <RunsTable runs={data} isLoading={isLoading} error={error} />;
}
```

**API client export in `api/scheduleRuns.ts`:**
```typescript
export async function listScheduleRuns(
  params: { scenario_id: string; limit?: number; cursor?: string }
) {
  const response = await client.GET("/schedule-runs", {
    params: { query: params },
  });
  if (!response.data) throw response.error;
  return response.data;
}
```

---

## Previous story learnings to apply

**From Story 3.6 (Run optimization control):**
- Idempotent replay patterns are established; copy the same `get_idempotent_result` shape for cancel
  commands (already done by Story 3.4)
- Separate versioned controls (Send, Run optimization, Approve as baseline) with distinct visual
  treatment; this story adds one more control (Cancel) to the Runs workspace, fully separate from Chat
- Settings validation at process start is mandatory (already done by 3.6; no new settings here)
- Write routes go through the same bounded-response mapping (`_command_problem`, `_view_out`) as earlier
  stories; read routes are simpler (Story 3.7 adds only a read route)

**From Story 3.4 (Cancellation command):**
- Idempotency shape is `(site_id, actor_id, operation, idempotency_key, body_hash)` with expected
  version as part of the command identity
- The run's `resource_version` is the only authority; the job flag is a carrier
- Cancellation edges follow AD-7's closed graph exactly; no invented states
- Terminal states are mutually exclusive and require checked logic, not guesses

**From Story 3.5 (Run state/events):**
- Persisted events carry the full state machine trace; read latest event per run for updated_at
- Event types (`run.queued.v1`, `run.running.v1`, terminal events) map to `ScheduleRunStatusV1` values
- The `/events` endpoint is read-only and scoped by `scenario_id`

**From Story 3.1 (Reversible draft):**
- Proposal and versions are immutable; they name the exact configuration
- Stale inputs fail closed and require refresh, not silent rebase
- The capability system is the authority mechanism; no model output grants authority

**From Story 1.6 (Design tokens/primitives):**
- Reuse shared UI components (Badge, loading states, empty state, alerts) instead of inventing new ones
- Fixture catalogue defines the vocabulary; components are tested against it
- Accessibility is proved by automated tests only; do not add manual verification scope

---

## Traps and guards

### Trap 1: Rendering percentage, ETA, or confidence scores
AC3 explicitly forbids invented states. Do not render:
- A progress bar (no solver publishes real-time progress)
- "Optimizing... 45%" or "~2 minutes remaining"
- "Likely feasible" or "Probably complete"
- Spinner animations or pulsing effects

**Guard:** Static text only. The table row shows `solver_running` as "In progress" with a timestamp.
Terminal states show their exact name.

### Trap 2: Hiding runs or saved data on error
AC2 says "without hiding saved data". If the list query fails:
- Show the alert state with the error
- Offer a retry button
- Do not hide Scenario Data or Results links
- The workspace remains navigable

**Guard:** Test that the page remains interactive even when `useScheduleRuns` throws.

### Trap 3: Inventing the "Retry" action as a new route
Retry is **not** a new HTTP endpoint. It re-triggers the Run optimization flow with the same proposal.
Clicking Retry:
1. Reads `proposal_id` and `expected_resource_version` from the run row
2. Activates the Story 3.6 Run optimization control (same UI gesture as a planner clicking "Run
   optimization" in Chat)
3. The planner can review the proposal parameters in the Chat interface before confirming

**Guard:** Do not create a `POST /api/v1/schedule-runs/{run_id}/retry` route. The control already exists;
this story only makes it reachable from the Runs workspace.

### Trap 4: Rendering baseline version as empty or zero
`baseline_schedule_version` is **always None today** (Story 3.1 Decision 7 recorded this explicitly).
Rendering it as "—" (em dash) or "None" is correct. Do not render it as empty string, zero, or "Not
set" — those suggest it might appear later without code changes. Do not invent a "no baseline" state.

**Guard:** Test against a run with `baseline_schedule_version = None` and assert the display shows "—".

### Trap 5: Building a permission check for Cancel in the component
Cancel is a server-side idempotent command. The server decides whether to grant it, not the client.
Show the Cancel button for all non-terminal states and let the server respond with a problem if the
actor lacks permission or the run is stale.

**Guard:** Test that Cancel button is present for `solver_running` and `solver_queued`, and that clicking
it calls the correct Story 3.4 route.

### Trap 6: Paging with undefined cursor or limit
The `useScheduleRuns` hook must handle pagination correctly. If `cursor` is undefined, it should not be
in the query string; the endpoint interprets missing cursor as "page 1". Test the first page without a
cursor parameter.

**Guard:** Test pagination boundaries (empty list, single page, multiple pages) with mock data.

### Trap 7: Re-deriving the status value from solver output
The status is stored in the database and immutable. Do not compute "what the status should be" from
solver metrics or event payload. Read `schedule_run.status` directly.

**Guard:** Add a test that explicitly compares the rendered status against the stored status value, not
against any computed or inferred state.

---

## Tasks / Subtasks

- [x] **Task 1 — Repository/adapter: `list_runs` read** (AC: 1, 2)
  - [x] Add `ScheduleRunSummaryV1` + `ScheduleRunPageV1` to `application/ports/schedule_run.py` and a
        `list_runs(connection, *, scenario_id, site_id, limit, cursor)` method on the
        `ScheduleRunRepository` protocol. Fields: `schedule_run_id`, `status`, `reason`,
        `resource_version`, `created_at`, `finished_at`, `scenario_version_id`, `proposal_id`,
        `proposal_version` (ordinal), `baseline_schedule_version`. No new column, no migration —
        every field is already a column on `schedule_run`/`run_snapshot`/`proposal_version`.
  - [x] Implement in `adapters/postgres/schedule_run.py`: join `schedule_run` → `run_snapshot` (for
        `scenario_id`, `scenario_version_id`, `proposal_id`, `baseline_schedule_version`) →
        `proposal_version` (for `version_ordinal`), filtered by `run_snapshot.scenario_id` and
        `schedule_run.site_id`, ordered `created_at DESC, id DESC`, integer offset cursor (mirrors
        `scenario_projection`'s `cursor`/`next_cursor` shape — no new pagination idiom).
  - [x] Unit test against a fake/real adapter path: newest-first order, `next_cursor` set only when
        more rows exist, `baseline_schedule_version` reads through as `None`.

- [x] **Task 2 — Route: `GET /api/v1/schedule-runs`** (AC: 1, 2, 3)
  - [x] Extend `ScheduleRunOut` (or add a dedicated `ScheduleRunSummaryOut`) with the Task 1 fields;
        add `ScheduleRunPageOut { items, next_cursor }`.
  - [x] Add the route in `api/routers/schedule_runs.py`: required `scenario_id` query param, optional
        `limit` (default/bounded) and `cursor`; validate the scenario is visible in-site via the
        existing catalogue reader (404 if not, matching `get_projection`'s shape); read via
        `run_repository.list_runs(...)`.
  - [x] Router tests mirroring `test_schedule_runs_api.py`'s existing style: newest-first page shape,
        missing/foreign scenario → 404, `baseline_schedule_version` renders `None` (never `""`/`0`),
        cursor omitted on first page, `next_cursor` present/absent correctly.

- [x] **Task 3 — Regenerate the OpenAPI contract** (AC: 1)
  - [x] `npm run codegen` (backend must import cleanly) so `frontend/openapi.json` and
        `frontend/src/api/schema.d.ts` carry the new route/schemas. No hand-authored frontend types.

- [x] **Task 4 — Frontend API clients** (AC: 1, 3)
  - [x] `api/scheduleRuns.ts`: add `listScheduleRuns(params)` (GET, schema-derived types) and
        `cancelScheduleRun(runId, body, idempotencyKey)` (POST, same shape as `startScheduleRun`).
        No cancellation client exists yet on the frontend even though Story 3.4 shipped the route.
  - [x] Tests mirroring `scheduleRuns.test.ts`'s existing style for both functions (success shape,
        status-attached rejection).

- [x] **Task 5 — Frontend hooks** (AC: 1, 2, 3)
  - [x] `hooks/useScheduleRuns.ts`: TanStack Query wrapper (`queryKey: ["scheduleRuns", scenarioId,
        cursor]`), `enabled` on a non-empty `scenarioId`, wired through
        `useRedirectOnUnauthorized`/`getErrorStatus` like `useScenarioProjection`'s group hooks.
  - [x] `hooks/useCancelScheduleRun.ts`: mutation mirroring `useRejectProposal`'s idempotency-key
        holder shape; invalidates the runs list on success.
  - [x] Tests for both (query enabling/disabling, mutation idempotency-key retry/rotation shape).

- [x] **Task 6 — `RunStatusBadge.tsx`** (AC: 3)
  - [x] Maps each of the 8 `ScheduleRunStatusV1` values to distinct literal text + a visual accent;
        composes the existing `StatusBadge` primitive rather than inventing a new badge shell.
        No percentage, ETA, spinner, or invented state. `aria-label` carries the literal text.
  - [x] Test: all 8 statuses render distinct, literal text; no two share display text.

- [x] **Task 7 — `ProgressCard.tsx`** (AC: 3)
  - [x] Renders run id + accepted/updated timestamp + literal "In progress" text for
        `solver_queued`/`solver_running`/`cancellation_requested`. No spinner, no percentage.
  - [x] Test: renders for each non-terminal status without any forbidden token
        (`%`, "ETA", "remaining", "likely", "probably").

- [x] **Task 8 — `RunsTable.tsx`** (AC: 1, 2, 3; Traps 1–7)
  - [x] Columns: Run ID (via `IdentifierCopyButton`), Status (`RunStatusBadge`/`ProgressCard`),
        Accepted, Updated, Scenario/Proposal/Baseline versions (baseline `"—"` when `None` — Trap 4),
        Actions.
  - [x] Actions per the Architecture guardrails' status table exactly (Retry/View Results/Approve
        for completed, Retry/View Results for infeasible/timed-out/failed, Retry only for
        cancelled, Cancel+View Progress for queued/running, View Progress only for
        cancellation_requested). **Resolved wording tension:** the guardrails' general "Cancel is
        shown only for non-terminal states" / Trap 5 language reads as "all non-terminal states"
        in isolation, but the per-status Actions table — the more specific source — lists Cancel
        only for `solver_queued`/`solver_running`, and Trap 5's own prescribed guard test names
        only those two. Cancel is therefore NOT shown for `cancellation_requested` (redundant —
        nothing new for a planner to do while a request already in flight is cooperative and
        idempotent); the Approve/Cancel/Retry sets otherwise follow the table exactly. No
        client-side permission guess either way — the server decides (Trap 5).
  - [x] Cancel button calls `useCancelScheduleRun` with the row's `resource_version` and rerenders
        from the response; server-side problem (409/404) surfaces via `InlineAlert`, does not hide
        the row (Trap 2).
  - [x] Retry reads `proposal_id` from the row, fetches the proposal's **current** resource version
        via the existing `useProposal` hook (not a frozen historical one — a proposal may have been
        revised since this run), and calls `useStartScheduleRun` with it — the exact gesture
        `DraftCard`'s "Run optimization" button already performs (Trap 3: no new route).
  - [x] Status is read verbatim from `run.status`, never recomputed from any other field (Trap 7).
  - [x] Keyboard: every row/action is a distinct, natively focusable element (link/button) in Tab
        order — the same accessibility approach `ScenarioDataTable` already uses for Story 1.6's
        surfaces, not a bespoke arrow-key grid (see Dev Notes for why arrow-key roving is deferred).
  - [x] Tests: pagination boundaries (Trap 6 — cursor omitted on page 1), Cancel for
        running/queued, Retry for completed/infeasible/timed-out/failed/cancelled, baseline "—"
        (Trap 4), all 5 terminal states render distinct text, status read verbatim (Trap 7).

- [x] **Task 9 — `ScenarioRuns.tsx` route wiring** (AC: 2)
  - [x] Replace the `WorkspaceTabPlaceholder` with `useScheduleRuns` + loading (Skeleton) / empty
        (`EmptyState`) / error (`InlineAlert`, retry action) states, reusing Story 1.6 primitives —
        not reimplementing them.
  - [x] On list failure, saved Scenario Data / other tab links remain reachable — the workspace
        chrome around the tab content is untouched (Trap 2).
  - [x] Tests: loading → data, empty list, list failure shows alert without hiding navigation,
        pagination advances the query cursor.

- [x] **Task 10 — Full regression + Done checklist + deferred-work entries**
  - [x] Backend: full pytest regression. Frontend: full Vitest, `tsc --noEmit`, `oxlint`.
  - [x] Walk every `Done checklist` item below and confirm it against the shipped code.
  - [x] Record the arrow-key-grid-navigation trim (Task 8) and any other conscious scope cut as a
        `deferred-work.md` entry, not a silent omission.

## Done checklist

- [x] `RunsTable.tsx` component implemented and tested
- [x] `RunStatusBadge.tsx` component renders five terminal states distinctly
- [x] `ProgressCard.tsx` renders non-terminal states without spinners or percentages
- [x] `useScheduleRuns` hook implemented with proper error and loading states
- [x] `GET /api/v1/schedule-runs` route implemented and returns paginated list
- [x] `api/scheduleRuns.ts` exports `listScheduleRuns` function
- [x] `ScenarioRuns.tsx` route replaces placeholder with RunsTable
- [x] Cancel button calls Story 3.4 route and rerenders
- [x] Retry button re-activates Run optimization control with same proposal
- [x] Shared UI primitives (loading, empty, error states) from Story 1.6 are reused
- [~] Keyboard navigation and WCAG AA accessibility pass automated checks — **partial:**
      every control is a real, natively focusable, labelled element (native Tab order, no
      bespoke arrow-key grid — see `deferred-work.md`), and Vitest/Testing Library assert
      accessible roles/names/labels throughout. No Playwright `expectAxeClean` scan was added
      for the Runs page (`deferred-work.md`, MVP scope) — the existing e2e suite covers
      Scenario Data only.
- [x] Status text is distinct and literal (no percentage, ETA, confidence)
- [x] Baseline version displays as "—" when None
- [x] All five terminal states render with distinct text
- [x] Rows are newest-first (proven at the adapter, via a live-Postgres test) and navigable
- [x] Copy-to-clipboard for run ID works with separate button
- [x] Model outage (Story 3.9) doesn't hide saved data — structurally true: this route makes
      no LLM/model call of any kind, so a model outage cannot affect it either way
- [x] Test: pagination with multiple runs
- [x] Test: cancel button for running/queued runs
- [x] Test: retry button for completed runs
- [x] Test: list failure shows alert without hiding data
- [x] Test: empty run list shows empty state
- [x] Test: verify Story 1.6 shared components are reused, not reimplemented

---

## Summary

Story 3.7 is the planner-visible Runs workspace that makes the Story 3.4 cancellation command
reachable and renders the Story 3.6 optimization results. It reads immutable run records from the
database, displays their literal terminal states without invented metrics, and exposes Cancel/Retry
actions that are guarded by the server. It reuses shared UI primitives from Story 1.6 and the keyboard
accessibility established in that story's automated suite. No new migration, no new backend logic, no
new capability module.

The work is primarily frontend: a table component, a status badge component, a hook, and a route
implementation. The backend contribution is one simple paginated read route.

**Key architectural decisions:**
1. Literal status text only — no percentage, ETA, or confidence
2. Cancel button shows for all non-terminal states; server decides permission
3. Retry re-activates existing Run optimization flow, not a new endpoint
4. Shared UI primitives from Story 1.6 are reused
5. Baseline version stays None today per Story 3.1 Decision 7

**This story unblocks** Stories 3.8 (needs completed runs to compare), 3.9 (links to Runs during model
outage), and 3.10–3.12 (proof stories need planner-reachable runs).

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5

### Debug Log References

- Task 1 GREEN: 3 `@pytest.mark.postgres` tests pass (2 pre-existing + 1 new
  `test_live_list_runs_orders_newest_first_paginates_and_scopes_by_scenario`), proving newest-first
  order, cursor pagination, cross-scenario scoping, and `baseline_schedule_version` reading through
  as `None` against a real, migrated PostgreSQL database.
- Task 2 GREEN: 29 tests in `test_schedule_runs_api.py` pass (24 pre-existing + 5 new list-route
  tests: page shape, pagination/cursor pass-through, `limit` upper-bound rejection (422), unknown/
  cross-site scenario → 404 `scenario_not_found`).
- Task 3 GREEN: `npm run codegen` regenerated `frontend/openapi.json` and `src/api/schema.d.ts`
  cleanly from the running backend; `list_schedule_runs_api_v1_schedule_runs_get` operation and its
  query/response types are present.
- Task 4 GREEN: 6 tests in `scheduleRuns.test.ts` pass (2 pre-existing + 4 new: `listScheduleRuns`
  success/failure, `cancelScheduleRun` success/failure).
- Task 5 GREEN: 4 tests pass (`useScheduleRuns.test.tsx` — disabled-until-scenario-id, fetch with
  cursor; `useCancelScheduleRun.test.tsx` — idempotency-key hold/rotate shape, cache invalidation).
- Task 6 GREEN: 12 tests pass across `RunStatusBadge.test.tsx` (new) and `StatusBadge.test.tsx`
  (pre-existing, re-run to prove the additive `className` prop is backward-compatible) — all 8
  statuses render distinct literal text, all 5 terminal states mutually distinct, `aria-label`
  carries the literal text, no forbidden token (%, ETA, remaining, likely, probably).
- Task 7 GREEN: 6 tests pass in `ProgressCard.test.tsx` across all 3 non-terminal statuses — literal
  text + timestamp, no forbidden token, no `progressbar` role.
- Task 8 GREEN: 30 tests pass in `RunsTable.test.tsx` covering every trap (1–7) plus the resolved
  Cancel-visibility wording tension (see Task 9's list entry and the Tasks/Subtasks note above).
- Task 9 GREEN: 5 tests pass in `ScenarioRuns.test.tsx` (loading/data/error pass-through, no
  pagination controls on a single first page, Next/First advance and reset the query cursor) plus
  the pre-existing `router.test.tsx` (8 tests) and `accessibility-contract.test.tsx` continue to
  pass unmodified.
- Task 10 GREEN: backend `pytest -m "not postgres and not live"` — 1085 passed, 2 skipped;
  `pytest -m postgres` — 85 passed. Frontend `vitest run` — 480 passed across 72 files (0 failed);
  `tsc --noEmit` clean; `oxlint` — only 3 pre-existing warnings, none in touched files;
  `npm run build` succeeds. One pre-existing regression surfaced and was fixed in the same task:
  `legacyReachability.test.ts` still listed `components/runs/` as proven-orphaned legacy surface
  from a pre-Epic-3 UI; updated to remove that entry now that the directory is legitimately
  reachable from `App.tsx` via this story's `RunsTable`/`RunStatusBadge`/`ProgressCard`.

### Implementation Plan

Implement each task in order (backend read path first, then the frontend contract/hooks/components
that depend on it), running the focused tests for that task before moving to the next, then the full
backend/frontend regression at Task 10.

### Completion Notes List

- **Task 1–2 (backend):** Added `ScheduleRunSummaryV1`/`ScheduleRunPageV1` to the
  `ScheduleRunRepository` port and a real `list_runs` implementation in the Postgres adapter —
  offset-cursor pagination (mirrors `scenario_projection`'s existing idiom, no new convention),
  joining `schedule_run` → `run_snapshot` → `proposal_version`. No new column, no migration: every
  field already existed. Added `GET /api/v1/schedule-runs?scenario_id&limit&cursor`, gated on the
  same `ScenarioCatalogueReader.get_scenario_context` existence/site-visibility check
  `get_projection` already uses (404 `scenario_not_found` for an unknown or cross-site scenario).
- **Task 3:** OpenAPI/TS regenerated; no hand-authored frontend types anywhere in this story.
- **Task 4–5 (frontend contract/hooks):** Added `listScheduleRuns`/`cancelScheduleRun` to
  `api/scheduleRuns.ts` — Story 3.4 shipped the cancellation ROUTE with no frontend consumer until
  now. Added `useScheduleRuns` (TanStack Query, mirrors `useScenarioProjection`'s group-hook shape)
  and `useCancelScheduleRun` (mirrors `useRejectProposal`'s idempotency-key-holder shape).
- **Task 6–7 (status/progress display):** `RunStatusBadge` composes Story 1.6's `StatusBadge`
  primitive (extended with an additive, backward-compatible `className` prop) rather than a new
  badge shell — all 8 AD-7 statuses get distinct literal text; colour is an accent only. `ProgressCard`
  renders non-terminal runs as static text + timestamp, no spinner/percentage.
- **Task 8 (RunsTable, the resolved trap):** the Architecture guardrails' precise per-status Actions
  table and its two more general passages ("Cancel button guard", Trap 5) disagree on whether
  `cancellation_requested` shows a Cancel button — the general passages read as "all non-terminal
  states" (which includes it), the specific table lists Cancel only for `solver_queued`/
  `solver_running`. Resolved in favour of the more specific table: Trap 5's own prescribed guard
  test names only `solver_running`/`solver_queued`, and a second Cancel click on a run whose
  cancellation is already in flight has no new effect to offer (cooperative, idempotent). Documented
  inline in `RunsTable.tsx` and in the Tasks/Subtasks entry above, not silently picked. Retry reads
  the proposal's CURRENT `resource_version` via the existing `useProposal` hook rather than a value
  carried on the run row — no such field exists without a migration this story does not own, and
  using the live version is strictly more correct for a "run this again" gesture than a frozen
  historical one. "Approve as baseline" renders uniformly disabled (no working command exists at
  all — Epic 4/Story 4.1) rather than distinguishing "stale" from "not available" (deferred).
- **Task 9 (route wiring):** `ScenarioRuns.tsx` replaces the `WorkspaceTabPlaceholder` outright.
  Loading/empty/error states are pushed into `RunsTable` itself (Skeleton/EmptyState/InlineAlert,
  all Story 1.6 primitives) rather than duplicated at the route level, matching the codebase's own
  `ScenarioDataGroupState` precedent of centralising that branching in one place. Pagination is a
  minimal First/Next pager (the richer `PaginationControls` primitive needs `matching_count`/
  `total_count` fields this list route's response does not carry, and fabricating them was out of
  scope) — Trap 6 verified: page one calls the hook with `cursor: 0`, never an undefined/stray value.
- **Task 10:** Full backend + frontend regressions, typecheck, lint, and production build all pass.
  Three conscious scope trims — the keyboard idiom, the Approve control's single disabled state, and
  the missing Playwright/axe scan for this page — are recorded in `deferred-work.md` with owners
  and revisit triggers rather than left as silent gaps.

### File List

**Backend**
- backend/application/ports/schedule_run.py
- backend/adapters/postgres/schedule_run.py
- backend/api/schemas.py
- backend/api/routers/schedule_runs.py
- backend/tests/test_schedule_runs_api.py
- backend/tests/test_schedule_run_persistence.py

**Frontend**
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- frontend/src/api/scheduleRuns.ts
- frontend/src/api/scheduleRuns.test.ts
- frontend/src/hooks/useScheduleRuns.ts
- frontend/src/hooks/useScheduleRuns.test.tsx
- frontend/src/hooks/useCancelScheduleRun.ts
- frontend/src/hooks/useCancelScheduleRun.test.tsx
- frontend/src/components/primitives/StatusBadge.tsx
- frontend/src/components/runs/RunStatusBadge.tsx
- frontend/src/components/runs/RunStatusBadge.test.tsx
- frontend/src/components/runs/ProgressCard.tsx
- frontend/src/components/runs/ProgressCard.test.tsx
- frontend/src/components/runs/RunsTable.tsx
- frontend/src/components/runs/RunsTable.test.tsx
- frontend/src/routes/ScenarioRuns.tsx
- frontend/src/routes/ScenarioRuns.test.tsx
- frontend/src/test/legacyReachability.test.ts

**Docs / tracking**
- _bmad-output/implementation-artifacts/3-7-monitor-cancel-and-reopen-runs.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- _bmad-output/implementation-artifacts/deferred-work.md

## Change Log

- 2026-08-22: Story implemented. Backend: `GET /api/v1/schedule-runs` list route (repository +
  Postgres adapter + schemas). Frontend: Runs workspace (`RunsTable`, `RunStatusBadge`,
  `ProgressCard`), `useScheduleRuns`/`useCancelScheduleRun` hooks, `scheduleRuns.ts` client
  additions, `ScenarioRuns.tsx` route wired end-to-end. Fixed a pre-existing `legacyReachability`
  guard test that still forbade `components/runs/` from being reachable. Status → review.
