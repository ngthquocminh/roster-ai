# Phase 4: Results & Insights - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-19
**Phase:** 04-results-insights
**Areas discussed:** Charting approach, Coverage cards & warnings layout, Schedule table presentation, Insights & non-terminal run states

---

## Charting approach

### Q: How should the demand-vs-served chart be built?

| Option | Description | Selected |
|--------|-------------|----------|
| Recharts | Widely paired with shadcn/ui, composable, responsive/tooltips for free | ✓ |
| Custom SVG/CSS bars | No new dependency, matches repo's minimal-deps pattern | |
| You decide | Let the planner/researcher pick | |

**User's choice:** Recharts

### Q: What should the chart show — by function, by day, or both?

| Option | Description | Selected |
|--------|-------------|----------|
| By function | Required vs served hours per task family — more actionable | ✓ |
| By day | Coverage fraction per weekday — shows weekly shape | |
| Both (two charts) | No information left out, more screen space/build | |

**User's choice:** By function

### Q: How should required vs served hours be encoded per function?

| Option | Description | Selected |
|--------|-------------|----------|
| Grouped bars | Two bars side-by-side per function | ✓ |
| Overlaid/single bar with fill | Compact, progress-bar-like | |
| You decide | Let the planner pick | |

**User's choice:** Grouped bars

### Q: Brand color or distinct required/served pair?

| Option | Description | Selected |
|--------|-------------|----------|
| Brand indigo + muted gray | Served = existing #4F46E5, required = muted gray | ✓ |
| Distinct semantic pair | e.g. blue/green, chart-convention but new colors | |
| You decide | Let the planner pick | |

**User's choice:** Brand indigo + muted gray

---

## Coverage cards & warnings layout

### Q: How should stat cards and coverage breakdowns be organized?

| Option | Description | Selected |
|--------|-------------|----------|
| Top stat row + separate breakdown table | 2 headline cards + table below | ✓ |
| Everything as cards | Grid of 13+ cards with real fixture data | |
| You decide | Let the planner pick | |

**User's choice:** Top stat row + separate breakdown table

### Q: Should the breakdown table repeat by-function numbers or focus on by-day only?

| Option | Description | Selected |
|--------|-------------|----------|
| Table = by-day only | No redundancy with the chart | ✓ |
| Table = both function and day | Precise numbers next to visual, some redundancy | |
| You decide | Let the planner pick | |

**User's choice:** Table = by-day only

### Q: Where should degenerate-solve warnings appear?

| Option | Description | Selected |
|--------|-------------|----------|
| Banner directly above the stat row | Seen before reading the numbers it qualifies | ✓ |
| Inline per affected function | More precise but easy to miss on skim | |
| You decide | Let the planner pick | |

**User's choice:** Banner directly above the stat row

### Q: How should a null total_cost/total_unmet_hours render?

| Option | Description | Selected |
|--------|-------------|----------|
| "Not computed" with a tooltip | Honest, explains why it's missing | ✓ |
| Em dash — | Matches TimestampCell precedent, no explanation | |
| You decide | Let the planner pick | |

**User's choice:** "Not computed" with a tooltip

---

## Schedule table presentation

### Q: How should the schedule table handle a large row count?

| Option | Description | Selected |
|--------|-------------|----------|
| Scrollable container, like RunHistoryTable | Reuses existing pattern | ✓ |
| Grouped by day | Easier to scan, more component work | |
| You decide | Let the planner pick | |

**User's choice:** Scrollable container, like RunHistoryTable

### Q: Should the schedule table support sorting/filtering?

| Option | Description | Selected |
|--------|-------------|----------|
| Server order only | Matches RunHistoryTable's explicit precedent | ✓ |
| Client-side sortable columns | More useful for scanning, new interaction pattern | |
| You decide | Let the planner pick | |

**User's choice:** Server order only

### Q: How should the shift window column display start_h/end_h?

| Option | Description | Selected |
|--------|-------------|----------|
| Day N + HH:MM | Converts raw offset to domain's own day convention | ✓ |
| Raw hour offsets | Zero conversion, meaningless without day-boundary math | |
| You decide | Let the planner pick | |

**User's choice:** Day N + HH:MM

---

## Insights & non-terminal run states

### Q: Should the insight report auto-fetch or be button-triggered?

| Option | Description | Selected |
|--------|-------------|----------|
| Button-triggered | Matches "on demand" framing, avoids unwanted LLM call | ✓ |
| Auto-fetch on mount | One less click, couples page-load to LLM latency | |
| You decide | Let the planner pick | |

**User's choice:** Button-triggered

### Q: What should the Results view show for a non-COMPLETED run (deep-link)?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse RunInFlightPanel / FAILED-error copy | Same Phase-3 components/copy, no new UI | ✓ |
| Redirect to Run History | Simpler route, but kills the deep link | |
| You decide | Let the planner pick | |

**User's choice:** Reuse RunInFlightPanel / FAILED-error copy

### Q: After a 502 insight failure, what should the insight area show?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline error + retry button | Distinct failure message, button re-enabled | ✓ |
| Silent — just re-enable the button | Simpler, no explanation given | |
| You decide | Let the planner pick | |

**User's choice:** Inline error + retry button

---

## Claude's Discretion

- Exact Recharts component composition, tooltip content/formatting, axis labels.
- Exact card/table visual styling within shadcn's `Card`/`Table` primitives.
- Whether the by-day breakdown table is a shadcn `Table` or a simpler list/grid.
- Retry-button copy and whether repeated 502s show cumulative context.
- How the RunOut fetch (for non-terminal branching) and the result fetch compose as TanStack Query hooks (one hook vs two).

## Deferred Ideas

- Coverage-by-day chart (the "both charts" option, not chosen — by-day stays table-only).
- Sortable/filterable schedule table (explicitly deferred in favor of server order).
- Reviewed-not-folded todos: demand deadline-fill scheduling, engine extraction, round-2 relative-gap stop, run cancellation/concurrency limits, DEMAND_LOAD tuning, per-scenario engine selection — all backend/engine, unrelated to this frontend results-rendering phase.
