import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Persistent inline banner (SHELL-04) — deliberately NOT a toast. A toast
 * auto-dismisses; a dismissed message about a backend that is still down is
 * a silent failure wearing a notification's clothes.
 *
 * Renders fixed literal copy from UI-SPEC's Copywriting Contract regardless
 * of the passed error's contents. This is the counter-intuitive part, and
 * it is deliberate (T-1-02, ASVS V7):
 *   - `fetch` cannot distinguish a CORS-blocked request from a backend that
 *     is simply not running; both throw a generic `TypeError: Failed to
 *     fetch` with no further detail. Browsers deliberately withhold the
 *     distinction from JS. Any branch inspecting the error text for a CORS
 *     substring would be fabricated confidence dressed as helpfulness — the
 *     fixed copy's non-diagnostic vagueness is the honest answer here, not
 *     a gap to close.
 *   - The error may carry backend internals (a stack trace, a file path, an
 *     exception class name). None of that reaches JSX. `error` is accepted
 *     as a prop only so callers share a uniform signature and so it can be
 *     logged to the console — never as render input.
 */
export function ErrorBanner({ error }: { error: unknown }) {
  // eslint-disable-next-line no-console
  console.error(error);

  return (
    <Alert className="mx-6 my-4 max-w-3xl border-destructive/40">
      <AlertTitle>Can't reach the ShiftMind API.</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        Make sure the backend is running (
        <code>uv run uvicorn api.main:app --reload</code> in{" "}
        <code>backend/</code>) and reload.
      </AlertDescription>
    </Alert>
  );
}
