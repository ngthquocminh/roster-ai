---
baseline_commit: 6d5a5c9
---

# Story 3.7: Monitor, Cancel, and Reopen Runs

Status: ready-for-dev

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

## Done checklist

- [ ] `RunsTable.tsx` component implemented and tested
- [ ] `RunStatusBadge.tsx` component renders five terminal states distinctly
- [ ] `ProgressCard.tsx` renders non-terminal states without spinners or percentages
- [ ] `useScheduleRuns` hook implemented with proper error and loading states
- [ ] `GET /api/v1/schedule-runs` route implemented and returns paginated list
- [ ] `api/scheduleRuns.ts` exports `listScheduleRuns` function
- [ ] `ScenarioRuns.tsx` route replaces placeholder with RunsTable
- [ ] Cancel button calls Story 3.4 route and rerenders
- [ ] Retry button re-activates Run optimization control with same proposal
- [ ] Shared UI primitives (loading, empty, error states) from Story 1.6 are reused
- [ ] Keyboard navigation and WCAG AA accessibility pass automated checks
- [ ] Status text is distinct and literal (no percentage, ETA, confidence)
- [ ] Baseline version displays as "—" when None
- [ ] All five terminal states render with distinct text
- [ ] Rows are newest-first and navigable
- [ ] Copy-to-clipboard for run ID works with separate button
- [ ] Model outage (Story 3.9) doesn't hide saved data
- [ ] Test: pagination with multiple runs
- [ ] Test: cancel button for running/queued runs
- [ ] Test: retry button for completed runs
- [ ] Test: list failure shows alert without hiding data
- [ ] Test: empty run list shows empty state
- [ ] Test: verify Story 1.6 shared components are reused, not reimplemented

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
