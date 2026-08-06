import { forwardRef, type ComponentPropsWithoutRef } from "react";

import { cn } from "@/lib/utils";

export const EvidenceHighlight = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<"div">
>(function EvidenceHighlight({ className, tabIndex = -1, ...props }, ref) {
  return (
    <div
      className={cn(
        "rounded-evidence border border-evidence-border bg-evidence-surface p-evidence-inset text-evidence-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
      ref={ref}
      tabIndex={tabIndex}
      {...props}
    />
  );
});
