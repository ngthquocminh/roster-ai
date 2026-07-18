/**
 * RUN-03's honest in-flight wait panel — UI-SPEC Application Structure item
 * 2 / E3. Mirrors `ProviderDownBanner`'s persistent-inline `Alert`
 * (`variant="default"`) structural pattern, but purely presentational: the
 * parent (`RunHistory`, plan 03-05) derives the single newest non-terminal
 * run from its one `useRuns` response (via `newestActiveRun` in
 * `lib/runStatus.ts`) and passes it down — this component never fetches.
 *
 * Renders nothing (not even empty chrome) when `run` is null or already
 * terminal — the defensive terminal guard should never fire from a correct
 * parent, but keeps this component honest on its own if it ever does.
 *
 * T-3-08 honesty: text only. No cancel/abort control, no progress bar,
 * percentage, or ETA — the only motion anywhere in this feature is the
 * indeterminate RUNNING spinner on the status icon (`lib/runStatus.ts`'s
 * table row treatment), not here.
 */
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { isTerminalStatus } from "@/lib/runStatus";
import type { components } from "@/api/schema";

type RunOut = components["schemas"]["RunOut"];

interface RunInFlightPanelProps {
  run: RunOut | null;
}

const COPY: Record<string, { title: string; body: string }> = {
  PENDING: {
    title: "Queued",
    body: "Waiting for the solver to pick this up — it's next in line.",
  },
  RUNNING: {
    title: "Solving…",
    body: "This can take a few minutes: round 1 finds a feasible schedule quickly, then round 2 spends the rest of the time tuning cost. It can't be cancelled once started — let it finish.",
  },
};

export function RunInFlightPanel({ run }: RunInFlightPanelProps) {
  if (run == null || isTerminalStatus(run.status)) {
    return null;
  }

  const copy = COPY[run.status];
  if (!copy) {
    return null;
  }

  return (
    <Alert
      variant="default"
      data-testid="run-in-flight-panel"
      className="mx-0 my-2 max-w-3xl"
    >
      <AlertTitle>{copy.title}</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        {copy.body}
      </AlertDescription>
    </Alert>
  );
}
