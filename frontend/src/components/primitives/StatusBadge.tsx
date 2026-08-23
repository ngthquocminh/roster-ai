import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

type StatusBadgeProps = Readonly<{
  status: string;
  icon?: ReactNode;
  className?: string;
}>;

export function StatusBadge({ className, icon, status }: StatusBadgeProps) {
  return (
    <Badge aria-label={status} className={className} variant="secondary">
      {icon}
      <span>{status}</span>
    </Badge>
  );
}
