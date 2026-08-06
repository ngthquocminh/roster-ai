import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";

type StatusBadgeProps = Readonly<{
  status: string;
  icon?: ReactNode;
}>;

export function StatusBadge({ icon, status }: StatusBadgeProps) {
  return (
    <Badge aria-label={status} variant="secondary">
      {icon}
      <span>{status}</span>
    </Badge>
  );
}
