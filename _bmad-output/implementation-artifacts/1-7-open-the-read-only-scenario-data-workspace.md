---
baseline_commit: e925c07965a363f7f0a6aae73b4bfddcd3842e4d
---

# Story 1.7: Open the Read-Only Scenario Data Workspace

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want a read-only Scenario Data workspace,
so that I can verify the exact demand, workforce, assignments, locks, and rules before trusting assistance.

**This is a frontend-only story.** Story 1.4 and Story 1.5 already shipped every backend endpoint this story consumes (`/api/v1/scenarios/{scenario_id}/projection*`), the generated OpenAPI types are already in `frontend/src/api/schema.d.ts`, and both endpoints already have their own passing NFR35 evidence. **There is no backend work in this story** — no new route, no new port method, no migration.

**Depends on:** Story 1.3 (done) — the governed route tree (`App.tsx`'s `routes`), `ScenarioWorkspace.tsx`'s persistent-context shell, `ScenarioVersionContext`, the `AppBar`. Story 1.4 (done) — the seven `GET /api/v1/scenarios/{scenario_id}/projection*` read endpoints and their generated TypeScript types. Story 1.5 (done) — not directly consumed by this story (its exact-target resolution endpoints are Story 2.8's consumer), but its existence confirms the projection read path is stable.
**Story 1.6 is `ready-for-dev`, not `done`, as of this story's creation** — it has a complete plan (`1-6-establish-shiftmind-design-tokens-and-shared-primitives.md`) but may or may not be implemented before this story is. It explicitly does **not** build Workspace tabs or the Scenario Data grid (its own Task 3 lists both as out of scope, deferred here) — so this story is never blocked on it starting. But it *does* touch shared token/primitive surfaces this story also touches — see Dev Notes "Story 1.6 ordering" for exactly what to check and how to stay correct either way.
**Unblocks:** Story 1.8 — its *frontend* half (sorting/filtering/pagination/column-chooser/copy controls) layers directly on top of this story's group panels and API hooks. **Note for sizing and sequencing: Story 1.8 is a full-stack story, not a frontend-only one.** Server-side sort/filter does not exist yet — Story 1.4 shipped `cursor`/`limit` only and deliberately deferred both (*"explicit sorting is Story 1.8's acceptance boundary, not this one's"*; `matching_count` is hardcoded to `total_count` in `adapters/postgres/scenario_projection.py`). Story 1.8 owns that backend contract, and its Tasks 1–4 are **not** blocked on this story — see `1-8-control-scenario-data-tables.md`'s header. Also unblocks Story 1.9 (viewer/agent parity and mutation-denial audits target these same routes/components), Story 2.8 (evidence-link navigation opens `/scenarios/:scenarioId/data?group=...` — this story's exact URL scheme).

## Acceptance Criteria

1. **Given** a selected fixture, **when** the planner opens `/scenarios/:scenarioId/data`, **then** the workspace shell exposes real routes for Chat, Scenario Data, Runs, and Results while Scenario Data shows the seven groups in the required fixed order, **and** Results is disabled with an accessible explanation until a run is selected. *(UX-DR1, UX-DR3)*

2. **Given** any Scenario Data group, **when** it renders, **then** it uses a captioned semantic table with stable headers, contained two-axis scroll, and sticky orientation cues, **and** it exposes no editable cells, mutation controls, bulk selection, or mutation-looking menus. *(FR24, UX-DR4, UX-DR14)*

3. **Given** the model provider is unavailable, **when** the planner uses Scenario Data, **then** the full read-only view remains available because it calls the application scenario-read service directly, **and** no AgentRuntime dependency is invoked. *(FR8, partial; AR15)*

## Tasks / Subtasks

- [x] Task 1: Restructure the scenario workspace into a shared shell + four peer child routes (AC: #1)
  - [x] In `frontend/src/App.tsx`, change the `scenarios/:scenarioId` route from a leaf to a parent with `children`:
    ```
    {
      path: "scenarios/:scenarioId",
      Component: ScenarioWorkspace,
      children: [
        { index: true, Component: ScenarioChat },
        { path: "data", Component: ScenarioData },
        { path: "runs", Component: ScenarioRuns },
        { path: "runs/:runId", Component: ScenarioResults },
      ],
    }
    ```
    Four new files in `frontend/src/routes/`: `ScenarioChat.tsx`, `ScenarioData.tsx`, `ScenarioRuns.tsx`, `ScenarioResults.tsx`. Each independently calls `useParams()` for `scenarioId` (and `runId` for `ScenarioResults`) — do not prop-drill through `Outlet` context; `ScenarioWorkspace` already proved the pattern of a child route reading its own params.
  - [x] Edit `frontend/src/routes/ScenarioWorkspace.tsx`: **keep every existing branch unchanged** (loading, 401-null, terminal 404/422, generic error, stale-with-cached-data) — only the final success-path `<main>` changes. Replace the placeholder `<section>` (lines 151-161 today) with `<WorkspaceTabs scenarioId={scenarioId} /><Outlet />`.
  - [x] **Layout width judgment call — apply exactly this, do not improvise a different split.** DESIGN.md requires Scenario Data to use "the available viewport width after `{spacing.workspace-gutter}` gutters" (i.e. no reading-column cap) while Chat/Runs/Results keep a centered column. The persistent context bar and the tab bar sit above all four views, so: **drop `max-w-6xl mx-auto` from `ScenarioWorkspace.tsx`'s success-path `<main>`**, leaving only `px-6 py-8` (full width, 24px gutters) — this makes `ScenarioVersionContext` and `WorkspaceTabs` span full width too, which is fine (nothing in DESIGN.md ties their width to the content column). Inside `ScenarioChat.tsx`/`ScenarioRuns.tsx`/`ScenarioResults.tsx`, wrap their own content in `<div className="mx-auto max-w-6xl">` to preserve the existing centered-column feel. `ScenarioData.tsx` gets no such wrapper — it uses the full gutter-to-gutter width directly, which is the entire point of this change (large tables need it). Keep `max-w-6xl` (not DESIGN.md's nominal `max-w-5xl`) — that's the value Story 1.3 already shipped everywhere else in this app; reconciling it to `max-w-5xl` is Story 1.6's job, not this story's.

- [x] Task 2: Build the workspace-level tab bar (AC: #1)
  - [x] New file `frontend/src/features/scenario-workspace/WorkspaceTabs.tsx` (sibling to the existing `ScenarioVersionContext.tsx` in the same feature dir — this is workspace-shell chrome, not Scenario-Data-specific). Props: `{ scenarioId: string }`.
  - [x] **This is NOT the shadcn `Tabs` component from `@/components/ui/tabs`.** These four items are real routes (UX-DR1: "Each tab has a real route; browser Back/Forward works"), so render them as `NavLink`s styled to look like tabs — mirror `AppBar.tsx`'s existing `NavLink` pattern, not Radix Tabs' internal state-switching. (The Scenario Data *group* navigation in Task 4 below is the one that legitimately uses shadcn `Tabs` — don't conflate the two; they look similar but behave completely differently.)
  - [x] Four items, in order: Chat → `NavLink to={`/scenarios/${scenarioId}`} end` (link text "Chat"); Scenario Data → `NavLink to={`/scenarios/${scenarioId}/data`}` (link text "Scenario Data"); Runs → `NavLink to={`/scenarios/${scenarioId}/runs`}` (link text "Runs"); Results → **always disabled in this story** (no `ScheduleRun` concept exists until Epic 3 — do not build run-selection state/logic here). Render Results as a non-interactive element (e.g. `<span aria-disabled="true">Results</span>`, not an `<a>`/`<button>` with a no-op handler), plus **always-visible** (not hover/title-only — UX-DR29 forbids hover-only meaning) explanatory text using the exact EXPERIENCE.md copy: `"Results unavailable: select a run."`
  - [x] Active-state styling per DESIGN.md's `workspace-tabs` component: active item gets `{colors.primary}` (`#4F46E5`) text + a 2px underline, inactive/disabled inherit shadcn muted. **Check `frontend/src/index.css` before styling — it depends on whether Story 1.6 has landed yet:** if `--primary` is still `oklch(0.205 0 0)` (shadcn's default near-black), Story 1.6 hasn't shipped — mirror `AppBar.tsx`'s current workaround (hardcoded `text-[#4F46E5]` Tailwind arbitrary-value hex), do not assume `text-primary` renders indigo. If `--primary: #4F46E5` is already present, Story 1.6 has shipped — use `text-primary`/`border-primary` utility classes directly (the DESIGN.md-correct mechanism), and note that by then `AppBar.tsx`'s own indigo usage will have been retokenized to `text-evidence-link` (Story 1.6 Task 2) — do **not** copy that specific class for the active-tab color, `workspace-tabs.active-foreground` maps to `{colors.primary}`, not `{colors.evidence-link}`; they're visually identical (`#4F46E5`) today but are two distinct tokens with different intended uses.
  - [x] `NavLink`'s active state must also carry `aria-current="page"` (react-router's `NavLink` sets this automatically when active — verify it lands in the DOM via a test, don't hand-roll it) — DESIGN.md: "Active state is also conveyed by `aria-current`, not color alone."
  - [x] 44×44 CSS px minimum touch target on every item (UX-DR29). On narrow viewports the tab list must scroll horizontally without truncating labels (UX-DR responsive table) — wrap the list in `overflow-x-auto` with `whitespace-nowrap` items, do not `text-ellipsis`/truncate.

- [x] Task 3: Scenario Data — API client + query hooks (AC: #2, #3)
  - [x] New file `frontend/src/api/scenarioProjection.ts`, mirroring `frontend/src/api/scenarioCatalogue.ts`'s shape exactly (type derived from `paths`, `client.GET(...)`, `throw { ...error, status: response.status }` on error). Seven functions:
    - `getScenarioOverview(scenarioId): Promise<ScenarioOverview>` → `GET /api/v1/scenarios/{scenario_id}/projection`
    - `getWorkAreasAndTasks(scenarioId, cursor?, limit?): Promise<TaskPage>` → `.../projection/work-areas-and-tasks`
    - `getWorkers(scenarioId, cursor?, limit?): Promise<WorkerPage>` → `.../projection/workers`
    - `getDemand(scenarioId, cursor?, limit?): Promise<DemandIntervalPage>` → `.../projection/demand`
    - `getBaselineAssignments(scenarioId, cursor?, limit?): Promise<AssignmentPage>` → `.../projection/baseline-assignments`
    - `getLocks(scenarioId, cursor?, limit?): Promise<LockPage>` → `.../projection/locks`
    - `getConstraintsAndObjectives(scenarioId, cursor?, limit?): Promise<ConstraintPage>` → `.../projection/constraints-and-objectives`
    Derive each response type from `paths["/api/v1/scenarios/{scenario_id}/projection..."]["get"]["responses"][200]["content"]["application/json"]`, exactly like `scenarioCatalogue.ts`'s `FixtureCatalogueEntry`/`ScenarioContext` types. **This story only ever calls these with `cursor=0` and the server default `limit` (50) — do not pass explicit values, do not build pagination.** The `cursor`/`limit` parameters exist on the functions now purely so Story 1.8 can pass real values later without touching this file's function signatures again (same "define the full shape now, narrow usage now" precedent Story 1.4 used for `AssignmentV1`/`LockV1`).
  - [x] **Do not confuse this with the existing `ScenarioContext` type/`useScenarioContext` hook.** Those (Story 1.3, `scenarioCatalogue.ts` / `useScenarioContext.ts`) back the persistent top-of-page context bar (`ScenarioVersionContext.tsx`) and hit `GET /api/v1/scenarios/{scenario_id}` — a *different*, older, narrower endpoint. The Scenario Data "Overview" *group* (item 1 of the seven fixed groups, with `work_area_count`/`task_count`/.../`projection_generated_at`) is a **new, separate** concept from Story 1.4's `GET .../projection` endpoint. Do not try to reuse `useScenarioContext` for the Overview group panel — it lacks the count fields and `projection_generated_at` this group needs.
  - [x] New file `frontend/src/hooks/useScenarioProjection.ts` with seven hooks (`useScenarioOverview`, `useWorkAreasAndTasks`, `useWorkers`, `useDemand`, `useBaselineAssignments`, `useLocks`, `useConstraintsAndObjectives`), each a thin `useQuery` wrapper exactly like `useScenarioContext.ts`: `queryKey: ["scenario-projection", scenarioId, "<group-slug>"] as const`, `enabled: Boolean(scenarioId)`, `retry: false`, **no `staleTime`** (same rationale as `useScenarioContext`: the payload is immutable per `scenario_version`, but a new version can be imported and the server always re-resolves "latest," so an infinite `staleTime` could show a stale version after a re-import — comment this in the file, don't silently omit the explanation).
  - [x] Use the **exact same slug strings** the backend already uses as `group` discriminant values (`"work-areas-and-tasks"`, `"workers"`, `"demand"`, `"baseline-assignments"`, `"locks"`, `"constraints-and-objectives"`, plus `"overview"` for the first group) everywhere a group is identified in the frontend (query-key segment, `?group=` URL value in Task 4). This is deliberate: Story 2.8's evidence-link navigation will target `/scenarios/:scenarioId/data?group=<same-slug>` later, and reusing today's vocabulary avoids a translation layer then.
  - [x] **AC #3 is satisfied structurally, not by a runtime toggle.** No `AgentRuntime` exists yet anywhere in this codebase (Story 2.1 introduces it in Epic 2) — there is nothing to simulate "down." Satisfy this AC by construction: every file this story adds under `frontend/src/features/scenario-data/`, `frontend/src/routes/ScenarioData.tsx`, `frontend/src/api/scenarioProjection.ts`, and `frontend/src/hooks/useScenarioProjection.ts` must import nothing from `frontend/src/api/constraints.ts`, `frontend/src/api/insights.ts`, `frontend/src/hooks/useApplyConstraint.ts`, `frontend/src/hooks/useRunInsights.ts`, or any future agent/chat module. Add a test proving this (see Task 6).

- [x] Task 4: Scenario Data group navigation + seven group panels (AC: #1, #2)
  - [x] New route `frontend/src/routes/ScenarioData.tsx` (thin, mirrors `FixtureCatalogue.tsx`'s route/view split): reads `scenarioId` via `useParams()`, renders `<ScenarioDataView scenarioId={scenarioId} />`.
  - [x] New file `frontend/src/features/scenario-data/ScenarioDataView.tsx` — owns the **group navigation**, which genuinely is shadcn `Tabs` from `@/components/ui/tabs` (per DESIGN.md: "Scenario group navigation | Inherits shadcn Tabs or Select") because this one switches content *within one route*, not across routes. Wire `Tabs`'s `value`/`onValueChange` to a `?group=` search param via `useSearchParams()` — this is the URL-serialization EXPERIENCE.md requires ("selection is reflected in the URL"). Default to `"overview"` when the param is absent or holds a value outside the known seven-slug set (defensive guard against a hand-edited/garbage URL — don't crash, don't silently 404, just fall back).
  - [x] Seven `TabsTrigger`s in the **fixed required order**: Overview, Work areas and tasks, Workers, Demand, Baseline assignments, Locks, Constraints and objectives (EXPERIENCE.md's exact group list/order — this order is load-bearing, not cosmetic: agent evidence citations in later epics use the same vocabulary).
  - [x] **Do not pass `forceMount` to `TabsContent`.** Verified in `frontend/node_modules/@radix-ui/react-tabs`: `Content`'s `forceMount` prop is optional and defaults unset, meaning Radix unmounts inactive `TabsContent` from the DOM by default. Put each group's data-fetching hook call *inside* that group's panel component (not lifted to `ScenarioDataView`) so switching to a tab is what triggers its first fetch — this gets you "only fetch the active group" for free, with no manual `enabled` gating needed beyond what Task 3's hooks already do for `scenarioId`.
  - [x] New shared wrapper `frontend/src/features/scenario-data/ScenarioDataTable.tsx` — the identical chrome all six list-shaped groups need: a bordered `overflow-auto` scroll container (AC #2 "contained two-axis scroll" / UX-DR31 "horizontal overflow must stay inside labelled table regions, never the page") wrapping `@/components/ui/table`'s `Table`, with a sticky, opaque, muted-background header row (AC #2 "sticky orientation cues" / DESIGN.md "sticky opaque header... Header surface uses inherited muted tone" — shadcn's `TableHeader` has no sticky styling by default, add `className="sticky top-0 z-10 bg-muted"` yourself). Props: `caption: string`, `children` (caller supplies its own `<TableHeader>`/`<TableBody>`). **Every `<TableHead>` must carry an explicit `scope="col"`** — shadcn's `TableHead` renders a plain `<th>` with no `scope`, and AC #2's "stable headers" / EXPERIENCE.md's Accessibility Floor ("`<th scope>` associations") requires it; this isn't added automatically. Do not build a generic column-config system on top of this — Overview's key/value layout genuinely differs from the six list groups, and a config-driven generic table would need as much per-group code as a plain component. Three similar-looking tables beat one premature abstraction here.
  - [x] New shared wrapper `frontend/src/features/scenario-data/ScenarioDataGroupState.tsx` — the four-state branching (loading skeleton / error+retry / empty / loaded) EXPERIENCE.md's State Patterns table prescribes identically for every Scenario Data group. Props: `{ isPending, isError, isEmpty, onRetry, children }`. Loading → `Skeleton` rows matching the caller's expected column count (caller passes `columnCount`). Empty (loaded, zero items) → the exact literal EXPERIENCE.md copy for an **intrinsically empty group**: `"This fixture has no records in this group."` (not the filtered-empty copy — no filters exist until Story 1.8, and `baseline-assignments`/`locks` are *always* empty per Story 1.4, so every fixture hits this state for those two groups). Loaded with items → renders `children`. **Error with no cached data — check whether Story 1.6 has shipped `frontend/src/components/primitives/` first:** if `InlineAlert.tsx`/`EmptyState.tsx` exist there, build this state on top of them (Story 1.6's whole purpose is exactly this reuse — `InlineAlert` with `variant="destructive"`, `USER_ERROR_COPY.connection`'s title/description, Retry as its `action`; `EmptyState` for the empty branch instead of a bare `<p>`). If Story 1.6 hasn't shipped yet, compose raw shadcn `Alert`/`AlertTitle`/`AlertDescription` directly, mirroring `FixtureCatalogueView.tsx`'s `UnavailableCatalogue`/`EmptyCatalogue` — do not block this story on 1.6 landing first, but don't hand-roll a third copy of this pattern if the primitive already exists when you get here.
  - [x] Seven panel files under `frontend/src/features/scenario-data/groups/`, each calling its Task 3 hook and rendering through `ScenarioDataGroupState` + `ScenarioDataTable`:
    - `OverviewPanel.tsx` — **not a list table**; a key/value semantic table (`<table><caption>Overview</caption><tbody><tr><th scope="row">...</th><td>...</td></tr>...</tbody></table>`, still inside `ScenarioDataTable`'s scroll chrome for consistency). Rows: Scenario name (`scenario_name`), Scenario ID (`scenario_id`, monospace), Fixture version (`fixture_version`, monospace), Baseline version (`baseline_schedule_version ?? "Not established"`, monospace — same fallback copy `ScenarioVersionContext.tsx` already uses), Time horizon (`horizon_start` via `formatTimestamp` + `horizon_minutes`, e.g. "starts {formatTimestamp(horizon_start)}, {horizon_minutes} minutes"), Site timezone (`site_timezone`), Last verified (`projection_generated_at` via `formatTimestamp` — this is the field the Structural Seed explicitly says "rendered by the UX as the 'last verified' timestamp"), then the seven counts (`work_area_count`, `task_count`, `worker_count`, `demand_interval_count`, `baseline_assignment_count`, `lock_count`, `constraint_count`) each as its own row.
    - `WorkAreasAndTasksPanel.tsx` — columns: Task ID (`task_id`, monospace), Name, Function, Area ID (`area_id`, monospace), Area name, Unit type ID (`unit_type_id ?? "—"`).
    - `WorkersPanel.tsx` — columns: Contact ID (`contact_id`, monospace), Name, Employment type, Grade, EBA (`eba`), Contracted hours, Qualifications, Availability windows. `qualifications` and `availability_windows` are arrays — render each cell as a joined string: qualifications → `"{task_id} ({rate})"` joined by `", "`; availability windows → `"{kind} " + formatMinuteWindow(start_minute, end_minute)` joined by `"; "` (see Task 4's `formatMinuteWindow` note below). Empty array → `"—"`.
    - `DemandPanel.tsx` — columns: Record ID (`record_id`, monospace), Family (`family`), Task ID (`task_id`, monospace), Area ID (`area_id ?? "—"`, monospace), Window (`formatMinuteWindow(start_minute, end_minute)`), Amount, Unit (`unit`).
    - `BaselineAssignmentsPanel.tsx` — columns: Record ID, Worker ID (`worker_id`, monospace), Task ID (`task_id`, monospace), Shift ID (`shift_id ?? "—"`, monospace), Window. **Always renders the intrinsic-empty state** — Story 1.4 permanently returns `items: []` for this group until Epic 3/4 exist; do not treat an empty response as a bug or add a workaround.
    - `LocksPanel.tsx` — columns: Record ID, Target type (`target_type`), Target ref (`target_ref`, monospace), Scope, Source. **Always renders the intrinsic-empty state**, same reason as above.
    - `ConstraintsPanel.tsx` — columns: Record ID, Constraint type (`constraint_type`), Value, Value type (`value_type ?? "—"`).
  - [x] In `frontend/src/lib/formatShiftWindow.ts`, add `export function formatMinuteWindow(startMinute: number, endMinute: number): string { return formatShiftWindow(startMinute / 60, endMinute / 60); }`. The existing function's "Day N, HH:MM–HH:MM" math (floor by 1440 minutes/day from an origin instant) applies identically to the new AD-20 minute-offset convention — both represent minutes-from-horizon-start with the same day-boundary semantics (`domain/problem.py`'s old hour-offset horizon and the new `ScenarioProjectionV1` minute-offset horizon are the same concept at different units). Add a focused test (`formatShiftWindow.test.ts`) for the new export; don't duplicate `formatDayTime`'s internal logic.
  - [x] `Record ID`, `Task ID`, `Contact ID`/`Worker ID`, `Area ID`, `Shift ID` cells use `font-mono text-xs` with `title={value}` — same convention `ScenarioVersionContext.tsx`/`FixtureCatalogueView.tsx` already use for identifiers. No copy-to-clipboard control yet (UX-DR17, Story 1.8's scope).
  - [x] Mutation-denial (AC #2): no `<input>`, `<select>` (other than the group-nav Tabs itself), checkbox, editable `contentEditable`, drag handle, "..." overflow menu, or button implying create/edit/delete anywhere under `frontend/src/features/scenario-data/`. This is a visual/structural constraint, not just a backend one — Story 1.4/1.5 already made the backend GET-only; this task makes the frontend visually match FR24/UX-DR4.

- [x] Task 5: Honest placeholder content for Chat, Runs, and Results (AC: #1)
  - [x] `frontend/src/routes/ScenarioChat.tsx`, `ScenarioRuns.tsx`, `ScenarioResults.tsx` each render a small shared placeholder (new component, e.g. `frontend/src/components/layout/WorkspaceTabPlaceholder.tsx` with `{ title, description }` props) rather than three near-duplicate files. **Do not reuse `frontend/src/components/layout/PlaceholderView.tsx` verbatim** — its copy ("ships in a later phase of the v0.4 milestone") names the *retired* pre-Gate-A milestone and its own comment says it backed the now-removed legacy Editor/Runs/Results tabs (see `AppBar.tsx`'s comment: "Story 1.3 retired the legacy Editor/Runs/Results tabs"). It's fine to delete `PlaceholderView.tsx` if it's confirmed unused after this story, or repurpose it with new copy — just don't ship the old wording.
  - [x] Exact copy: Chat → title "Chat", description "Conversational investigation is not available yet." Runs → title "Runs", description "Run history and manual optimization are not available yet." Results → title "Results", description "Run results are not available yet." (Optionally include the `runId` from `useParams()` in Results' copy, e.g. "for run {runId}" — not required.)
  - [x] Each wraps its placeholder in the `mx-auto max-w-6xl` div per Task 1's layout note.

- [x] Task 6: Tests
  - [x] `frontend/src/features/scenario-workspace/WorkspaceTabs.test.tsx` (new): renders all four items in order; Chat/Scenario Data/Runs are real links with correct `href`s; active item carries `aria-current="page"` and the indigo/underline treatment (assert via class or computed attribute, not just presence); Results is not a link/button (not in `getAllByRole("link"/"button")`), has `aria-disabled="true"`, and the literal explanation text is present unconditionally (not only on hover/focus).
  - [x] `frontend/src/routes/ScenarioWorkspace.test.tsx` (**must be updated, not just extended**): the existing test `"renders persistent context and only the literal next-surface placeholder"` (lines 59-78 today) asserts `screen.queryByRole("tab")` is absent and `"Chat"`/`"Runs"`/`"Results"` text is absent — **this assertion is now wrong and must be rewritten** to assert the opposite: `WorkspaceTabs` renders with all four labels present, Results disabled. Every other existing test in this file (loading, 401, terminal 404/422, generic error+retry, stale-with-cached-data, focus-management) returns before reaching the tab bar and should need no changes — verify each still passes as-is; if `renderWorkspace()`'s local route config needs `children` added so `<Outlet />` has somewhere to render (it will, since `ScenarioWorkspace` now renders `<Outlet />`), add a trivial stub `index` child (e.g. `{ index: true, element: <p>stub</p> }`) rather than wiring the real `ScenarioChat`.
  - [x] `frontend/src/routes/router.test.tsx` (**must be updated**): the test `"routes removed legacy children and unknown paths to RootErrorBoundary"` (lines 153-174 today) currently asserts `/scenarios/${scenarioId}/runs` and `/scenarios/${scenarioId}/runs/run-1` hit `RootErrorBoundary` — **remove these two paths from that list** (keep `/nope`, which is still genuinely unknown) and add new assertions in the main `describe("governed route tree", ...)` block that those two paths now mount real content (`ScenarioRuns`'s "Runs" placeholder heading and `ScenarioResults`'s "Results" placeholder heading, respectively — not an error boundary). Add one more assertion that `/scenarios/${scenarioId}/data` mounts `ScenarioData` (assert the default-selected "Overview" tab and its heading/caption).
  - [x] `frontend/src/api/scenarioProjection.test.ts` (new, mirrors `scenarioCatalogue.test.ts`'s shape): one test per function proving the correct path/params are sent and errors carry `status`.
  - [x] `frontend/src/hooks/useScenarioProjection.test.tsx` (new, mirrors `useScenarioContext.test.tsx`'s shape): each hook calls its API function with the right `scenarioId`, is `enabled: false` when `scenarioId` is empty, and does not retry on error.
  - [x] `frontend/src/features/scenario-data/ScenarioDataView.test.tsx` (new): renders all seven group tabs in the exact required order; defaults to Overview with no `?group=` param; selecting a tab updates the URL `?group=` value; an unknown/garbage `?group=` value falls back to Overview without crashing; switching tabs and back does not re-render a group that was never selected as having fetched (a reasonable proxy: mock each group hook and assert the never-visited ones were never called).
  - [x] Per-group panel tests (`OverviewPanel.test.tsx`, `WorkAreasAndTasksPanel.test.tsx`, `WorkersPanel.test.tsx`, `DemandPanel.test.tsx`, `BaselineAssignmentsPanel.test.tsx`, `LocksPanel.test.tsx`, `ConstraintsPanel.test.tsx`): loading skeleton, error+retry, empty (`"This fixture has no records in this group."` for baseline-assignments/locks at minimum — those are the two provably-always-empty groups), and loaded-with-rows rendering the right cell values from a fixture-shaped mock response. Each asserts a `<caption>`, `<th scope="col">` on every header, and the presence of no `<input>`/`<select>`/`<button>` implying mutation.
  - [x] `formatShiftWindow.test.ts`: extend with cases for `formatMinuteWindow`, including a cross-midnight case (mirrors the existing hour-based cross-midnight test).
  - [x] AC #3 structural proof: a test (e.g. in `ScenarioDataView.test.tsx` or a small dedicated test) that statically greps/imports-checks that no file under `frontend/src/features/scenario-data/`, `frontend/src/routes/ScenarioData.tsx`, `frontend/src/api/scenarioProjection.ts`, or `frontend/src/hooks/useScenarioProjection.ts` imports from `@/api/constraints`, `@/api/insights`, `@/hooks/useApplyConstraint`, or `@/hooks/useRunInsights`.
  - [x] Full regression before marking done: `npm run typecheck`, `npm run lint`, `npm run build`, `npm test` (frontend); `uv run --frozen pytest`, `alembic check` (backend — must show zero diff since this story touches no backend file).

### Review Findings

- [x] [Review][Patch] Scenario Data query hooks never call `useRedirectOnUnauthorized` — a 401 mid-browse leaves the user stuck in an infinite unusable "Retry" loop instead of the app's established sign-in redirect [frontend/src/hooks/useScenarioProjection.ts]
- [x] [Review][Patch] `ScenarioDataGroupState`'s error branch shows the same generic "connection" copy for every failure class (401/404/422/5xx); `ScenarioWorkspace` one level up already distinguishes terminal vs. transient statuses and this regresses that [frontend/src/features/scenario-data/ScenarioDataGroupState.tsx:30]
- [x] [Review][Patch] `ScenarioDataView`'s tab switch replaces the entire URL query string instead of merging (`setSearchParams({ group })`), silently dropping any other params — a forward risk since the story text says Story 2.8's evidence links will target this same `?group=` scheme alongside other params [frontend/src/features/scenario-data/ScenarioDataView.tsx:30]
- [x] [Review][Patch] Results tab uses `aria-disabled="true"` on a plain `<span>`, which has no defined ARIA semantics outside a widget role [frontend/src/features/scenario-workspace/WorkspaceTabs.tsx]
- [x] [Review][Patch] Every group panel hardcodes a `columnCount` prop that must be kept in sync by hand with its header array, with nothing tying the two together [frontend/src/features/scenario-data/groups/]
- [x] [Review][Patch] Shared `panelTestContract` only guards against `input`/`select`/`contenteditable`/`button`, not anchors or `role="button"` elements — a gap in AC #2's "no mutation-looking menus" enforcement for future panels [frontend/src/features/scenario-data/groups/panelTestContract.tsx]
- [x] [Review][Patch] All seven new group panel components are written as single ~800–1000 character one-line JSX returns, contradicting this project's documented multi-line JSX convention [frontend/src/features/scenario-data/groups/]
- [x] [Review][Patch] `WorkspaceTabPlaceholder`'s heading `id` is derived from `title.toLowerCase()` with no collision guard [frontend/src/components/layout/WorkspaceTabPlaceholder.tsx]

## Dev Notes

- **Story 1.6 ordering — check its actual status before writing token/primitive-adjacent code, don't assume either order.** Story 1.6 ("Establish ShiftMind Design Tokens and Shared Primitives") now has its own complete story file (`1-6-establish-shiftmind-design-tokens-and-shared-primitives.md`, status `ready-for-dev`), but neither story blocks the other structurally — Story 1.6's own Task 3 explicitly lists Workspace tabs and the Scenario Data grid as out of scope, deferred to this story. What actually depends on ordering: (a) **`--primary`/indigo styling** — see Task 2's inline guidance, check `index.css` first. (b) **`ScenarioDataGroupState`'s error/empty branches** — see Task 4's inline guidance, prefer Story 1.6's `InlineAlert`/`EmptyState` if they exist by the time you implement this. (c) **`ScenarioWorkspace.tsx` — both stories edit this file, in adjacent but non-overlapping regions.** Story 1.6's Task 6 touches the `query.isError && !query.data` alert block (today's lines ~84-120); this story's Task 1 touches only the success-path `<main>` return block (today's lines ~122-163). If both stories are implemented close together, expect a normal (non-semantic) merge/rebase between them, not a real logic conflict. Everything else this story needs (`Tabs`, `Table`, `Skeleton`, `Alert`, `Button` from `frontend/src/components/ui/`) already exists independent of Story 1.6.
- **Two different "tabs" in this story — do not conflate them.** Workspace tabs (Chat/Scenario Data/Runs/Results, Task 2) are real routes rendered as styled `NavLink`s. Scenario group navigation (Overview/Work areas.../Constraints, Task 4) is Radix `Tabs` switching content within one route, reflected in `?group=`. They share a visual "tab" vocabulary in the UX docs but nothing in implementation.
- **Two different "overview" concepts — do not conflate them.** `useScenarioContext`/`ScenarioContext` (Story 1.3, `GET /api/v1/scenarios/{scenario_id}`) backs the persistent top-of-page context bar and is unchanged by this story. The Scenario Data "Overview" group (Story 1.4, `GET /api/v1/scenarios/{scenario_id}/projection`, `ScenarioOverviewOut`) is new and has more fields (counts, `projection_generated_at`). Both exist simultaneously on the same page when Scenario Data is open.
- **Radix `Tabs.Content` unmounts inactive panels by default** (confirmed against `frontend/node_modules/@radix-ui/react-tabs`'s types — `forceMount` is optional/unset by default). Put each group's query hook call inside its own panel component so tab selection is what triggers the fetch; this is the whole lazy-loading mechanism, no manual `enabled`-per-active-tab wiring needed.
- **What NOT to build.** No pagination/next-prev controls, no sorting, no filtering, no column chooser, no identifier copy-to-clipboard control, no evidence links, no run-selection logic for Results — all named Story 1.8 (or later epics) in epics.md and explicitly out of this story's three ACs. Fetch and render exactly the initial window (`cursor=0`, server default `limit=50`) of each group.
- **Domain purity / layering is irrelevant here** — this is a pure frontend story, nothing in `backend/` changes. Do not touch `backend/application/`, `backend/adapters/`, `backend/api/`, or any migration.
- **Test conventions:** Vitest + React Testing Library, co-located `*.test.tsx`/`*.test.ts` files, mock hooks with `vi.mock(...)` the same way `ScenarioWorkspace.test.tsx`/`router.test.tsx` already mock `useScenarioContext`/`useFixtureCatalogue` — don't mock `openapi-fetch`/`client.ts` directly in component tests, mock at the hook boundary.

### Project Structure Notes

- New frontend files converge on the Structural Seed's `frontend/src/features/` (chat/scenario-data/runs/results grouping) and `frontend/src/routes/` (route composition only) split:
  - `frontend/src/routes/ScenarioChat.tsx`, `ScenarioData.tsx`, `ScenarioRuns.tsx`, `ScenarioResults.tsx` (new)
  - `frontend/src/features/scenario-workspace/WorkspaceTabs.tsx` (new, alongside existing `ScenarioVersionContext.tsx`)
  - `frontend/src/features/scenario-data/ScenarioDataView.tsx`, `ScenarioDataTable.tsx`, `ScenarioDataGroupState.tsx` (new)
  - `frontend/src/features/scenario-data/groups/{Overview,WorkAreasAndTasks,Workers,Demand,BaselineAssignments,Locks,Constraints}Panel.tsx` (new)
  - `frontend/src/api/scenarioProjection.ts` (new, mirrors `scenarioCatalogue.ts`)
  - `frontend/src/hooks/useScenarioProjection.ts` (new, mirrors `useScenarioContext.ts`)
  - `frontend/src/components/layout/WorkspaceTabPlaceholder.tsx` (new, small)
  - `frontend/src/lib/formatShiftWindow.ts` (extended with `formatMinuteWindow`)
- Edited existing files: `frontend/src/App.tsx` (route tree), `frontend/src/routes/ScenarioWorkspace.tsx` (shell only, all existing branches preserved), `frontend/src/routes/ScenarioWorkspace.test.tsx`, `frontend/src/routes/router.test.tsx`.
- `backend/`, `frontend/src/api/schema.d.ts`, `frontend/openapi.json` are **untouched** — no codegen needed, the types this story needs already exist from Story 1.4/1.5.
- `frontend/src/components/{editor,runs,results,scenarios}/` remain frozen legacy (AD-25) — untouched. `frontend/src/components/layout/PlaceholderView.tsx` is not in that frozen list and may be deleted/repurposed per Task 5.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.7, lines 481-502] — story statement and the three acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6, lines 461-479] — the design-tokens story this one was originally scoped to depend on; now `ready-for-dev` with its own story file (see below)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4, lines 407-434 and Story 1.5, lines 436-459] — the backend contract this story consumes unmodified
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md] — route/surface map (route table, line ~32-42), fixed Scenario Data group order and copy (line ~44-56), Voice and Tone table, Component Patterns table (Workspace tabs, Scenario/version context, Scenario group navigation, Scenario Data grid, Filter bar/Column chooser deferred), Large-table contract, State Patterns table (Scenario Data row), Responsive & Platform, Accessibility Floor
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md] — colors/typography/spacing tokens, `workspace-tabs`/`scenario-data-grid` component deltas, Layout & Spacing (full-width Scenario Data vs centered Chat/Runs/Results)
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-4, AD-14, AD-26, Structural Seed] — one immutable scenario projection; TanStack Query as sole remote-cache owner; NFR35 already allocated/measured elsewhere; `frontend/src/features`/`routes` structural seed
- [Source: frontend/src/routes/ScenarioWorkspace.tsx] — the exact file/branches this story edits
- [Source: frontend/src/features/scenario-workspace/ScenarioVersionContext.tsx] — sibling component, `baseline_schedule_version ?? "Not established"` fallback copy convention reused in `OverviewPanel`
- [Source: frontend/src/App.tsx] — current route tree this story restructures
- [Source: frontend/src/components/layout/AppBar.tsx] — `NavLink` pattern to mirror for `WorkspaceTabs`; its comment explicitly names this story as where the workspace tabs arrive; the hardcoded indigo-hex workaround to reuse
- [Source: frontend/src/api/scenarioCatalogue.ts, frontend/src/hooks/useScenarioContext.ts] — exact thin-wrapper conventions `scenarioProjection.ts`/`useScenarioProjection.ts` must mirror
- [Source: frontend/src/features/fixture-catalogue/FixtureCatalogueView.tsx] — the loading/error/empty state-branching shape `ScenarioDataGroupState` generalizes
- [Source: frontend/src/lib/errors.ts] — `USER_ERROR_COPY`, `getErrorStatus`
- [Source: frontend/src/lib/formatShiftWindow.ts, formatTimestamp.ts] — existing formatters to extend/reuse
- [Source: frontend/src/components/ui/tabs.tsx, table.tsx, skeleton.tsx] — shadcn primitives already scaffolded and available without Story 1.6
- [Source: frontend/src/api/schema.d.ts, lines ~293-520 paths, ~531-1148 schemas] — exact endpoint paths, operation IDs, and response/item field names (`ScenarioOverviewOut`, `TaskPageOut`/`TaskProjectionOut`, `WorkerPageOut`/`WorkerProjectionOut`, `DemandIntervalPageOut`/`DemandIntervalOut`, `AssignmentPageOut`/`AssignmentOut`, `LockPageOut`/`LockOut`, `ConstraintPageOut`/`ConstraintProjectionOut`)
- [Source: frontend/node_modules/@radix-ui/react-tabs/dist/*.d.mts] — confirms `Tabs.Content`'s `forceMount` is optional/unset by default (verified directly, not assumed)
- [Source: frontend/src/index.css, lines ~57-58] — confirms `--primary` is still shadcn default, not indigo
- [Source: frontend/src/routes/router.test.tsx, lines 153-174] — the exact test assertions this story must update (legacy-retired-routes list)
- [Source: frontend/src/routes/ScenarioWorkspace.test.tsx, lines 59-78] — the exact test assertion this story must rewrite (no-tabs assertion)
- [Source: _bmad-output/implementation-artifacts/1-4-serve-the-normalized-scenario-read-contract.md] — full backend contract detail, field-by-field mapping, "always empty" rationale for baseline-assignments/locks
- [Source: _bmad-output/implementation-artifacts/1-5-resolve-exact-evidence-targets.md] — confirms this story is not its consumer (Story 2.8 is) and that the projection read path is stable
- [Source: _bmad-output/implementation-artifacts/1-6-establish-shiftmind-design-tokens-and-shared-primitives.md] — sibling story, `ready-for-dev` as of this story's creation; its Task 1 (`--primary`/`--ring`/evidence-token values), Task 2 (`AppBar.tsx` retokenized to `text-evidence-link`), Task 3 (`InlineAlert`/`EmptyState`/`StatusBadge`/etc. under `components/primitives/`), and Task 6 (its own edit to `ScenarioWorkspace.tsx`) are the exact source of the "check before you style" guidance in Tasks 2/4 above

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

### Implementation Plan

- Preserve the existing workspace loading/error/stale branches while converting its success surface into a parent route shell.
- Add route-backed workspace navigation and direct TanStack Query projection reads with exact generated OpenAPI response types.
- Build lazy URL-addressable Scenario Data groups on shared read-only table/state primitives, then prove all route, state, accessibility, and layering contracts with tests.

### Debug Log References

- `npm test -- --run ...` — story-focused red/green checks; final focused result: 15 files, 79 tests passed.
- `npm run typecheck`, `npm run lint`, `npm run build`, `npm test` — frontend completion gate; 68 files, 335 tests passed. Lint reported four existing Fast Refresh warnings and no errors.
- `uv run --frozen pytest` from `backend/` — 311 passed, 6 live tests deselected.
- `uv run --frozen alembic -c ../alembic.ini check` — no new upgrade operations detected.

### Completion Notes List

- Converted the scenario workspace into a full-width shared shell with real Chat, Scenario Data, Runs, and Results child routes; Results remains accessibly disabled until run selection exists.
- Added all seven generated-contract projection clients and query hooks with exact backend group slugs, disabled-empty-ID behavior, no retries, and no agent-runtime dependency.
- Added URL-backed, lazy-mounted group navigation and seven captioned semantic read-only panels with contained two-axis scrolling, sticky headers, scoped headers, approved state treatments, and minute-window formatting.
- Added honest shared placeholders for Chat, Runs, and Results and comprehensive API, hook, route, panel-state, accessibility, mutation-denial, and architectural-boundary coverage.
- Verified frontend typecheck/lint/build/all tests, backend regression tests, and zero Alembic schema diff.

### File List

- `_bmad-output/implementation-artifacts/1-7-open-the-read-only-scenario-data-workspace.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `frontend/src/App.tsx`
- `frontend/src/api/scenarioProjection.test.ts`
- `frontend/src/api/scenarioProjection.ts`
- `frontend/src/components/layout/WorkspaceTabPlaceholder.tsx`
- `frontend/src/features/scenario-data/ScenarioDataGroupState.tsx`
- `frontend/src/features/scenario-data/ScenarioDataTable.tsx`
- `frontend/src/features/scenario-data/ScenarioDataView.test.tsx`
- `frontend/src/features/scenario-data/ScenarioDataView.tsx`
- `frontend/src/features/scenario-data/groups/BaselineAssignmentsPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/BaselineAssignmentsPanel.tsx`
- `frontend/src/features/scenario-data/groups/ConstraintsPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/ConstraintsPanel.tsx`
- `frontend/src/features/scenario-data/groups/DemandPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/DemandPanel.tsx`
- `frontend/src/features/scenario-data/groups/LocksPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/LocksPanel.tsx`
- `frontend/src/features/scenario-data/groups/OverviewPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/OverviewPanel.tsx`
- `frontend/src/features/scenario-data/groups/WorkAreasAndTasksPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/WorkAreasAndTasksPanel.tsx`
- `frontend/src/features/scenario-data/groups/WorkersPanel.test.tsx`
- `frontend/src/features/scenario-data/groups/WorkersPanel.tsx`
- `frontend/src/features/scenario-data/groups/panelTestContract.tsx`
- `frontend/src/features/scenario-workspace/WorkspaceTabs.test.tsx`
- `frontend/src/features/scenario-workspace/WorkspaceTabs.tsx`
- `frontend/src/hooks/useScenarioProjection.test.tsx`
- `frontend/src/hooks/useScenarioProjection.ts`
- `frontend/src/lib/formatShiftWindow.test.ts`
- `frontend/src/lib/formatShiftWindow.ts`
- `frontend/src/routes/ScenarioChat.tsx`
- `frontend/src/routes/ScenarioData.tsx`
- `frontend/src/routes/ScenarioResults.tsx`
- `frontend/src/routes/ScenarioRuns.tsx`
- `frontend/src/routes/ScenarioWorkspace.test.tsx`
- `frontend/src/routes/ScenarioWorkspace.tsx`
- `frontend/src/routes/router.test.tsx`
- `frontend/src/test/scenarioDataBoundaries.test.ts`

## Change Log

- 2026-08-06: Implemented the read-only Scenario Data workspace, seven projection groups, route-backed workspace navigation, placeholders, and full verification coverage; moved story to review.
