/**
 * RUN-01's "Run Scenario" primary CTA — see UI-SPEC "Run Scenario button
 * behavior" and Copywriting Contract. Purely presentational (props-only, no
 * hook of its own): the parent (`RunHistory`, plan 03-05) owns `useRuns` /
 * `useTriggerRun` and passes every state down, mirroring the same
 * disabled-logic + spinner + branch-on-error.status shape as
 * `CreateScenarioDialog`'s submit button, but standalone.
 *
 * RUN-03 honesty (T-3-08): renders no cancel/abort control and no
 * determinate-progress affordance (no progress bar, no percentage, no ETA)
 * in any state — the only motion anywhere is the isPending spinner on the
 * button itself.
 */
import { LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getErrorStatus } from "@/lib/errors";

interface TriggerRunButtonProps {
  onTrigger: () => void;
  isLoadingList: boolean;
  runInProgress: boolean;
  isPending: boolean;
  error: unknown;
}

export function TriggerRunButton({
  onTrigger,
  isLoadingList,
  runInProgress,
  isPending,
  error,
}: TriggerRunButtonProps) {
  const disabled = isLoadingList || runInProgress || isPending;
  const errorStatus = error != null ? getErrorStatus(error) : undefined;
  const errorMessage =
    error == null
      ? undefined
      : errorStatus === 404
        ? "This scenario no longer exists."
        : "Couldn't start the run. Try again.";

  return (
    <div className="flex flex-col gap-1.5">
      <Button type="button" disabled={disabled} onClick={onTrigger}>
        {isPending && (
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
        )}
        {isPending ? "Starting…" : "Run Scenario"}
      </Button>
      {runInProgress && !isPending && (
        <p className="text-xs leading-[1.5] text-muted-foreground">
          A run is already in progress for this scenario.
        </p>
      )}
      {errorMessage && (
        <p className="text-xs leading-[1.5] text-destructive">{errorMessage}</p>
      )}
    </div>
  );
}
