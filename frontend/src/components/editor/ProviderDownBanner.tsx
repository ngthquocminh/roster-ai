/**
 * D-04/CONS-05 fixed-copy 503 banner. Structurally disjoint from the
 * rejection render path (`TranscriptEntry`'s `rejected[]` treatment) — it
 * renders on a thrown error BEFORE any 200 body exists, so a provider
 * outage can never be dressed as "your input was wrong" (T-02-14).
 *
 * Deliberately `variant="default"` (NOT `destructive`) — the whole point of
 * this component is to look visibly different from rejection styling, per
 * UI-SPEC's explicit distinction (Copywriting Contract "Provider-down
 * banner (503)"). Mirrors `ErrorBanner`'s persistent-inline-Alert-not-toast
 * philosophy but with fixed, distinct copy and the default variant.
 */
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function ProviderDownBanner() {
  return (
    <Alert
      variant="default"
      data-testid="provider-down-banner"
      className="mx-0 my-2 max-w-3xl"
    >
      <AlertTitle>The constraint parser is unavailable right now.</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        The LLM provider couldn't be reached. Your constraint wasn't lost —
        edit it if needed and try again in a moment.
      </AlertDescription>
    </Alert>
  );
}
