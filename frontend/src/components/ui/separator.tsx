import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * A real separator, not a decorative rule.
 *
 * The Draft card uses this to make revise structurally discontinuous from
 * reject (UX-DR35), and `EXPERIENCE.md` makes automated coverage the only
 * accepted proof of that. An `aria-hidden` div carries no such semantics, so
 * the discontinuity existed only visually. `role="separator"` with an explicit
 * orientation is what an assistive technology can actually report.
 */
function Separator({
  className,
  orientation = "horizontal",
  ...props
}: React.ComponentProps<"div"> & { orientation?: "horizontal" | "vertical" }) {
  return (
    <div
      aria-orientation={orientation}
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      data-slot="separator"
      role="separator"
      {...props}
    />
  );
}

export { Separator };
