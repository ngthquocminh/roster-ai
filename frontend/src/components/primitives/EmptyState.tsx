import type { ReactNode } from "react";

type EmptyStateProps = Readonly<{
  explanation: string;
  action?: ReactNode;
}>;

export function EmptyState({ action, explanation }: EmptyStateProps) {
  return (
    <div className="text-sm text-muted-foreground">
      <p>{explanation}</p>
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
