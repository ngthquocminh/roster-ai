import type { ReactNode } from "react";

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { cn } from "@/lib/utils";

type InlineAlertProps = Readonly<{
  title: string;
  description?: string;
  action?: ReactNode;
  variant?: "default" | "destructive";
  className?: string;
  descriptionId?: string;
  live?: "polite";
}>;

export function InlineAlert({
  action,
  className,
  description,
  descriptionId,
  live,
  title,
  variant = "default",
}: InlineAlertProps) {
  return (
    <Alert
      {...(live === "polite"
        ? { "aria-atomic": true, "aria-live": "polite" as const, role: "status" }
        : {})}
      className={cn(variant === "destructive" && "border-destructive/40", className)}
      variant={variant}
    >
      <AlertTitle>{title}</AlertTitle>
      {description || action ? (
        <AlertDescription id={descriptionId}>
          {description ? <p>{description}</p> : null}
          {action ? <div className="mt-3">{action}</div> : null}
        </AlertDescription>
      ) : null}
    </Alert>
  );
}
