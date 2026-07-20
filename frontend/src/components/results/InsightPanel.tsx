/**
 * RES-04/RES-05's on-demand insight panel (D-11, D-13) — UI-SPEC section 6 /
 * E7. Button-triggered `useRunInsights` mutation rendering exactly one of
 * five states: idle, pending ("Generating…"), error (502, distinct
 * destructive styling + "Try Again"), not-ready (`ready:false`, a normal
 * 200 body — NEVER treated as an error), and ready (`ready:true`, the LLM
 * report rendered as plain JSX text, `whitespace-pre-wrap`).
 *
 * Analog: `RunInFlightPanel.tsx`'s Alert-based state-rendering shape,
 * combined with `ErrorBanner.tsx`'s distinct-error-styling precedent for the
 * 502 block. Unlike `ErrorBanner`, the 502 copy here is paired with a
 * re-enabled retry button (D-13) rather than being a dead-end banner.
 *
 * RES-04 hard rule: the ready/not-ready branch reads `data.ready` from the
 * response body — never `response.status` or any HTTP status code. RES-05
 * hard rule: this component only touches `useRunInsights`'s own isolated
 * mutation state; it never reads or writes any other query, so a 502 here
 * re-renders only this section.
 */
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useRunInsights } from "@/hooks/useRunInsights";

const HEADING = "Insight Report";

export function InsightPanel({ runId }: { runId: string }) {
  const insights = useRunInsights(runId);

  return (
    <section className="rounded-lg border p-4">
      <h2 className="text-lg font-semibold">{HEADING}</h2>

      {insights.isIdle && (
        <>
          <p className="mt-1 text-sm text-muted-foreground">
            Get a plain-language summary of this run&apos;s cost, coverage,
            and any tradeoffs the solver made.
          </p>
          <Button className="mt-2" onClick={() => insights.mutate()}>
            Get Insight Report
          </Button>
        </>
      )}

      {insights.isPending && (
        <Button className="mt-2" disabled>
          Generating…
        </Button>
      )}

      {insights.isError && (
        <>
          <Alert variant="default" className="mt-2 border-destructive/40">
            <AlertTitle>
              Couldn&apos;t generate an insight report right now.
            </AlertTitle>
            <AlertDescription className="whitespace-normal break-words">
              The LLM provider may be unavailable.
            </AlertDescription>
          </Alert>
          <Button
            className="mt-2"
            variant="outline"
            onClick={() => insights.mutate()}
          >
            Try Again
          </Button>
        </>
      )}

      {insights.isSuccess && insights.data?.ready === false && (
        <p className="mt-1 text-sm text-muted-foreground">
          Not ready yet — try again in a moment.
        </p>
      )}

      {insights.isSuccess && insights.data?.ready === true && (
        <p className="mt-1 text-sm whitespace-pre-wrap break-words">
          {insights.data.report}
        </p>
      )}
    </section>
  );
}
