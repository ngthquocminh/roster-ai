# Phase 4: Results & Insights - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The Results view, mounted at `/scenarios/:scenarioId/runs/:runId` (replacing
`ResultsPlaceholder.tsx`, the last of the four ScenarioLayout routes), where a
user reads a completed run's coverage summary, a demand-vs-served chart, the
solved schedule as a table, and can request a plain-language insight report
on demand.

Delivers: RES-01 (coverage cards, incl. RES-06 degenerate-solve warnings),
RES-02 (demand-vs-served chart), RES-03 (schedule table), RES-04 (on-demand
insights, branching on `ready` not status code), RES-05 (insight failure
isolation). This is the final phase of the v0.4 milestone — no backend
changes are required; every field this phase needs already exists in
`RunResult` / `InsightOut`.

**Not this phase:** No what-if compare, no run cancellation, no editing
overrides from here (Editor's job). No new backend endpoints or schema
changes — this is a pure frontend read/render phase against
`GET /runs/{id}/result` and `GET /runs/{id}/insights`, both already live.

</domain>

<decisions>
## Implementation Decisions

Four gray areas were discussed. All four landed on the recommended option.

### Charting (RES-02)
- **D-01: Add Recharts as a new dependency.** No chart library exists in
  `frontend/package.json` today (first one added in this project). Chosen
  over a hand-built SVG/CSS chart for its shadcn-idiomatic composability and
  built-in tooltip/responsive handling.
- **D-02: Chart shows coverage-by-function only**, not coverage-by-day — the
  more actionable breakdown for a scheduler. Grouped bars (required vs
  served side-by-side per function), not an overlaid/fill style.
- **D-03: Color pairing — served = existing brand indigo `#4F46E5`**
  (already used for active nav/links in `ScenarioLayout.tsx`), required =
  muted gray outline. No new colors introduced to the app's palette.

### Coverage cards & warnings (RES-01, RES-06)
- **D-04: Two-tier layout.** A top stat row (total cost, total unmet hours)
  + a separate breakdown table below for detail. Not "everything as cards"
  (would be 13+ cards with the real fixture: 4 functions + 7 days).
- **D-05: Breakdown table shows coverage-by-day only**, not by-function —
  by-function is already covered visually by the chart (D-02); the table
  fills the gap the chart leaves (by-day has no chart). No duplicated
  numbers between chart and table.
- **D-06: Warnings render as a banner directly above the stat row** — the
  user sees the coverage-honesty caveat *before* reading the numbers it
  qualifies, per ROADMAP's explicit framing ("RES-01 folds RES-06 in — the
  warnings are a coverage-honesty signal and belong next to the coverage
  they qualify"). Not inline-per-function (too easy to miss on skim).
- **D-07: Null `total_cost`/`total_unmet_hours` render as "Not computed"
  with an explanatory tooltip** (not a bare em dash) — the solver hitting
  its time limit before optimizing cost is a real, honest fact worth
  surfacing, consistent with this project's established
  never-hide-solver-limitations pattern (RUN-03's honest in-flight wait is
  the direct precedent).

### Schedule table (RES-03)
- **D-08: Scrollable container, reusing `RunHistoryTable.tsx`'s exact
  pattern** (fixed max-height, all rows rendered, internal scroll) — no new
  pagination or grouping-by-day component.
- **D-09: Server order only, no client-side sort/filter** — matches
  `RunHistoryTable`'s explicit "server ordering, no client re-sort"
  precedent (stated in that file's own header comment).
- **D-10: Shift window column shows "Day N, HH:MM–HH:MM"**, converting the
  raw `start_h`/`end_h` hour-offset floats into the domain's own day
  convention (day-2 06:00 = 30.0h, per `docs/API.md`'s time-representation
  note) — not raw decimal hours.

### Insights & non-terminal run states (RES-04, RES-05)
- **D-11: Button-triggered, not auto-fetch on mount.** Matches RES-04's own
  framing ("request... on demand") and avoids coupling page-load latency to
  an LLM call the user may not want — coverage/chart/schedule are already
  useful without it.
- **D-12: Non-COMPLETED deep-link handling.** `GET /runs/{id}/result` 409s
  before `COMPLETED`, but the Results route must stay deep-linkable (this
  project's SHELL-03 precedent treats deep-linkability as a real
  requirement). Fetch `GET /runs/{id}` (RunOut — always succeeds regardless
  of status) first and branch: `PENDING`/`RUNNING` reuses
  `RunInFlightPanel`'s honest-wait copy from Phase 3; `FAILED` reuses the
  run's `error` text treatment already built in `RunHistoryTable.tsx`
  (`FAILED_NO_ERROR_COPY` fallback). No new copy invented for states
  already solved in Phase 3.
- **D-13: 502 insight failure → inline error message + re-enabled retry
  button**, styled distinctly from the loading/ready states (mirrors Phase
  2's D-04 precedent of visibly distinct outcome treatments). Not silent —
  the user gets an explanation, not just a reset button. Per RES-05, this
  failure must not touch the rest of the view (coverage/chart/schedule stay
  intact and interactive).

### Claude's Discretion (planner decides; not pre-answered)
- Exact Recharts component choices (BarChart vs custom composition),
  tooltip content/formatting, axis labels.
- Exact card/table visual styling within shadcn's existing `Card`/`Table`
  primitives.
- Whether the breakdown table (D-05) is a shadcn `Table` or a simpler
  list/grid — not specified, just its data scope (by-day only).
- Retry-button copy and whether repeated 502s show cumulative context (e.g.
  "failed again") or reset each time.
- How `GET /runs/{id}` (D-12's RunOut fetch) and `GET /runs/{id}/result`
  compose as TanStack Query hooks (one hook with internal branching vs two
  separate hooks) — follow the established `useScenario`/`useOverrides`
  dependent-query pattern from Phase 2.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The API contract (authoritative — read first)
- `docs/API.md` — read specifically:
  - `GET /runs/{run_id}/result` — `RunResult` shape, `409` before
    `COMPLETED`, null-metric note ("the solver can report a non-finite
    cost... serialized as `None`").
  - `GET /runs/{run_id}/insights` — `InsightOut`'s two-shape `200` contract
    (`ready: true/false`) and the `502` failure path; **the client must
    branch on `ready`, not status code** (this is a hard project fact —
    `.planning/PROJECT.md` "v0.4 key context" item 2 restates it).
  - Model tables for `RunResult`, `RunOut`, `InsightOut`.
  - ⚠️ **Known doc gap the planner must fix in lockstep with this phase:**
    `docs/API.md`'s `RunResult` model table does **not** document a
    `warnings` field, but `GET /runs/{run_id}/result` actually returns a
    top-level `warnings: string[]` array (confirmed in
    `backend/services/serialize.py:44`, sourced from
    `backend/domain/result.py`'s `SolveResult.warnings` and populated by
    `backend/engine/cpsat/engine.py`'s degenerate-solve detection). This is
    the same doc/code drift pattern flagged in Phase 2's context (D-01
    note, referencing commit `93ca4e0`). Update `docs/API.md`'s `RunResult`
    example JSON and model table to include `warnings` as part of this
    phase's work — RES-06 depends on this field being real and documented.

### Backend surfaces this phase reads (no changes needed)
- `backend/api/routers/runs.py` — `get_run_result` (`GET /{run_id}/result`,
  raw `json.loads` of `result_json`, no Pydantic schema — the dict shape in
  `serialize.py` **is** the wire contract).
- `backend/services/serialize.py` — the exact `RunResult` JSON shape
  including the undocumented `warnings` field.
- `backend/domain/result.py` — `SolveResult.warnings: List[str]` — plain
  human-readable strings, already display-ready (no client-side formatting
  needed beyond rendering the string).

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` — RES-01..06 (this phase owns the final 6 of
  24 v0.4 requirements).
- `.planning/ROADMAP.md` "Phase 4" — goal, 5 success criteria, and Notes
  (esp. the `ready`-vs-status-code distinction and the null-metrics note).
- `.planning/PROJECT.md` "## Current Milestone: v0.4" + "v0.4 key context"
  table (item 2: insights two-shape contract; item 3: solves are slow and
  uncancellable — bears on the D-12 non-terminal-run branch).
- `.planning/phases/02-.../02-CONTEXT.md` — D-04's "visibly distinct
  outcome treatments" precedent, directly reused for D-13.

### Design rationale (the "why")
- `docs/design.md` — whole-system architecture (context, not a per-phase
  contract).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (frontend, established in Phases 1-3)
- **`frontend/src/api/client.ts` + `schema.d.ts`** — single typed
  `openapi-fetch` client. New wrappers for `GET /runs/{id}/result` and
  `GET /runs/{id}/insights` follow `frontend/src/api/runs.ts`'s existing
  pattern (which currently only wraps list/trigger — this phase adds the
  two result/insight wrappers to that same file or a sibling).
- **`frontend/src/hooks/useRuns.ts`** — TanStack Query pattern to follow for
  new `useRunResult`/`useRunInsights` hooks (self-terminating poll pattern
  is NOT needed here — result/insights are one-shot fetches, not polled).
- **`frontend/src/components/runs/RunInFlightPanel.tsx`** — reused verbatim
  per D-12 for the PENDING/RUNNING branch.
- **`frontend/src/components/runs/RunHistoryTable.tsx`** — reused for two
  patterns: its scrollable-container structure (D-08) and its
  `FAILED_NO_ERROR_COPY` / inline error-text treatment (D-12's FAILED
  branch).
- **`frontend/src/components/layout/ErrorBanner.tsx`** — pattern to extend
  for the warnings banner (D-06) — needs a warning-styled variant, not
  reused as-is (ErrorBanner is styled for errors, not coverage caveats).
- **`frontend/src/components/ui/*`** — shadcn primitives already present
  (`table`, `alert`, `button`) cover the table, warnings banner, and
  insight-retry button without new primitive components.
- **`frontend/src/lib/formatTimestamp.ts`** — pattern to follow (not reuse
  directly — it formats ISO timestamps, not hour-offset floats) when
  building the Day-N/HH:MM formatter for D-10.

### Established Patterns (do not re-litigate)
- **Server state = TanStack Query** (Phase 1 D). No raw `fetch`+`useState`.
- **Types generated, never hand-written** — `openapi-typescript` →
  `schema.d.ts`. Since this phase adds `warnings` to the documented API
  contract (doc-only fix, the field already exists at runtime), confirm
  whether `schema.d.ts` regen already includes `warnings` in `RunResult`
  (it's runtime JSON, not a Pydantic-validated response model, so the
  OpenAPI schema may already be silent on it either way — verify during
  planning/research).
- **shadcn/ui + Tailwind v4**, desktop-first. react-router.
- **"Server order only, no client re-sort"** — explicit precedent from
  `RunHistoryTable.tsx`'s header comment, now also D-09's rule for the
  schedule table.
- **Distinct visual treatment per outcome** — Phase 2's D-04 (provider-down
  banner ≠ validation-error style) is the direct precedent for D-13
  (insight-failure state ≠ loading/ready state).

### Integration Points
- **`frontend/src/routes/ResultsPlaceholder.tsx`** — the placeholder this
  phase replaces; mounts at ScenarioLayout's `runs/:runId` child route
  (`App.tsx` route table, `frontend/src/routes/ScenarioLayout.tsx`).
- **`ScenarioLayout.tsx`'s disabled "Results" nav tab** — already correctly
  wired to highlight (via `useMatch`) when a run's results page is active,
  even though it stays a non-clickable placeholder tab (no static path to
  link to without a `runId`) — this is an established Phase 1 decision, not
  something to revisit this phase.
- **`RunHistoryTable.tsx`'s row click** — already navigates to
  `/scenarios/:scenarioId/runs/:runId` (the exact route this phase builds
  the real view for); no navigation-source change needed.

</code_context>

<specifics>
## Specific Ideas

- Chart and breakdown table must never show the same number twice — each
  piece of coverage data (by-function vs by-day) has exactly one home (D-02
  + D-05).
- The warnings banner and the null-metric "Not computed" tooltip are both
  instances of the same underlying principle this project keeps reapplying:
  never hide or silently drop a solver limitation — say it plainly next to
  the number it affects (RUN-03, D-06, D-07 all trace back to this).

</specifics>

<deferred>
## Deferred Ideas

- **Coverage-by-day chart** — considered (the "both" option in the charting
  discussion) but not chosen; by-day stays table-only this phase. Could
  become a second chart in a future iteration if a user wants the visual.
- **Sortable/filterable schedule table** — explicitly deferred in favor of
  server order (D-09); would be a natural follow-up once schedules grow
  beyond the fixture's 40 shifts.

### Reviewed Todos (not folded)

`todo.match-phase 04` returned 6 matches; **all are false positives** from
backend/engine keyword overlap (`demand`, `solve`, `run`, `coverage`,
`task`) — the same pattern noted in every prior phase's context (the
matcher has no frontend-vs-backend notion). None belong to this phase:

| Todo | Why not folded |
|---|---|
| Demand scheduling deadline-fill vs flat hourly | Engine behavior change; unrelated to reading results. |
| Extract solver engine into a separate service | Post-POC architecture; unrelated. |
| Add round-2 relative-gap stop | v2 `OPS-02`; engine timing, not results rendering. |
| Add run cancellation and concurrency limits | v2 `OPS-01`; unrelated to a completed run's results. |
| Tune DEMAND_LOAD and task mix for even coverage band | Engine calibration; unrelated. |
| Add per-scenario engine selection | Backend/engine work; unrelated. |

</deferred>

---

*Phase: 4-Results & Insights*
*Context gathered: 2026-07-19*
