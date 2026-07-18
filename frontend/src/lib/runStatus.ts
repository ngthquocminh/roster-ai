/**
 * Single source of run-status vocabulary (label + icon + color) AND the
 * terminal/active predicates that drive both polling (RUN-02/RUN-03) and
 * rendering (RUN-04) — see UI-SPEC's Color section status icon/color
 * mapping table. Kept pure (no React/JSX) so hooks, table, panel, and
 * button all import the same truth and can never drift apart.
 *
 * `RUN_STATUS_META` is a fixed lookup table, NOT a runtime humanization
 * attempt — an unrecognized status falls back to the raw string as its
 * label, mirroring toolLabels.ts's fallback discipline.
 */
import { Clock, LoaderCircle, Check, X, type LucideIcon } from "lucide-react";
import type { components } from "@/api/schema";

type RunOut = components["schemas"]["RunOut"];

export interface RunStatusMeta {
  label: string;
  Icon: LucideIcon;
  className: string;
  spin?: boolean;
}

export const RUN_STATUS_META: Record<string, RunStatusMeta> = {
  PENDING: { label: "Queued", Icon: Clock, className: "text-muted-foreground" },
  RUNNING: {
    label: "Running",
    Icon: LoaderCircle,
    className: "text-muted-foreground",
    spin: true,
  },
  COMPLETED: { label: "Completed", Icon: Check, className: "text-foreground" },
  FAILED: { label: "Failed", Icon: X, className: "text-destructive" },
};

export function runStatusMeta(status: string): RunStatusMeta {
  return (
    RUN_STATUS_META[status] ?? { label: status, Icon: Clock, className: "text-muted-foreground" }
  );
}

export function isTerminalStatus(status: string): boolean {
  return status === "COMPLETED" || status === "FAILED";
}

export function hasActiveRun(runs: RunOut[]): boolean {
  return runs.some((r) => !isTerminalStatus(r.status));
}

export function newestActiveRun(runs: RunOut[]): RunOut | null {
  return runs.find((r) => !isTerminalStatus(r.status)) ?? null;
}
