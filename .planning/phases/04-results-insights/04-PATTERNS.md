# Phase 4: Results & Insights - Pattern Map

**Mapped:** 2026-07-19
**Files analyzed:** 15 (new) + 1 (modified route wiring, if any)
**Analogs found:** 15 / 15

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `frontend/src/api/results.ts` | service (API wrapper) | request-response | `frontend/src/api/runs.ts` | role-match (deviation: hand-written type, see Shared Pattern "RunResult typing gap") |
| `frontend/src/api/insights.ts` | service (API wrapper) | request-response | `frontend/src/api/constraints.ts` | exact (typed via `paths`/`components`, error-throw convention) |
| `frontend/src/api/runs.ts` (ADD `getRun`) | service (API wrapper) | request-response | same file, existing `listRuns`/`triggerRun` | exact |
| `frontend/src/hooks/useRun.ts` | hook | request-response | `frontend/src/hooks/useOverrides.ts` (simpler: no `enabled`) or `useRuns.ts` shape | role-match |
| `frontend/src/hooks/useRunResult.ts` | hook | request-response (dependent query) | `frontend/src/hooks/useOverrides.ts` | exact (same `enabled` gating shape) |
| `frontend/src/hooks/useRunInsights.ts` | hook | request-response (mutation-as-fetch) | `frontend/src/hooks/useTriggerRun.ts` | role-match (no invalidation needed here, simpler) |
| `frontend/src/lib/formatShiftWindow.ts` | utility | transform | `frontend/src/lib/formatTimestamp.ts` | exact (pure deterministic string-format utility, same file-header-comment convention) |
| `frontend/src/components/results/CoverageSummary.tsx` | component | request-response (render) | `frontend/src/components/runs/RunInFlightPanel.tsx` (Alert-based stat/warning display) + new shadcn `Card` | role-match |
| `frontend/src/components/results/WarningsBanner.tsx` | component | request-response (render) | `frontend/src/components/layout/ErrorBanner.tsx` | exact (same `Alert`/`AlertTitle`/`AlertDescription` shape, different variant/copy) |
| `frontend/src/components/results/CoverageByDayTable.tsx` | component | request-response (render) | `frontend/src/components/runs/RunHistoryTable.tsx` | role-match (shadcn `Table` usage, no scroll/click needed) |
| `frontend/src/components/results/DemandVsServedChart.tsx` | component | request-response (render) | none in-repo (first chart in project) — use RESEARCH.md Pattern 2 (shadcn `chart` + Recharts) | no analog |
| `frontend/src/components/results/ScheduleTable.tsx` | component | request-response (render) | `frontend/src/components/runs/RunHistoryTable.tsx` | exact (scrollable container, server-order, TableCell structure) |
| `frontend/src/components/results/InsightPanel.tsx` | component | event-driven (button-triggered mutation) | `frontend/src/components/runs/RunInFlightPanel.tsx` (Alert-based state rendering) combined with mutation state from `useTriggerRun` consumers | role-match |
| `frontend/src/routes/ResultsView.tsx` | route/component | request-response (composition + branching) | `frontend/src/routes/ResultsPlaceholder.tsx` (file being replaced) + `RunHistoryTable`'s FAILED-copy branch | role-match |

## Pattern Assignments

### `frontend/src/api/results.ts` (service, request-response)

**Analog:** `frontend/src/api/runs.ts` (error-throw convention) — but this file MUST deviate from the "types generated, never hand-written" rule because `GET /runs/{run_id}/result` has no FastAPI `response_model` (confirmed `backend/api/routers/runs.py`), so `schema.d.ts` resolves it to `{ [key: string]: unknown }`.

**Imports pattern** (from `runs.ts` lines 1-11):
```typescript
import { client } from "./client";

export async function listRuns(scenarioId: string) {
  const { data, error, response } = await client.GET("/scenarios/{scenario_id}/runs", {
    params: { path: { scenario_id: scenarioId } },
  });
  if (error) {
    // T-1-02: attach the HTTP status so callers can branch on it.
    throw { status: response.status, ...error };
  }
  return data;
}
```

**Deviation required — hand-written type + wrapper** (use RESEARCH.md Code Example 2 verbatim as the base, field-sourced from `backend/services/serialize.py`):
```typescript
// DEVIATION from the codebase's "types generated, never hand-written" convention
// (see api/client.ts header comment): GET /runs/{run_id}/result has no FastAPI
// response_model, so openapi-typescript cannot type it. Hand-authored here
// against backend/services/serialize.py's serialize_result(); keep in sync
// manually if that function's shape changes.
export interface RunResult {
  status: string;
  metrics: {
    total_cost: number | null;
    total_unmet_hours: number | null;
    scheduled_shifts: number;
    scheduled_members: number;
    coverage_by_function: Record<string, { required_h: number | null; served_h: number | null; pct: number | null }>;
    coverage_by_day: Record<string, number | null>;
  };
  stats: { status: string; wall_time_s: number | null; unmet_objective_hours: number | null; cost_objective: number | null };
  schedule: Array<{ contact_id: string; member_name: string; task_id: string; function: string; shift_id: string; start_h: number; end_h: number }>;
  warnings: string[]; // RES-06 — real at runtime, keep even though schema.d.ts is silent on it
}

export async function getRunResult(runId: string): Promise<RunResult> {
  const { data, error, response } = await client.GET("/runs/{run_id}/result", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    throw { status: response.status, ...error };
  }
  return data as RunResult;
}
```

**Error handling pattern:** identical `throw { status: response.status, ...error }` from `runs.ts`/`constraints.ts` — always attach status so callers can distinguish (here: not actually branched-on since `/result` is only fetched once `RunOut.status === "COMPLETED"`, but keep the convention for consistency).

---

### `frontend/src/api/insights.ts` (service, request-response)

**Analog:** `frontend/src/api/constraints.ts` (fully typed via generated `components`/`paths` — `InsightOut` IS in `schema.d.ts`, confirmed by RESEARCH.md, no hand-written type needed here).

**Full pattern to copy** (adapt `constraints.ts` lines 1-17):
```typescript
import { client } from "./client";

export async function getRunInsights(runId: string) {
  const { data, error, response } = await client.GET("/runs/{run_id}/insights", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    // RES-05: 502 must be distinguishable — attach status, same T-1-02 convention.
    throw { status: response.status, ...error };
  }
  return data; // InsightOut: { ready: boolean, report?: string, ... } — branch on `ready`, never on status code
}
```

---

### `frontend/src/api/runs.ts` — ADD `getRun(runId)`

**Analog:** same file's existing `listRuns`/`triggerRun` (lines 13-32 of current file). Add a third export following the identical shape:
```typescript
export async function getRun(runId: string) {
  const { data, error, response } = await client.GET("/runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    throw { status: response.status, ...error };
  }
  return data; // RunOut — always succeeds regardless of run status (D-12)
}
```

---

### `frontend/src/hooks/useRun.ts` (hook, request-response)

**Analog:** `frontend/src/hooks/useOverrides.ts` structure, simplified (no `enabled` gate needed — this is the first, ungated fetch in the chain).
```typescript
import { useQuery } from "@tanstack/react-query";
import { getRun } from "@/api/runs";

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });
}
```

---

### `frontend/src/hooks/useRunResult.ts` (hook, dependent query)

**Analog:** `frontend/src/hooks/useOverrides.ts` (exact `enabled` gating shape).

**Core pattern** (from `useOverrides.ts` lines 15-21):
```typescript
import { useQuery } from "@tanstack/react-query";
import { getRunResult } from "@/api/results";

export function useRunResult(runId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["run", runId, "result"],
    queryFn: () => getRunResult(runId),
    enabled: options.enabled, // caller passes: runQuery.data?.status === "COMPLETED"
  });
}
```
**Note:** Query key `["run", runId, "result"]` is a prefix-extension of `useRun.ts`'s `["run", runId]` key — intentional TanStack Query key hierarchy convention (mirrors `["scenario", scenarioId]` / `["scenario", scenarioId, "overrides"]` in `useScenario.ts`/`useOverrides.ts`).

---

### `frontend/src/hooks/useRunInsights.ts` (hook, mutation-as-fetch)

**Analog:** `frontend/src/hooks/useTriggerRun.ts`, but WITHOUT the `onSuccess` invalidation (no other query depends on insight-fetch completing — RES-05 requires isolation, not cache coordination).

**Core pattern** (adapted from `useTriggerRun.ts` lines 20-27, dropping `queryClient`/`onSuccess`):
```typescript
import { useMutation } from "@tanstack/react-query";
import { getRunInsights } from "@/api/insights";

export function useRunInsights(runId: string) {
  return useMutation({
    mutationFn: () => getRunInsights(runId),
  });
}
```
**Why `useMutation` not `useQuery`:** D-11 (button-triggered) + D-13 (retry) — `useMutation` gives `isPending`/`isError`/`error`/`mutate()` retry semantics for free, matching how `useTriggerRun` already models a user-triggered network call in this codebase.

---

### `frontend/src/lib/formatShiftWindow.ts` (utility, transform)

**Analog:** `frontend/src/lib/formatTimestamp.ts` — same "deterministic, pure string-format utility with defensive fallback, explanatory header comment justifying the non-obvious implementation choice" pattern.

**Structural pattern to copy** (from `formatTimestamp.ts`): top-of-file comment explaining *why* the deterministic approach is required (there: avoiding `toLocaleString`'s host-timezone dependence in jsdom tests; here: avoiding independent hour/minute rounding causing a "24:00" boundary bug — see RESEARCH.md Pitfall 3). Use RESEARCH.md's Code Example 1 verbatim as the implementation:
```typescript
function formatDayTime(h: number): { day: number; hhmm: string } {
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
  return `Day ${start.day}, ${start.hhmm} – Day ${end.day}, ${end.hhmm}`;
}
```

---

### `frontend/src/components/results/WarningsBanner.tsx` (component, render)

**Analog:** `frontend/src/components/layout/ErrorBanner.tsx` — exact structural match, different content/variant.

**Full pattern to copy** (adapt `ErrorBanner.tsx` lines 1-33):
```tsx
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

// D-06: warning-styled variant of ErrorBanner's pattern — renders the
// solver's own degenerate-solve strings verbatim (plain JSX text, no
// dangerouslySetInnerHTML), positioned above the stat row so the user reads
// the caveat before the numbers it qualifies.
export function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <Alert variant="default" className="mx-0 my-2 max-w-3xl border-yellow-500/40">
      <AlertTitle>Coverage caveat</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        {warnings.map((w) => (
          <p key={w}>{w}</p>
        ))}
      </AlertDescription>
    </Alert>
  );
}
```
**Deviation from `ErrorBanner`:** `ErrorBanner` deliberately renders *fixed* copy regardless of error content (ASVS V7 rationale in its header comment — backend internals must never reach JSX). `WarningsBanner` is the opposite case: `SolveResult.warnings` strings are already display-ready, solver-generated (not user input, not backend internals) — rendering them verbatim as plain JSX text is correct and matches RESEARCH.md's Security Domain guidance (plain-text rendering only, no `dangerouslySetInnerHTML`).

---

### `frontend/src/components/results/CoverageSummary.tsx` (component, render)

**Analog:** No exact prior stat-card component exists (`Card` primitive is net-new this phase per RESEARCH.md Standard Stack). Follow `RunInFlightPanel.tsx`'s pattern of "plain presentational component, receives already-fetched data as props, never fetches itself," and use shadcn `Card`/`CardHeader`/`CardContent` (added via `npx shadcn add card`).

**Null-handling pattern (D-07, Pitfall 5)** — critical, not covered by any existing analog since no nullable-metric rendering exists elsewhere in the codebase yet:
```tsx
function CostStat({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <span title="The solver hit its time limit before optimizing cost.">
        Not computed
      </span>
    );
  }
  return <>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value)}</>;
}
```
**Do not** use `value ?? 0` (renders misleading "$0.00") or a bare em dash (hides the honest "not computed" fact) — this is RES-01/D-07's explicit rule, tracing back to the same never-hide-solver-limitations principle as `RunInFlightPanel.tsx`'s honest-wait copy.

---

### `frontend/src/components/results/CoverageByDayTable.tsx` (component, render)

**Analog:** `frontend/src/components/runs/RunHistoryTable.tsx` — reuse its `Table`/`TableHeader`/`TableBody`/`TableRow`/`TableCell` composition (lines ~108-152), but drop the scroll container, row-click navigation, and loading/error/empty state machine (this table renders synchronously from already-loaded `RunResult.metrics.coverage_by_day`, no independent query).

**Day-indexing pattern (Pitfall 2 — MUST match `ScheduleTable`'s convention):**
```tsx
// coverage_by_day keys are 0-indexed ("0".."6"); render 1-indexed to match
// formatShiftWindow's "Day N" convention used in the schedule table below —
// the same calendar day must show the same label in both tables.
{Object.entries(coverageByDay).map(([dayKey, unmetHours]) => (
  <TableRow key={dayKey}>
    <TableCell>{`Day ${Number(dayKey) + 1}`}</TableCell>
    <TableCell>{unmetHours == null ? "Not computed" : unmetHours}</TableCell>
  </TableRow>
))}
```

---

### `frontend/src/components/results/DemandVsServedChart.tsx` (component, render)

**No analog in-repo** — first chart in the project. Use RESEARCH.md Pattern 2 verbatim (shadcn `ChartContainer`/`ChartTooltip`/`ChartConfig` + Recharts `BarChart`). Key excerpt:
```tsx
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";

const chartConfig = {
  required_h: { label: "Required", color: "var(--muted-foreground)" },
  served_h: { label: "Served", color: "#4F46E5" }, // literal hex, matches ScenarioLayout.tsx's existing usage
} satisfies ChartConfig;

export function DemandVsServedChart({ data }: { data: Array<{ function: string; required_h: number; served_h: number }> }) {
  return (
    <ChartContainer config={chartConfig} className="min-h-[280px] w-full">
      <BarChart data={data}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="function" />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="required_h" fill="none" stroke="var(--color-required_h)" strokeWidth={2} />
        <Bar dataKey="served_h" fill="var(--color-served_h)" />
      </BarChart>
    </ChartContainer>
  );
}
```
**Pitfall guard:** `ChartContainer` MUST carry an explicit `min-h-*` class or Recharts' `ResponsiveContainer` renders nothing on first paint.

---

### `frontend/src/components/results/ScheduleTable.tsx` (component, render)

**Analog:** `frontend/src/components/runs/RunHistoryTable.tsx` — exact structural match for D-08/D-09.

**Scrollable container pattern to copy verbatim** (line 108):
```tsx
<div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
  <Table className="table-fixed">
    {/* ... */}
  </Table>
</div>
```
No loading/error state machine needed (parent `ResultsView` already gates rendering on `useRunResult` success); no row-click navigation (unlike `RunHistoryTable`, rows here are terminal, not links). Shift window column uses `formatShiftWindow(row.start_h, row.end_h)`.

**"Server order only" comment convention** to replicate (from `RunHistoryTable.tsx`'s own header comment / D-09): add an explicit file-header note stating no client re-sort is performed, matching the project's established precedent of stating this rule in prose, not just in code.

---

### `frontend/src/components/results/InsightPanel.tsx` (component, event-driven)

**Analog:** `frontend/src/components/runs/RunInFlightPanel.tsx` for the `Alert`-based state-rendering shape; mutation-state branching modeled directly on `useRunInsights` (`useTriggerRun`-derived) hook's `isPending`/`isError`/`isSuccess`/`data`/`error`.

**State-branch pattern** (RES-04/RES-05/D-13 — new, no direct render analog for mutation-driven UI in-repo, compose from `RunInFlightPanel`'s Alert usage + `ErrorBanner`'s distinct-error-styling precedent):
```tsx
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useRunInsights } from "@/hooks/useRunInsights";

export function InsightPanel({ runId }: { runId: string }) {
  const insights = useRunInsights(runId);

  if (insights.isIdle) {
    return <Button onClick={() => insights.mutate()}>Generate insight report</Button>;
  }
  if (insights.isPending) {
    return <Button disabled>Generating…</Button>;
  }
  if (insights.isError) {
    // D-13: distinct visual treatment from loading/ready states (Phase 2 D-04 precedent).
    return (
      <Alert variant="default" className="border-destructive/40">
        <AlertTitle>Couldn't generate the insight report.</AlertTitle>
        <AlertDescription>
          Try again — the schedule and coverage above are unaffected.
        </AlertDescription>
      </Alert>
      // + retry Button calling insights.mutate() again
    );
  }
  // isSuccess: branch on data.ready, NEVER on HTTP status (RES-04 hard rule)
  if (insights.data && !insights.data.ready) {
    return <p>Insight not ready yet.</p>; // should not normally happen — button only enabled when COMPLETED
  }
  return <p>{insights.data?.report}</p>; // plain JSX text child only — LLM-sourced string, no dangerouslySetInnerHTML
}
```

---

### `frontend/src/routes/ResultsView.tsx` (route, composition + branching)

**Analog:** `frontend/src/routes/ResultsPlaceholder.tsx` (file being replaced — trivial, just shows the mount point) + `RunHistoryTable.tsx`'s FAILED-branch copy (`FAILED_NO_ERROR_COPY` constant, lines 47/136-141) for D-12's FAILED state.

**Composition/branch pattern** (D-12, from RESEARCH.md's Pattern 1 + System Architecture Diagram):
```tsx
import { useParams } from "react-router";
import { useRun } from "@/hooks/useRun";
import { useRunResult } from "@/hooks/useRunResult";
import { RunInFlightPanel } from "@/components/runs/RunInFlightPanel";

const FAILED_NO_ERROR_COPY = "Failed — no error details were recorded."; // reuse RunHistoryTable's exact string

export function ResultsView() {
  const { runId } = useParams();
  const runQuery = useRun(runId!);
  const resultQuery = useRunResult(runId!, { enabled: runQuery.data?.status === "COMPLETED" });

  if (runQuery.isLoading) return null; // or a loading spinner, matching RunHistoryTable's LoaderCircle pattern
  if (runQuery.data?.status === "PENDING" || runQuery.data?.status === "RUNNING") {
    return <RunInFlightPanel run={runQuery.data} />;
  }
  if (runQuery.data?.status === "FAILED") {
    return <p className="text-destructive">{runQuery.data.error || FAILED_NO_ERROR_COPY}</p>;
  }
  // COMPLETED: render CoverageSummary + WarningsBanner + DemandVsServedChart +
  // CoverageByDayTable + ScheduleTable + InsightPanel, all fed by resultQuery.data
}
```

## Shared Patterns

### Typed API wrapper + error-throw convention
**Source:** `frontend/src/api/runs.ts`, `frontend/src/api/constraints.ts`
**Apply to:** `results.ts`, `insights.ts`, `runs.ts`'s new `getRun`
```typescript
if (error) {
  throw { status: response.status, ...error }; // T-1-02 convention — every wrapper attaches HTTP status
}
```

### Dependent query via `enabled`
**Source:** `frontend/src/hooks/useOverrides.ts`
**Apply to:** `useRunResult.ts` (gated on `useRun`'s `status === "COMPLETED"`)
```typescript
export function useOverrides(scenarioId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "overrides"],
    queryFn: () => getScenarioOverrides(scenarioId),
    enabled: options.enabled,
  });
}
```

### Mutation-as-fetch for user-triggered reads
**Source:** `frontend/src/hooks/useTriggerRun.ts`
**Apply to:** `useRunInsights.ts` (button-triggered `GET`, D-11/D-13's retry semantics)

### Plain-JSX-text-only rendering (no `dangerouslySetInnerHTML`)
**Source:** `frontend/src/components/runs/RunHistoryTable.tsx` header comment, `frontend/src/components/layout/ErrorBanner.tsx`
**Apply to:** `WarningsBanner.tsx` (solver warnings), `InsightPanel.tsx` (LLM report text), `ScheduleTable.tsx` (member_name/function/task_id cells) — React's default text-node escaping is the established, sufficient mitigation project-wide.

### RunResult typing gap (hand-written type deviation)
**Source:** RESEARCH.md Pitfall 1 + Code Example 2; precedent for "documented single-point deviation" is `formatTimestamp.ts`'s regex-not-`toLocaleString` header comment.
**Apply to:** `results.ts` only — single point of `as RunResult` casting, never repeated per-component.

### Scrollable table container
**Source:** `frontend/src/components/runs/RunHistoryTable.tsx` line 108: `max-h-[420px] overflow-y-auto rounded-md border border-border`
**Apply to:** `ScheduleTable.tsx` (D-08)

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `frontend/src/components/results/DemandVsServedChart.tsx` | component | request-response | First chart in the project — no prior Recharts/charting usage exists anywhere in `frontend/src/`. Use RESEARCH.md Pattern 2 (shadcn `chart` + Recharts `BarChart`) as the canonical source instead of an in-repo analog. |
| `frontend/src/components/results/InsightPanel.tsx` | component | event-driven | No prior component in the codebase branches render state off a `useMutation`'s `isIdle`/`isPending`/`isError`/`isSuccess` lifecycle with a manual retry button — closest available pieces (`RunInFlightPanel`'s Alert shape, `ErrorBanner`'s distinct-error-styling precedent) are composed rather than a single analog copied. |

## Metadata

**Analog search scope:** `frontend/src/api/`, `frontend/src/hooks/`, `frontend/src/components/runs/`, `frontend/src/components/layout/`, `frontend/src/lib/`, `frontend/src/routes/`
**Files scanned:** `api/runs.ts`, `api/constraints.ts`, `hooks/useRuns.ts`, `hooks/useOverrides.ts`, `hooks/useTriggerRun.ts`, `components/runs/RunHistoryTable.tsx`, `components/runs/RunInFlightPanel.tsx`, `components/layout/ErrorBanner.tsx`, `lib/formatTimestamp.ts`, `routes/ResultsPlaceholder.tsx`
**Pattern extraction date:** 2026-07-19
