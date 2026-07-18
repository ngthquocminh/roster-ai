/**
 * Reusable icon+text status cell (RUN-04) — generalizes TranscriptEntry's
 * icon+text convention (Check/X, neutral/destructive text, no Badge) across
 * all four run statuses. `runStatusMeta` (lib/runStatus.ts) is the single
 * source of icon/label/color so this component and RunHistoryTable's
 * FAILED-error color can never drift apart from one status vocabulary.
 *
 * Deliberately not a Badge/pill (UI-SPEC Design System note) — an inline
 * flex row of a lucide icon (size-4, aria-hidden) + a text span, mirroring
 * TranscriptEntry's applied/rejected rows exactly.
 */
import { runStatusMeta } from "@/lib/runStatus";

export function RunStatusLabel({ status }: { status: string }) {
  const { label, Icon, className, spin } = runStatusMeta(status);

  return (
    <div className="flex items-center gap-1.5">
      <Icon
        className={`size-4 shrink-0 ${className}${spin ? " animate-spin" : ""}`}
        aria-hidden="true"
      />
      <span className={`text-sm leading-[1.5] ${className}`}>{label}</span>
    </div>
  );
}
