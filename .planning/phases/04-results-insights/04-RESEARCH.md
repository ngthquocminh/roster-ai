# Phase 4: Results & Insights - Research

**Researched:** 2026-07-19
**Domain:** React frontend read view (charting, typed API consumption, error-isolation UI) over an already-live FastAPI backend — no backend changes.
**Confidence:** HIGH (codebase-verified for architecture/contracts; MEDIUM for Recharts API surface via Context7; one package flagged SUS by the legitimacy gate — see audit).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Four gray areas were discussed. All four landed on the recommended option.

**Charting (RES-02)**
- **D-01: Add Recharts as a new dependency.** No chart library exists in `frontend/package.json` today (first one added in this project). Chosen over a hand-built SVG/CSS chart for its shadcn-idiomatic composability and built-in tooltip/responsive handling.
- **D-02: Chart shows coverage-by-function only**, not coverage-by-day — the more actionable breakdown for a scheduler. Grouped bars (required vs served side-by-side per function), not an overlaid/fill style.
- **D-03: Color pairing — served = existing brand indigo `#4F46E5`** (already used for active nav/links in `ScenarioLayout.tsx`), required = muted gray outline. No new colors introduced to the app's palette.

**Coverage cards & warnings (RES-01, RES-06)**
- **D-04: Two-tier layout.** A top stat row (total cost, total unmet hours) + a separate breakdown table below for detail. Not "everything as cards" (would be 13+ cards with the real fixture: 4 functions + 7 days).
- **D-05: Breakdown table shows coverage-by-day only**, not by-function — by-function is already covered visually by the chart (D-02); the table fills the gap the chart leaves (by-day has no chart). No duplicated numbers between chart and table.
- **D-06: Warnings render as a banner directly above the stat row** — the user sees the coverage-honesty caveat *before* reading the numbers it qualifies, per ROADMAP's explicit framing ("RES-01 folds RES-06 in — the warnings are a coverage-honesty signal and belong next to the coverage they qualify"). Not inline-per-function (too easy to miss on skim).
- **D-07: Null `total_cost`/`total_unmet_hours` render as "Not computed" with an explanatory tooltip** (not a bare em dash) — the solver hitting its time limit before optimizing cost is a real, honest fact worth surfacing, consistent with this project's established never-hide-solver-limitations pattern (RUN-03's honest in-flight wait is the direct precedent).

**Schedule table (RES-03)**
- **D-08: Scrollable container, reusing `RunHistoryTable.tsx`'s exact pattern** (fixed max-height, all rows rendered, internal scroll) — no new pagination or grouping-by-day component.
- **D-09: Server order only, no client-side sort/filter** — matches `RunHistoryTable`'s explicit "server ordering, no client re-sort" precedent (stated in that file's own header comment).
- **D-10: Shift window column shows "Day N, HH:MM–HH:MM"**, converting the raw `start_h`/`end_h` hour-offset floats into the domain's own day convention (day-2 06:00 = 30.0h, per `docs/API.md`'s time-representation note) — not raw decimal hours.

**Insights & non-terminal run states (RES-04, RES-05)**
- **D-11: Button-triggered, not auto-fetch on mount.** Matches RES-04's own framing ("request... on demand") and avoids coupling page-load latency to an LLM call the user may not want — coverage/chart/schedule are already useful without it.
- **D-12: Non-COMPLETED deep-link handling.** `GET /runs/{id}/result` 409s before `COMPLETED`, but the Results route must stay deep-linkable (this project's SHELL-03 precedent treats deep-linkability as a real requirement). Fetch `GET /runs/{id}` (RunOut — always succeeds regardless of status) first and branch: `PENDING`/`RUNNING` reuses `RunInFlightPanel`'s honest-wait copy from Phase 3; `FAILED` reuses the run's `error` text treatment already built in `RunHistoryTable.tsx` (`FAILED_NO_ERROR_COPY` fallback). No new copy invented for states already solved in Phase 3.
- **D-13: 502 insight failure → inline error message + re-enabled retry button**, styled distinctly from the loading/ready states (mirrors Phase 2's D-04 precedent of visibly distinct outcome treatments). Not silent — the user gets an explanation, not just a reset button. Per RES-05, this failure must not touch the rest of the view (coverage/chart/schedule stay intact and interactive).

### Claude's Discretion (planner decides; not pre-answered)
- Exact Recharts component choices (BarChart vs custom composition), tooltip content/formatting, axis labels.
- Exact card/table visual styling within shadcn's existing `Card`/`Table` primitives.
- Whether the breakdown table (D-05) is a shadcn `Table` or a simpler list/grid — not specified, just its data scope (by-day only).
- Retry-button copy and whether repeated 502s show cumulative context (e.g. "failed again") or reset each time.
- How `GET /runs/{id}` (D-12's RunOut fetch) and `GET /runs/{id}/result` compose as TanStack Query hooks (one hook with internal branching vs two separate hooks) — follow the established `useScenario`/`useOverrides` dependent-query pattern from Phase 2.

### Deferred Ideas (OUT OF SCOPE)
- **Coverage-by-day chart** — considered (the "both" option in the charting discussion) but not chosen; by-day stays table-only this phase. Could become a second chart in a future iteration if a user wants the visual.
- **Sortable/filterable schedule table** — explicitly deferred in favor of server order (D-09); would be a natural follow-up once schedules grow beyond the fixture's 40 shifts.
- No what-if compare, no run cancellation, no editing overrides from here (Editor's job). No new backend endpoints or schema changes.
</user_constraints>

## Project Constraints (from CLAUDE.md)

- **Tech stack is locked** for this milestone (Python/FastAPI/CP-SAT/SQLite backend); this phase is frontend-only and must not modify backend code, confirmed compatible with CONTEXT.md's "no backend changes" Phase Boundary.
- **Domain stays pure (no solver/web/LLM imports in domain layer)** — not implicated by this phase (frontend-only), but relevant to Pitfall 1's decision *not* to add a backend `response_model`: any future fix to the `RunResult` typing gap must still respect this architecture (a Pydantic response schema in `api/schemas.py` is an API-layer concern, not a domain-layer one, so it would not violate this constraint if ever undertaken in a later milestone).
- **Safety: NL-derived constraints applied as soft constraints only** — not implicated; this phase does not touch constraint application.
- **Resilience: insight generation is a separate post-run step so an LLM failure never invalidates a successfully computed schedule** — directly maps to RES-05 and D-13; this constraint is the backend-side mirror of what Pattern 3 (mutation-isolated insight fetch) implements client-side. Confirmed already true server-side (`GET /runs/{run_id}/insights`'s docstring: "the run's status/result are untouched" on `502`).
- **Testing: no live LLM API in CI — a stubbed provider must drive tests** — applies to this phase's frontend tests only by extension: tests must mock `getRunInsights`/`client.GET` (per the established `vi.mock("./client")` boundary-mock convention), never hit a real backend or LLM provider.
- **GSD Workflow Enforcement**: file-changing work for this phase must go through `/gsd-execute-phase` (already the established path per STATE.md's "Operator Next Steps"); this research does not itself change repo files outside `.planning/`.
- **Naming/style conventions** (snake_case Python, PascalCase TS components, etc.) — not backend-relevant here; frontend naming already follows the established `frontend/src/` conventions surveyed throughout this research (camelCase hooks/functions, PascalCase components, kebab-case-free file names matching component names).

## Summary

Phase 4 is a pure frontend read/render phase: three already-live backend endpoints
(`GET /runs/{id}`, `GET /runs/{id}/result`, `GET /runs/{id}/insights`) feed a single
new route component that replaces `ResultsPlaceholder.tsx`. The phase's only new
runtime dependency is a charting library (`recharts`, added transitively via
`npx shadcn add chart`), and its only non-trivial logic is (a) an hour-offset →
"Day N, HH:MM" formatter for the schedule table and (b) response-shape branching
for two endpoints that must NOT be treated alike (`/result` 409s before
`COMPLETED`; `/insights` returns `200 {ready:false}` instead).

The single most consequential research finding, not fully surfaced in CONTEXT.md,
is this: **`GET /runs/{run_id}/result` has no Pydantic `response_model`** (confirmed
in `backend/api/routers/runs.py:52-64` — it returns a raw dict via `json.loads`).
As a direct consequence, `openapi-typescript`'s generated `schema.d.ts` does **not**
model `RunResult` at all — not even partially. The response type resolves to
`{ [key: string]: unknown }`. This is a stronger finding than "the `warnings` field
is undocumented": the entire `RunResult` shape (including `warnings`) is invisible
to codegen, and no `docs/API.md` fix + `npm run codegen:types` regen will change
that, because the OpenAPI schema itself has no schema entry for this response body.
The established "types generated, never hand-written" convention must be
deliberately broken for this one response — see Pitfall 1 and Code Example 1 for
the recommended handling.

The second key finding: the docs' human-readable "day-2 06:00 = 30.0h" convention
(1-indexed, prose) and the raw `coverage_by_day` dict keys `"0".."6"` (0-indexed,
confirmed against `backend/engine/cpsat/builder.py:273`'s
`by_day[int(sv.start_h // 24)]`) are the **same underlying bucketing** expressed two
different ways. Getting the display conversion right for both D-10 (schedule
table) and D-05 (breakdown table) requires reading them as one system — see
Pitfall 2.

**Primary recommendation:** Add `recharts` via `npx shadcn add card chart` (not a
bare `npm install recharts`) — this pulls in the project's already-configured
shadcn registry (`components.json`, style `radix-nova`) and gives composable
`ChartContainer`/`ChartTooltip`/`ChartConfig` primitives that render the brand
indigo (`#4F46E5`, literal hex — not a CSS variable in this codebase) without
inventing a new theming layer. Hand-write a `RunResult` TypeScript interface
(documented deviation) sourced from `backend/services/serialize.py`, and treat
`docs/API.md`'s `RunResult` fix as informational/contract documentation only —
it cannot make `schema.d.ts` type this endpoint.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Coverage cards / warnings banner rendering | Browser / Client | — | Pure presentation of already-fetched JSON; no server logic needed |
| Demand-vs-served chart (Recharts) | Browser / Client | — | Client-side SVG rendering; data is already aggregated server-side (`coverage_by_function`) |
| Schedule table + Day-N/HH:MM formatting | Browser / Client | — | Pure display-format transform of `start_h`/`end_h` floats; no new backend endpoint |
| On-demand insight fetch/cache | API / Backend | Browser / Client | Backend owns generation + caching (`runs.insight_json`); client only triggers and renders the two-shape response |
| Non-COMPLETED deep-link branching (`RunOut`) | Browser / Client | API / Backend | Backend already exposes `GET /runs/{id}` unconditionally; client does the state-branch |
| `RunResult` typing gap | API / Backend (root cause) | Browser / Client (workaround) | The absence of a `response_model` is a backend typing gap; this phase works around it client-side per explicit "no backend changes" scope |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `recharts` | npm | 10+ yrs (first published 2015-08-07) | 49.1M/week | github.com/recharts/recharts | `SUS` (signal: "too-new") | **Flagged — planner must add `checkpoint:human-verify` before install, per protocol.** See note below. |

**Note on the SUS verdict:** the legitimacy seam's "too-new" signal fired against
`recharts@3.9.2`'s **publish timestamp** (2026-07-04, ~2 weeks before this
research), not the package's actual age. `npm view recharts time.created` returns
`2015-08-07` and weekly downloads are 49M — this is one of the most established
charting libraries in the npm ecosystem, currently on a fast v3.x release cadence
(3.2.0 → 3.9.2 across recent months per `npm view recharts versions`). This is a
plausible false positive of the "too-new" heuristic against a mature package's
latest patch release, not a slopsquat/hallucination signal. Per protocol the
`SUS` disposition and its `checkpoint:human-verify` requirement still apply — the
planner must not skip the checkpoint on the strength of this note — but the human
verifying it should be told a fast-moving 10-year-old package's latest patch is
what tripped the check, not an unknown/suspicious package name. `postinstall`
script: `null` (no suspicious install-time script).

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `recharts` (see above).

**Installation path:** do not `npm install recharts` directly. Run
`npx shadcn@latest add card chart` from `frontend/` — this both adds the
`Card`/`ChartContainer`/`ChartTooltip`/`ChartConfig` source files under
`src/components/ui/` (matching the project's established shadcn source-copy
pattern, e.g. Phase 2's `npx shadcn add textarea`) and declares `recharts` as a
new `package.json` dependency. Verify post-install with
`npm view recharts version` (expect `3.9.x`) and confirm zero *other* new
dependencies landed (mirrors the Phase 2 Textarea precedent in STATE.md).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `recharts` | `3.9.2` [VERIFIED: npm registry] | Grouped bar chart (demand-vs-served) | Already chosen in CONTEXT.md D-01; de facto standard React charting library, React 19 peer-dep compatible (`^16.8.0 \|\| ^17 \|\| ^18 \|\| ^19`) [VERIFIED: npm registry] |
| shadcn `chart` registry component | bundled with shadcn CLI `^4.13.0` (already a devDependency) [CITED: ui.shadcn.com/docs/components/chart] | `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartConfig` composition primitives over Recharts | Matches this codebase's existing "copy shadcn source, don't wrap" convention (Textarea precedent); ties chart colors to `ChartConfig`'s `var(--color-<key>)` pattern |
| shadcn `card` registry component | same CLI | `Card`/`CardHeader`/`CardContent` for the D-04 stat row | Not yet present in `frontend/src/components/ui/` (confirmed via glob — only `alert, button, dialog, input, select, table, tabs, textarea` exist today) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tanstack/react-query` | `^5.101.2` (already installed) | `useRunResult`, `useRun` (D-12), `useRunInsights` hooks | Established Server-state pattern from Phase 1 — no raw `fetch`+`useState` anywhere in this phase either |
| `openapi-fetch` client (`@/api/client`) | already installed | Typed GET wrappers for `/runs/{id}`, `/runs/{id}/result`, `/runs/{id}/insights` | Single client instance convention (`client.ts` header comment: "do not construct a second client") |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| shadcn `chart` wrapper components | Raw `recharts` `<BarChart>`/`<ResponsiveContainer>`/`<Tooltip>` with hand-rolled Tailwind color classes | Raw Recharts works fine (see Code Example 2) but loses the `ChartConfig`→CSS-variable color wiring shadcn's tooltip/legend components read automatically; more code for equivalent result |
| Hand-written `RunResult` TS interface | Add a Pydantic `RunResult`/`response_model` to the backend endpoint, then regen | Would give real codegen coverage and close the typing gap permanently, but is a backend schema change CONTEXT.md's Phase Boundary explicitly rules out ("no backend changes are required... no new backend endpoints or schema changes") |

**Installation:**
```bash
cd frontend
npx shadcn@latest add card chart
```

**Version verification:** `npm view recharts version` → `3.9.2`, published `2026-07-04T03:09:25.298Z` [VERIFIED: npm registry]. `npm view recharts peerDependencies` confirms React 19 support [VERIFIED: npm registry].

## Architecture Patterns

### System Architecture Diagram

```
Browser (React Router: /scenarios/:scenarioId/runs/:runId)
        │
        ▼
  ResultsView (route component, replaces ResultsPlaceholder.tsx)
        │
        │ 1. useRun(runId)  ──────────────► GET /runs/{run_id}          (RunOut, always succeeds)
        │        │
        │        ├─ status PENDING/RUNNING ──► render <RunInFlightPanel> (reused verbatim, D-12)
        │        ├─ status FAILED ───────────► render FAILED_NO_ERROR_COPY-style error (D-12)
        │        └─ status COMPLETED ────────┐
        │                                    ▼
        │                     2. useRunResult(runId) ──► GET /runs/{run_id}/result
        │                            │                    (409 before COMPLETED — never hit here
        │                            │                     because gated on step 1's COMPLETED)
        │                            ▼
        │              ┌─────────────┴──────────────┬────────────────────┐
        │              ▼                             ▼                    ▼
        │     Coverage stat row + warnings   Demand-vs-served      Schedule table
        │     banner (D-04, D-06, D-07)      grouped bar chart      (D-08, D-09, D-10)
        │     [total_cost, total_unmet_hrs]  (D-02, D-03; Recharts  [scrollable, server order,
        │     + coverage_by_day table (D-05)  BarChart via          Day-N/HH:MM formatted
        │                                     ChartContainer)        shift window]
        │
        │ 3. (button click, D-11) ──► useRunInsights.mutate() ──► GET /runs/{run_id}/insights
        │                                    │
        │                     ┌──────────────┼───────────────┐
        │                     ▼              ▼                ▼
        │              ready:true      ready:false        502 error
        │              (render report) (shouldn't happen  (inline error +
        │                               — button only      retry button,
        │                               enabled when        D-13; rest of
        │                               COMPLETED)           view untouched,
        │                                                    RES-05)
```

### Recommended Project Structure
```
frontend/src/
├── api/
│   ├── runs.ts              # ADD: getRun(runId) wrapper (GET /runs/{id}) — does not exist yet
│   ├── results.ts           # NEW: getRunResult(runId) wrapper + hand-written RunResult type
│   └── insights.ts          # NEW: getRunInsights(runId) wrapper (InsightOut is already typed)
├── hooks/
│   ├── useRun.ts            # NEW: useQuery(["run", runId]) — single-run fetch, not the list poll
│   ├── useRunResult.ts      # NEW: useQuery(["run", runId, "result"], enabled: run?.status === "COMPLETED")
│   └── useRunInsights.ts    # NEW: useMutation wrapper (button-triggered, D-11; see Code Example 3)
├── lib/
│   └── formatShiftWindow.ts # NEW: hour-offset -> "Day N, HH:MM" (D-10; see Code Example 1)
├── components/results/      # NEW directory
│   ├── CoverageSummary.tsx  # D-04 stat row + D-07 null-metric "Not computed" tooltip
│   ├── WarningsBanner.tsx   # D-06 — extends ErrorBanner's pattern with a warning variant
│   ├── CoverageByDayTable.tsx # D-05 breakdown table
│   ├── DemandVsServedChart.tsx # D-02/D-03 Recharts grouped bar
│   ├── ScheduleTable.tsx    # D-08/D-09/D-10
│   └── InsightPanel.tsx     # D-11/D-13 on-demand button + report/error states
└── routes/
    └── ResultsView.tsx      # replaces ResultsPlaceholder.tsx; composes useRun + branches (D-12)
```

### Pattern 1: Dependent-query gate on run status (extends Phase 2's `useScenario`/`useOverrides` pattern)
**What:** Fetch `RunOut` first (always succeeds); gate the `/result` fetch on `status === "COMPLETED"` via TanStack Query's `enabled` option — exactly the `useOverrides(scenarioId, { enabled: scenarioQuery.isSuccess })` shape already in this codebase.
**When to use:** Any time a second fetch's validity depends on a first fetch's resolved data (D-12's deep-link requirement — `/result` 409s if fetched too early).
**Example:**
```typescript
// Source: pattern mirrors frontend/src/hooks/useOverrides.ts (already in repo)
export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });
}

export function useRunResult(runId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["run", runId, "result"],
    queryFn: () => getRunResult(runId),
    enabled: options.enabled, // caller passes: runQuery.data?.status === "COMPLETED"
  });
}
```

### Pattern 2: Recharts grouped bar chart via shadcn `ChartContainer`
**What:** Two `<Bar>` series (`required_h`, `served_h`) per function, composed through shadcn's chart primitives so the brand color and tooltip styling stay consistent with the rest of the app's theming approach.
**When to use:** D-02/D-03's demand-vs-served chart.
**Example:**
```tsx
// Source: https://ui.shadcn.com/docs/components/chart (shadcn chart docs) + Context7 /recharts/recharts
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";

// coverage_by_function: Record<string, { required_h: number; served_h: number; pct: number }>
const chartData = Object.entries(result.metrics.coverage_by_function).map(
  ([fn, c]) => ({ function: fn, required_h: c.required_h, served_h: c.served_h }),
);

const chartConfig = {
  required_h: { label: "Required", color: "var(--muted-foreground)" }, // D-03: muted gray outline
  served_h: { label: "Served", color: "#4F46E5" }, // D-03: brand indigo — literal hex, matches
                                                     // ScenarioLayout.tsx's existing border-[#4F46E5]
                                                     // usage; this app has no --primary CSS var for it
} satisfies ChartConfig;

export function DemandVsServedChart({ data }: { data: typeof chartData }) {
  return (
    <ChartContainer config={chartConfig} className="min-h-[280px] w-full">
      <BarChart data={data}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="function" />
        <ChartTooltip content={<ChartTooltipContent />} />
        {/* D-03: required rendered as outline-only (no fill), served as solid fill */}
        <Bar dataKey="required_h" fill="none" stroke="var(--color-required_h)" strokeWidth={2} />
        <Bar dataKey="served_h" fill="var(--color-served_h)" />
      </BarChart>
    </ChartContainer>
  );
}
```
**Pitfall guard:** `ChartContainer` must carry an explicit `min-h-*`/`h-*`/`aspect-*` class — Recharts' underlying `ResponsiveContainer` renders nothing (`return null`) until it can measure a non-zero parent height on first paint [CITED: github.com/recharts/recharts ResponsiveContainerContextProvider source, via Context7].

### Pattern 3: On-demand fetch as a `useMutation`, not a `useQuery`
**What:** Model the button-triggered insight fetch (D-11) as a `useMutation` whose `mutationFn` is a `GET` call, not a `useQuery` with `enabled: false` + manual `refetch()`. This gives natural `isPending`/`isError`/`error` state for the D-13 retry button without extra local state.
**When to use:** Any read that is user-triggered rather than mount-triggered and needs simple retry semantics.
**Example:**
```typescript
// Source: pattern mirrors frontend/src/hooks/useTriggerRun.ts (useMutation over a networked call)
import { useMutation } from "@tanstack/react-query";
import { getRunInsights } from "@/api/insights";

export function useRunInsights(runId: string) {
  return useMutation({
    mutationFn: () => getRunInsights(runId),
  });
}

// In the component: insights.mutate() on button click; insights.isPending disables the
// button while in flight; on 502, insights.error is set and insights.isError renders the
// D-13 inline error — insights.mutate() again re-enables the retry without touching any
// other query (RES-05: coverage/chart/schedule stay mounted and untouched).
```

### Anti-Patterns to Avoid
- **Casting `client.GET("/runs/{run_id}/result", ...)`'s `data` straight to a hand-rolled type at the call site, repeated per component:** do this once in `api/results.ts`'s wrapper (mirrors `constraints.ts`'s single indexed-type-alias convention) so every consumer gets the same `RunResult` shape, not N ad-hoc casts.
- **Fetching `/runs/{id}/result` unconditionally on mount:** it 409s before `COMPLETED` — always gate behind the `RunOut` status check (Pattern 1), never behind a raw `try/catch` on the 409.
- **Branching insight readiness on HTTP status code:** `ready:false` is a `200`, not a `409` or `404`. The UI must read `data.ready`, never `response.status`, to decide "not ready yet" (RES-04's hard requirement, restated in `.planning/PROJECT.md`'s "v0.4 key context").

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Grouped bar chart with tooltip/responsive sizing | Custom SVG/CSS bar chart | `recharts` `BarChart` + shadcn `chart` wrapper | D-01's own reasoning: hand-rolled tooltip positioning and resize-observer logic is exactly the kind of "deceptively complex" problem a maintained library already solves correctly |
| Scrollable table container with fixed max-height | New pagination/virtualization component | `RunHistoryTable.tsx`'s exact `max-h-[420px] overflow-y-auto` pattern (D-08) | Already built, tested, and stylistically consistent — a second scroll-container implementation would drift |
| Currency/number formatting for cost cards | Manual string interpolation (`$` + `.toFixed(2)` + manual thousands separators) | `Intl.NumberFormat("en-US", { style: "currency", currency: "USD" })` | No currency formatter exists yet in `frontend/src/lib/` (confirmed via grep — only `formatTimestamp.ts` exists); hand-rolled thousands-separator logic is a classic off-by-one/locale bug source |

**Key insight:** every "don't hand-roll" item above already has either a library
(Recharts) or an in-repo precedent (`RunHistoryTable`'s scroll container,
`getErrorStatus`'s status-extraction helper) — this phase's actual net-new logic
should be limited to the Day-N/HH:MM formatter (Pitfall 2) and the hand-written
`RunResult` type (Pitfall 1), both of which are irreducible given the current
backend contract.

## Common Pitfalls

### Pitfall 1: `RunResult` has zero codegen type coverage — not just a missing `warnings` field
**What goes wrong:** A planner reads CONTEXT.md's framing ("check whether `schema.d.ts` regen already includes `warnings`") and assumes the fix is narrow — add `warnings` to `docs/API.md`, regen, done. In fact `GET /runs/{run_id}/result`'s FastAPI route (`backend/api/routers/runs.py:52`) declares **no** `response_model` at all, so `openapi-typescript` emits `content: { "application/json": { [key: string]: unknown } }` for its `200` response — confirmed by reading the generated `operations["get_run_result_runs__run_id__result_get"]` block in `schema.d.ts:615-636`. Regenerating after a `docs/API.md` prose fix changes **nothing** in `schema.d.ts`, because `docs/API.md` is hand-written documentation, not the OpenAPI source (`GET /openapi.json`, which FastAPI derives from `response_model`s it doesn't have here).
**Why it happens:** The endpoint returns `json.loads(run["result_json"])` — a raw dict — specifically because `SolveResult`'s dataclasses (`domain/result.py`) were serialized once by `serialize_result()` and never re-validated against a Pydantic model on the way out.
**How to avoid:** Hand-write a `RunResult` (and nested `Metrics`, `CoverageStat`, `ScheduleRow`) TypeScript interface in `frontend/src/api/results.ts`, sourced field-for-field from `backend/services/serialize.py` (the actual wire contract) — not from `docs/API.md` (documentation, can drift) and not from `schema.d.ts` (doesn't model it). Cast the wrapper's `data` to this interface once, with a comment explaining why (mirrors this codebase's existing practice of a single explanatory comment at the one deviation point, e.g. `formatTimestamp.ts`'s regex-not-`toLocaleString` rationale). Still perform the `docs/API.md` fix CONTEXT.md requests — it is real value (keeps the human-readable contract honest) — just don't expect it to produce type safety.
**Warning signs:** `RunResult` fields typed as `unknown` anywhere in the codebase's TS; a component doing `(result as any).metrics.total_cost`.

### Pitfall 2: "Day N" means two different things depending on which endpoint's data it labels
**What goes wrong:** `coverage_by_day`'s dict keys (`"0".."6"`) are 0-indexed — verified against the exact bucketing expression the engine itself uses, `by_day[int(sv.start_h // 24)]` in `backend/engine/cpsat/builder.py:273` (day bucket 0 = hours 0–24). But `docs/API.md`'s prose convention for `start_h`/`end_h` uses 1-indexed human language: "day-2 06:00 = `30.0`" (the *second* day = hours 24–48 = bucket index 1). If the breakdown table (D-05) renders raw keys as "Day 0, Day 1, ... Day 6" while the schedule table (D-10) renders `Math.floor(start_h / 24) + 1` as "Day 1, Day 2, ... Day 7", the *same calendar day* is labeled "Day 0" in one table and "Day 1" in the other on the same screen.
**Why it happens:** The backend has one 0-indexed internal bucketing scheme; `docs/API.md`'s prose description of it uses ordinary 1-indexed English ("the second day"). Both are correct in their own context — they just don't visually agree.
**How to avoid:** Pick one display convention and apply it to **both** tables. Recommended: 1-indexed everywhere the user reads "Day N" (matches `docs/API.md`'s own worked example and ordinary English). Concretely: breakdown table renders `Day ${Number(dayKey) + 1}`; schedule table's formatter computes `Math.floor(h / 24) + 1` (see Code Example 1). Do not silently keep the raw 0-indexed `coverage_by_day` keys as display text — verify this decision is made once and shared, not decided independently per component.
**Warning signs:** Two tables on the same Results page showing "Day 0" and "Day 1" for what a human tester recognizes as the same day.

### Pitfall 3: Shifts can legitimately cross midnight — "Day N, HH:MM–HH:MM" collapses that
**What goes wrong:** D-10's literal format spec, "Day N, HH:MM–HH:MM", assumes `start_h` and `end_h` fall on the same calendar day. `backend/ingest/scenario_time.py:31`'s `day_window_hours` docstring explicitly handles "windows that cross midnight (end <= start -> end is next day)" for roster/availability windows — the same underlying time representation shifts are built from. A night shift (e.g. 22:00–06:00) is a real, supported case in this engine, not a theoretical edge.
**Why it happens:** The domain's hour-offset representation has no inherent day boundary; only the display formatter imposes one.
**How to avoid:** In the formatter, compute `startDay`/`endDay` independently; if they differ, render `"Day N, HH:MM – Day N+1, HH:MM"` instead of the single-day-prefix format. See Code Example 1 for the exact function, which handles this branch.
**Warning signs:** A schedule row where `end_h < start_h` after `% 24` reduction, or a row whose rendered end-time is earlier than its start-time within the same "Day N" label.

### Pitfall 4: Recharts `3.x` is a major-version jump from most cached tutorials/answers (`2.x`)
**What goes wrong:** Most Recharts tutorials, StackOverflow answers, and even some shadcn blog posts reference Recharts `2.x` APIs. `3.x` changed `ResponsiveContainer`'s default `width`/`height` from numeric pixels to percentage strings (`'100%'`) [CITED: github.com/recharts/recharts responsiveContainerUtils.ts, via Context7] and introduced a `responsive` prop as an alternative to `<ResponsiveContainer>`. Code copied verbatim from an older guide can silently render at 0×0.
**Why it happens:** `recharts@3.9.2` (installed via shadcn CLI, see Standard Stack) is very recent; training-data-era examples predate the v3 breaking changes.
**How to avoid:** Follow the shadcn `chart` component's own generated `ChartContainer` (Pattern 2) rather than hand-rolling `<ResponsiveContainer>` usage from memory; if hand-rolling directly, always set an explicit `height`/`min-h-*` on the immediate parent, matching the verified pattern in Pattern 2's pitfall guard.
**Warning signs:** Chart container renders empty/blank on first load, then appears after a window resize.

### Pitfall 5: `total_cost`/`total_unmet_hours` are `null`, not `NaN`, not absent
**What goes wrong:** A naive `result.metrics.total_cost.toFixed(2)` throws `Cannot read properties of null` when the solver hits its time limit before proving cost-optimality (`_num()` in `backend/services/serialize.py:14-17` explicitly converts non-finite floats to JSON `null`). A naive `result.metrics.total_cost ?? 0` silently renders "$0.00" — actively misleading (looks like zero cost, not "not computed").
**Why it happens:** `math.isnan`/`math.isinf` values aren't valid JSON; `null` is the closest JSON-safe representation, and it's a legitimate, expected value for a time-limited `UNKNOWN`-status solve (see the worked example in `docs/API.md` itself: `"status": "UNKNOWN"` accompanies a real `total_cost` in the doc's example — but a *shorter* time-limited run can legitimately null it out).
**How to avoid:** Per D-07, render `total_cost == null` as literal text **"Not computed"** with an explanatory tooltip (not `"$0.00"`, not `"—"`). Same treatment for `total_unmet_hours`. `coverage_by_function[fn].required_h`/`served_h`/`pct` are independently nullable per-function — the chart and breakdown table must each guard per-value, not just at the top-level `metrics` object.
**Warning signs:** A completed run with `solver_status: UNKNOWN` showing `$0.00` or `NaN` anywhere on the Results page.

## Code Examples

### 1. Hour-offset to "Day N, HH:MM" formatter (D-10, handles cross-midnight per Pitfall 3, 1-indexed per Pitfall 2)
```typescript
// Source: derived from backend/ingest/scenario_time.py's hour-offset convention +
// backend/engine/cpsat/builder.py:273's `int(sv.start_h // 24)` day-bucket math +
// docs/API.md's "day-2 06:00 = 30.0" worked example (1-indexed prose).
// frontend/src/lib/formatShiftWindow.ts
function formatDayTime(h: number): { day: number; hhmm: string } {
  // Round once in total minutes to avoid a 23.999h -> "24:00" boundary bug from
  // independently rounding hours and minutes.
  const totalMinutes = Math.round(h * 60);
  const day = Math.floor(totalMinutes / 1440) + 1; // 1-indexed: hours 0-24 => "Day 1"
  const minutesOfDay = totalMinutes % 1440;
  const hh = String(Math.floor(minutesOfDay / 60)).padStart(2, "0");
  const mm = String(minutesOfDay % 60).padStart(2, "0");
  return { day, hhmm: `${hh}:${mm}` };
}

export function formatShiftWindow(startH: number, endH: number): string {
  const start = formatDayTime(startH);
  const end = formatDayTime(endH);
  if (start.day === end.day) {
    return `Day ${start.day}, ${start.hhmm}–${end.hhmm}`;
  }
  // Cross-midnight shift (Pitfall 3) — label both days explicitly.
  return `Day ${start.day}, ${start.hhmm} – Day ${end.day}, ${end.hhmm}`;
}
```

### 2. Hand-written `RunResult` type + wrapper (Pitfall 1)
```typescript
// Source: field-for-field from backend/services/serialize.py (the actual wire
// contract) — NOT from schema.d.ts (untyped for this endpoint; see Pitfall 1).
// frontend/src/api/results.ts
import { client } from "./client";

// DEVIATION from the codebase's "types generated, never hand-written" convention
// (see api/client.ts header comment): GET /runs/{run_id}/result has no FastAPI
// response_model, so openapi-typescript cannot type it (schema.d.ts resolves this
// response to `{ [key: string]: unknown }`). Hand-authored here against
// backend/services/serialize.py's serialize_result(); keep in sync manually if
// that function's shape changes.
export interface CoverageStat {
  required_h: number | null;
  served_h: number | null;
  pct: number | null;
}

export interface RunResult {
  status: string;
  metrics: {
    total_cost: number | null;
    total_unmet_hours: number | null;
    scheduled_shifts: number;
    scheduled_members: number;
    coverage_by_function: Record<string, CoverageStat>;
    coverage_by_day: Record<string, number | null>;
  };
  stats: {
    status: string;
    wall_time_s: number | null;
    unmet_objective_hours: number | null;
    cost_objective: number | null;
  };
  schedule: Array<{
    contact_id: string;
    member_name: string;
    task_id: string;
    function: string;
    shift_id: string;
    start_h: number;
    end_h: number;
  }>;
  warnings: string[]; // RES-06 — real at runtime, undocumented pre-phase-4 in docs/API.md
}

export async function getRunResult(runId: string): Promise<RunResult> {
  const { data, error, response } = await client.GET("/runs/{run_id}/result", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    throw { status: response.status, ...error }; // T-1-02 convention
  }
  return data as RunResult;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Recharts `<ResponsiveContainer width={numeric} height={numeric}>` | `<ResponsiveContainer width="100%" height="100%">` defaults, or the new `responsive` prop directly on chart components | Recharts `3.x` [CITED: github.com/recharts/recharts, via Context7] | Copying `2.x`-era snippets verbatim can silently 0×0-render (Pitfall 4) |
| shadcn CLI installing components by copying files with manually pinned versions | shadcn `chart` registry component pulls `recharts` as a real `package.json` dependency, versioned by npm | Ongoing (this project's shadcn CLI is `^4.13.0`, already installed) | `recharts` shows up in `npm view`/lockfile like any other dependency — the Package Legitimacy Audit above applies to it directly |

**Deprecated/outdated:**
- None specific to this phase's stack; `recharts@2.x` still functions but the shadcn CLI installs `3.x` by default as of this research date.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `npx shadcn add card chart` will add exactly `recharts` as the only new `package.json` dependency (no transitive UI deps beyond what's already installed) | Package Legitimacy Audit / Standard Stack | Low — verifiable at install time by diffing `package.json`; if wrong, the plan's post-install verification step catches it immediately (same pattern as the Textarea precedent) |
| A2 | 1-indexed "Day N" display (Pitfall 2's recommendation) is the correct UX choice over keeping the raw 0-indexed `coverage_by_day` keys | Pitfall 2 | Low-medium — either choice is internally consistent once applied uniformly; the real risk is the two tables disagreeing with each other, not which convention is picked. Flagged as `Claude's Discretion` in CONTEXT.md is silent on this specific point — recommend the planner confirm this displayed-day convention explicitly in the plan rather than leaving it implicit per-component. |
| A3 | No shift in the committed fixtures (`data/sample_tiny_input.json`, `data/sample_tiny_input_more_tm.json`) actually crosses midnight today | Pitfall 3 | Low — the cross-midnight branch (Code Example 1) is cheap defensive code either way; not verified against actual fixture data this session (would require parsing the full 420KB fixture), but the *code path* for cross-midnight windows is confirmed to exist and be reachable in `scenario_time.py` |

**If this table is empty:** N/A — see above.

## Open Questions

1. **Should `docs/API.md`'s `RunResult` fix use `warnings` as required or optional (`string[] | undefined`)?**
   - What we know: `backend/domain/result.py:53` defaults `warnings: List[str] = field(default_factory=list)`, and `serialize_result()` always includes the key (empty list, not omitted, when there are no warnings).
   - What's unclear: whether some historical `result_json` rows (recorded before `warnings` was added to `SolveResult`) predate the field and would deserialize without the key.
   - Recommendation: treat as `string[]` (never `undefined`) in the hand-written `RunResult` type per Code Example 2, but defensively render `warnings ?? []` at the one call site that maps it to the banner (D-06) — cheap insurance against pre-warnings-era cached `result_json` rows in the dev SQLite DB, at negligible cost.

2. **Exact visual treatment of the "muted gray outline" required-bar (D-03) — literal Tailwind token or CSS variable?**
   - What we know: D-03 specifies "required = muted gray outline" and explicitly "no new colors introduced to the app's palette."
   - What's unclear: whether `var(--muted-foreground)` (an existing shadcn theme token, confirmed present in `frontend/src/index.css`) is the intended "muted gray," versus one of the unused `--chart-1`..`--chart-5` tokens also already defined in that file.
   - Recommendation: use `var(--muted-foreground)` — it's the token already used elsewhere in this app for de-emphasized text (e.g. `RunHistoryTable`'s empty-state copy), keeping the chart visually consistent with existing muted-text usage rather than introducing an unused `--chart-N` token for the first time. Left as `Claude's Discretion` per CONTEXT.md; this is a recommendation, not a locked decision.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RES-01 | User can see coverage summary cards for a completed run | `RunResult.metrics` fully mapped in Code Example 2; D-04/D-07 null-handling in Pitfall 5; existing `Card`/`Alert` shadcn primitives (add `card` via CLI) |
| RES-02 | User can see a demand-vs-served chart for a completed run | Recharts + shadcn `chart` verified (Standard Stack, Pattern 2); `coverage_by_function` shape confirmed against `docs/API.md` and `serialize.py` |
| RES-03 | User can see the schedule as a readable table | `RunHistoryTable.tsx`'s scrollable/server-order pattern (D-08/D-09) reused directly; `formatShiftWindow` (Code Example 1) for the shift-window column |
| RES-04 | User can fetch a plain-language insight report on demand; UI branches on `ready`, not status code | `InsightOut` already fully typed in `schema.d.ts` (confirmed); Pattern 3's `useMutation` wrapper; Anti-Pattern section reiterates the ready-vs-status-code hazard |
| RES-05 | An insight failure (`502`) leaves the rest of the results view intact | Pattern 3's `useMutation` isolation — insight fetch state lives entirely in its own hook instance, structurally unable to affect `useRun`/`useRunResult`'s query state |
| RES-06 | Degenerate-solve warnings (`SolveResult.warnings`) are surfaced, not dropped | Confirmed real at runtime (`serialize.py:44`, `domain/result.py:53`) but absent from `schema.d.ts` — requires the hand-written `RunResult` type (Pitfall 1, Code Example 2) to be visible to the frontend at all; `docs/API.md` fix requested in CONTEXT.md is documentation-only, addressed separately from the type gap |
</phase_requirements>

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | frontend build/dev | ✓ | v22.22.0 [VERIFIED: local] | — |
| npm | package install, codegen scripts | ✓ | 10.9.0 [VERIFIED: local] | — |
| vitest | component/unit tests | ✓ | 4.1.10 [VERIFIED: local] | — |
| shadcn CLI | `card`/`chart` component install | ✓ (installed as `^4.13.0` devDependency; CLI itself invoked via `npx`) | 4.13.1 resolved during this research session [VERIFIED: local] | — |
| recharts | charting | not yet installed | will resolve to `3.9.2` via shadcn CLI [VERIFIED: npm registry] | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — `recharts` is not yet installed but has no environment blocker, only the package-legitimacy `SUS` checkpoint gate documented above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest `4.1.10` + `@testing-library/react` `16.3.2` (already configured; `frontend/package.json` `"test": "vitest run"`) |
| Config file | `frontend/vite.config.ts` (vitest config lives inline per existing convention — confirmed present) |
| Quick run command | `npm run test -- <pattern>` from `frontend/` (or `npx vitest run <file>`) |
| Full suite command | `npm run test` from `frontend/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RES-01 | Coverage cards render `total_cost`/`total_unmet_hours`, including null → "Not computed" | unit | `npx vitest run src/components/results/CoverageSummary.test.tsx` | ❌ Wave 0 |
| RES-01/RES-06 | Warnings banner renders above stat row when `warnings.length > 0`; renders nothing when empty | unit | `npx vitest run src/components/results/WarningsBanner.test.tsx` | ❌ Wave 0 |
| RES-02 | Chart renders one grouped bar pair per function with correct required/served values | unit | `npx vitest run src/components/results/DemandVsServedChart.test.tsx` | ❌ Wave 0 |
| RES-03 | Schedule table renders server order, no re-sort; shift window formats correctly incl. cross-midnight | unit | `npx vitest run src/components/results/ScheduleTable.test.tsx` + `src/lib/formatShiftWindow.test.ts` | ❌ Wave 0 |
| RES-04 | Insight panel branches on `ready` field, not HTTP status; `ready:false` never treated as an error | unit | `npx vitest run src/components/results/InsightPanel.test.tsx` | ❌ Wave 0 |
| RES-05 | A `502` from `getRunInsights` leaves `useRun`/`useRunResult` query state and rendered coverage/chart/schedule untouched | integration | `npx vitest run src/routes/ResultsView.test.tsx` | ❌ Wave 0 |
| D-12 | Non-COMPLETED deep link renders `RunInFlightPanel` (PENDING/RUNNING) or FAILED copy, never attempts `/result` | integration | `npx vitest run src/routes/ResultsView.test.tsx` | ❌ Wave 0 (same file as above) |

### Sampling Rate
- **Per task commit:** `npx vitest run <changed-file>.test.tsx`
- **Per wave merge:** `npm run test` (full suite) from `frontend/`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `frontend/src/lib/formatShiftWindow.test.ts` — covers RES-03 (day-boundary, cross-midnight, rounding cases from Pitfall 3)
- [ ] `frontend/src/api/results.test.ts` — covers the `RunResult` wrapper's error-throwing convention (mirrors `runs.test.ts`'s `vi.mock("./client")` boundary-mock pattern)
- [ ] `frontend/src/api/insights.test.ts` — same boundary-mock pattern for `getRunInsights`
- [ ] `frontend/src/components/results/*.test.tsx` — new directory, no existing fixtures; each component test needs a hand-built `RunResult`-shaped fixture object (no `schema.d.ts` type to build it against — construct against Code Example 2's interface)
- [ ] `frontend/src/routes/ResultsView.test.tsx` — integration coverage for D-12's three-way branch (PENDING/RUNNING, FAILED, COMPLETED) and RES-05's failure-isolation; follow `RunHistory.test.tsx`'s `createMemoryRouter` + mocked-hooks convention

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in v0.4 (documented Out of Scope in REQUIREMENTS.md) |
| V3 Session Management | no | Same — no sessions |
| V4 Access Control | no | Local/demo single-user app; no per-resource authorization model exists or is being added |
| V5 Input Validation | partial | This phase is read-only (no new user input except the insight-fetch trigger, which carries no payload); `runId`/`scenarioId` come from `useParams()` and are passed straight through as opaque path segments to the typed `openapi-fetch` client, which itself does no further validation — acceptable here because the backend 404s on an unknown id rather than trusting client-side shape |
| V6 Cryptography | no | No crypto operations in this phase |
| V7 Error Handling & Output Encoding | yes | React's default JSX text-node escaping is the established mitigation for all rendered strings in this codebase (explicitly documented in `RunHistoryTable.tsx`'s header comment and `ErrorBanner.tsx`) — this phase renders **three new untrusted-ish string sources**: `warnings[]` (solver-generated, not user input, but still free text), the LLM-generated `report` string (D-11/RES-04), and `member_name`/`function`/`task_id` fields (sourced from fixture data, not user input, but still rendered verbatim). None of these require `dangerouslySetInnerHTML`; render all as plain JSX children only. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reflected/stored XSS via LLM-generated `report` text rendered unsanitized | Tampering / Elevation of Privilege | Render `report` (a string) as a plain JSX text child only — never `dangerouslySetInnerHTML`, never `innerHTML`. The backend's numeric-grounding guard (`docs/API.md`'s "every number the report cites is checked... treated as a fabrication") mitigates *factual* fabrication but is not an XSS control — the frontend's plain-text rendering is the actual XSS mitigation and must not be weakened even though the content is LLM-sourced rather than directly user-typed. |
| Trusting an untyped (`unknown`) API response shape at multiple call sites | Tampering (type-confusion bugs, not a classic security vuln but a correctness/DoS-adjacent risk) | Single hand-written `RunResult` type + single wrapper function (Code Example 2) — one point of `as RunResult` casting, not N scattered casts that could each independently drift from the real backend shape |
| Insight failure (502) cascading into a broken results page (partial-failure blast radius) | Denial of Service (client-side availability) | `useMutation`-isolated insight fetch (Pattern 3) — structurally cannot affect the `useRun`/`useRunResult` query cache or their rendered output, satisfying RES-05 as both a UX requirement and a fault-isolation control |

## Sources

### Primary (HIGH confidence)
- `backend/api/routers/runs.py` — confirmed no `response_model` on `GET /runs/{run_id}/result`; confirmed 409/502 error paths and `ready`-branch contract in `get_run_insights`'s docstring
- `backend/services/serialize.py` — exact `RunResult` wire shape, including `warnings`
- `backend/domain/result.py` — `SolveResult.warnings: List[str]` default
- `backend/api/schemas.py` — confirmed `InsightOut`/`RunOut` Pydantic models exist; confirmed no `RunResult` model exists anywhere in this file
- `backend/engine/cpsat/builder.py:273` — `coverage_by_day`'s 0-indexed bucketing source of truth
- `backend/ingest/scenario_time.py` — hour-offset convention and cross-midnight window handling
- `frontend/src/api/schema.d.ts` — confirmed generated types for `RunOut`/`InsightOut`; confirmed `get_run_result`'s response resolves to `{ [key: string]: unknown }`
- `frontend/src/api/runs.ts`, `frontend/src/hooks/useRuns.ts`, `frontend/src/hooks/useTriggerRun.ts`, `frontend/src/hooks/useOverrides.ts`, `frontend/src/hooks/useScenario.ts`, `frontend/src/hooks/useApplyConstraint.ts` — established hook/wrapper conventions this phase must extend
- `frontend/src/components/runs/RunHistoryTable.tsx`, `RunInFlightPanel.tsx`, `frontend/src/components/layout/ErrorBanner.tsx` — direct reuse targets per D-08/D-12/D-06
- `frontend/src/index.css`, `frontend/src/routes/ScenarioLayout.tsx` — confirmed `#4F46E5` is a literal hex value, not a CSS variable, and confirmed the existing `--chart-1..5`/`--muted-foreground` tokens
- `frontend/components.json` — confirmed shadcn CLI config (`radix-nova` style, `cssVariables: true`) applicable to `npx shadcn add card chart`
- `docs/API.md` — full endpoint/model reference, status code summary
- `npm view recharts version/peerDependencies/time.created/versions/engines` — direct registry facts [VERIFIED: npm registry]
- `gsd-tools query package-legitimacy check --ecosystem npm recharts` — legitimacy seam verdict

### Secondary (MEDIUM confidence)
- Context7 `/recharts/recharts` — grouped `BarChart` code examples, `ResponsiveContainer` v3 breaking-change notes, sourced from the official Recharts GitHub repo's docs/storybook content [CITED]
- `https://ui.shadcn.com/docs/components/chart` (via WebFetch) — `npx shadcn add chart` command, `ChartContainer`/`ChartConfig` example pattern, `min-h-*` requirement note [CITED]

### Tertiary (LOW confidence)
- WebSearch result snippets about the general existence of shadcn's chart registry (corroborated and superseded by the direct WebFetch of the official docs page above; listed only as the discovery step, not relied on for facts)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — recharts version/peer-deps directly verified against npm registry; shadcn chart component pattern directly fetched from official docs
- Architecture: HIGH — every pattern (dependent queries, mutation-as-fetch, scrollable table reuse) is either a direct extension of existing, read code in this repo or a documented, explicit deviation (RunResult typing gap)
- Pitfalls: HIGH — day-indexing and cross-midnight findings are grep-verified against actual backend source, not inferred; recharts v3 breaking-change note is CITED from Context7/official source, not assumed from training data alone

**Research date:** 2026-07-19
**Valid until:** 2026-08-18 (30 days — stable domain: no live external API dependency beyond the npm registry snapshot for `recharts`, which the planner should re-verify with `npm view recharts version` at execution time given its fast 3.x release cadence)
