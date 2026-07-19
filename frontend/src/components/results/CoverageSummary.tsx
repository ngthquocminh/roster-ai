/**
 * D-04/D-07/RES-01 — the page's Display-type focal point: two Cards side by
 * side ("Total Cost", "Total Unmet Hours"). Purely presentational — receives
 * already-fetched RunResult metrics fields as props, never fetches itself
 * (same "props in, render out" precedent as RunInFlightPanel.tsx).
 *
 * Each card guards its own nullability independently (RESEARCH.md Pitfall 5
 * partial case): one card can read "Not computed" while its sibling shows a
 * real number. A null metric NEVER renders as `value ?? 0` ("$0.00", a
 * misleading real-looking zero) or a bare em dash (that convention is
 * reserved for "field never applicable" elsewhere in this app) — it renders
 * the literal "Not computed" plus a Tooltip explaining the solver hit its
 * time limit. This is this project's never-hide-solver-limitations
 * principle, the same honesty rule as RunInFlightPanel's wait copy.
 */
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

const NOT_COMPUTED_TOOLTIP =
  "The solver reached its time limit before finishing this calculation.";

function NullableStat({ value }: { value: React.ReactNode | null }) {
  if (value == null) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-default text-[28px] leading-[1.2] font-semibold">
            Not computed
          </span>
        </TooltipTrigger>
        <TooltipContent>{NOT_COMPUTED_TOOLTIP}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <span className="text-[28px] leading-[1.2] font-semibold">{value}</span>
  );
}

function CostStat({ value }: { value: number | null }) {
  const formatted =
    value == null
      ? null
      : new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
        }).format(value);
  return <NullableStat value={formatted} />;
}

function UnmetHoursStat({ value }: { value: number | null }) {
  const formatted = value == null ? null : `${value.toFixed(1)} h`;
  return <NullableStat value={formatted} />;
}

export function CoverageSummary({
  total_cost,
  total_unmet_hours,
}: {
  total_cost: number | null;
  total_unmet_hours: number | null;
}) {
  return (
    <TooltipProvider>
      <div className="grid grid-cols-2 gap-8">
        <Card>
          <CardHeader>
            <span className="text-xs leading-[1.2] text-muted-foreground">
              Total Cost
            </span>
          </CardHeader>
          <CardContent>
            <CostStat value={total_cost} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <span className="text-xs leading-[1.2] text-muted-foreground">
              Total Unmet Hours
            </span>
          </CardHeader>
          <CardContent>
            <UnmetHoursStat value={total_unmet_hours} />
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
