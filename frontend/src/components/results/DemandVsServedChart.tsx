/**
 * Demand-vs-served grouped bar chart (RES-02, D-02, D-03) — the first chart
 * in this project. One grouped pair per function from
 * `RunResult.metrics.coverage_by_function`: required renders as an
 * outline-only bar (`fill="none"`, `stroke` = `var(--muted-foreground)`),
 * served renders as a solid brand-indigo fill (`#4F46E5` — a literal hex,
 * matching `ScenarioLayout.tsx`'s existing active-tab usage; this app has no
 * `--primary` CSS variable for it). Composed through the shadcn
 * `ChartContainer`/`ChartTooltip`/`ChartTooltipContent` primitives (04-01)
 * so brand color and tooltip styling stay consistent with the rest of the
 * app's theming approach (RESEARCH.md Pattern 2).
 *
 * `ChartContainer` carries an explicit `min-h-[280px] w-full` — Recharts'
 * `ResponsiveContainer` renders nothing until it can measure a non-zero
 * parent height on first paint (RESEARCH.md Pitfall 4).
 *
 * This is the by-function coverage view; the by-day breakdown table (plan
 * 04-04) owns by-day. No number appears in both (D-02/D-05).
 *
 * Both the chart and the schedule table (`ScheduleTable.tsx`) render only
 * data-sourced plain JSX text children — no `dangerouslySetInnerHTML`
 * anywhere in this file.
 */
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type { CoverageStat } from "@/api/results";

export interface DemandVsServedDatum {
  function: string;
  required_h: number | null;
  served_h: number | null;
}

/**
 * Pure data transform (unit-testable independent of Recharts' DOM):
 * `coverage_by_function` -> one chart datum per function, preserving
 * function keys and passing `required_h`/`served_h` through verbatim,
 * including `null` (D-07/Pitfall 5 — `null` means "not computed", never
 * silently coerced to `0` here).
 */
export function toChartData(
  coverageByFunction: Record<string, CoverageStat>,
): DemandVsServedDatum[] {
  return Object.entries(coverageByFunction).map(([fn, stat]) => ({
    function: fn,
    required_h: stat.required_h,
    served_h: stat.served_h,
  }));
}

const chartConfig = {
  required_h: { label: "Required", color: "var(--muted-foreground)" },
  served_h: { label: "Served", color: "#4F46E5" },
} satisfies ChartConfig;

const NOT_COMPUTED = "Not computed";

type BarKey = "required_h" | "served_h";

function isBarKey(name: unknown): name is BarKey {
  return name === "required_h" || name === "served_h";
}

export function DemandVsServedChart({
  coverage_by_function,
}: {
  coverage_by_function: Record<string, CoverageStat>;
}) {
  const data = toChartData(coverage_by_function);
  // Recharts requires a number to compute bar height — a `null` value
  // renders as a zero-height bar here, but the original `null` survives on
  // the row (`*_raw`) so the tooltip formatter below can still render "Not
  // computed" instead of a misleading "0h" line (UI-SPEC "Chart tooltip (a
  // value is null)").
  const chartData = data.map((d) => ({
    function: d.function,
    required_h: d.required_h ?? 0,
    served_h: d.served_h ?? 0,
    required_h_raw: d.required_h,
    served_h_raw: d.served_h,
  }));

  return (
    <ChartContainer config={chartConfig} className="min-h-[280px] w-full">
      <BarChart data={chartData}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="function" />
        <YAxis
          label={{ value: "Hours", angle: -90, position: "insideLeft" }}
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              formatter={(value, name, item) => {
                const key = isBarKey(name) ? name : undefined;
                const label = key ? chartConfig[key].label : name;
                const rawValue = key
                  ? (item.payload as { required_h_raw: number | null; served_h_raw: number | null })[
                      `${key}_raw`
                    ]
                  : (value as number);
                return (
                  <div className="flex w-full flex-1 items-center justify-between gap-2 leading-none">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {rawValue == null ? NOT_COMPUTED : `${rawValue}h`}
                    </span>
                  </div>
                );
              }}
            />
          }
        />
        {/* D-03: required rendered as outline-only (no fill), served as solid fill */}
        <Bar
          dataKey="required_h"
          fill="none"
          stroke="var(--color-required_h)"
          strokeWidth={2}
        />
        <Bar dataKey="served_h" fill="var(--color-served_h)" />
      </BarChart>
    </ChartContainer>
  );
}
