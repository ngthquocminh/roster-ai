/**
 * Fixed tool→label lookup (UI-SPEC Copywriting Contract "Tool Label Map").
 * Used for the legacy-override fallback (`OverridesList`, this plan) and
 * the rejected-item transcript heading (plan 02-05's `TranscriptEntry`).
 *
 * This is a fixed lookup table, NOT a runtime humanization attempt — an
 * unrecognized `tool` value falls back to the raw string itself, never a
 * fabricated label.
 */
export const TOOL_LABELS: Record<string, string> = {
  lock_worker_shift: "Lock worker shift",
  set_min_workers_per_task: "Minimum workers per task",
  exclude_worker_from_task: "Exclude worker from task",
  scale_demand: "Scale demand",
  set_max_hours: "Max hours",
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}
