import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { USER_ERROR_COPY } from "@/lib/errors";

/**
 * Persistent inline banner (SHELL-04) — deliberately NOT a toast. A toast
 * auto-dismisses; a dismissed message about a backend that is still down is
 * a silent failure wearing a notification's clothes.
 *
 * Renders shared fixed copy regardless of the passed error's contents. The
 * error may carry backend commands, file paths, stack traces, or exception
 * class names. It is retained solely for console diagnostics and never used
 * as render input (T-1-02, ASVS V7).
 */
export function ErrorBanner({ error }: { error: unknown }) {
  // eslint-disable-next-line no-console
  console.error(error);

  return (
    <Alert className="mx-6 my-4 max-w-3xl border-destructive/40">
      <AlertTitle>{USER_ERROR_COPY.connection.title}</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        {USER_ERROR_COPY.connection.description}
      </AlertDescription>
    </Alert>
  );
}
