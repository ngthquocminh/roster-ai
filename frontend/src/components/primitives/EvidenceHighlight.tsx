import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { cn } from "@/lib/utils";

// Exported so cross-context consumers that can't render the component (e.g. the Playwright
// reduced-motion spec, which checks computed style in a real browser rather than jsdom) can read
// the real class list instead of hand-copying it and silently drifting out of sync.
export const EVIDENCE_HIGHLIGHT_CLASS =
  "rounded-evidence border border-evidence-border bg-evidence-surface p-evidence-inset text-evidence-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

export const EvidenceHighlight = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<"div">
>(function EvidenceHighlight({ className, tabIndex = -1, ...props }, ref) {
  return (
    <div
      className={cn(EVIDENCE_HIGHLIGHT_CLASS, className)}
      ref={ref}
      tabIndex={tabIndex}
      {...props}
    />
  );
});
