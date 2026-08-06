import type { ReactNode } from "react";

import { EmptyState } from "@/components/primitives/EmptyState";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TERMINAL_STATUSES, USER_ERROR_COPY } from "@/lib/errors";

type Props = Readonly<{
  isPending: boolean;
  isError: boolean;
  errorStatus?: number;
  isEmpty: boolean;
  onRetry: () => void;
  columnCount: number;
  children: ReactNode;
}>;

export function ScenarioDataGroupState({
  children,
  columnCount,
  errorStatus,
  isEmpty,
  isError,
  isPending,
  onRetry,
}: Props) {
  if (isPending) {
    return (
      <div aria-label="Loading scenario data" className="space-y-2" role="status">
        {[0, 1, 2].map((row) => (
          <div className="flex gap-2" key={row}>
            {Array.from({ length: columnCount }, (_, column) => (
              <Skeleton className="h-10 min-w-24 flex-1" key={column} />
            ))}
          </div>
        ))}
      </div>
    );
  }
  if (isError) {
    // Terminal statuses (scenario missing or the id itself malformed) can
    // never succeed on retry — mirrors ScenarioWorkspace's classification
    // one route level up, so a group failing independently of the parent
    // context query still gets a truthful, non-retryable explanation.
    const isTerminal = errorStatus !== undefined && TERMINAL_STATUSES.has(errorStatus);
    return (
      <InlineAlert
        action={
          isTerminal ? undefined : (
            <Button className="min-h-11" onClick={onRetry} type="button" variant="outline">
              Retry
            </Button>
          )
        }
        description={
          isTerminal
            ? "The requested scenario is not available."
            : USER_ERROR_COPY.connection.description
        }
        title={isTerminal ? "Scenario not found" : USER_ERROR_COPY.connection.title}
        variant="destructive"
      />
    );
  }
  if (isEmpty) return <EmptyState explanation="This fixture has no records in this group." />;
  return children;
}
