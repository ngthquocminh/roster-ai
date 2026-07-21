import { useRouteError } from "react-router";

import { Button } from "@/components/ui/button";
import { USER_ERROR_COPY } from "@/lib/errors";

/**
 * The crash backstop (SHELL-04). Mounted as the root route's `errorElement`
 * in App.tsx — one wiring that covers two distinct failures:
 *   - a render exception anywhere below the root, and
 *   - an unmatched URL (react-router surfaces a no-match as a route error,
 *     so an unknown path lands here too, instead of react-router's own
 *     developer-facing default error page).
 *
 * Renders only shared crash-backstop copy — never the caught error's message
 * or stack (T-1-02, ASVS V7). The error is retained solely for console
 * diagnostics and never used as render input.
 */
export function RootErrorBoundary() {
  const error = useRouteError();

  // eslint-disable-next-line no-console
  console.error(error);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-[20px] leading-[1.2] font-semibold">
        {USER_ERROR_COPY.unexpectedCrash.title}
      </h1>
      <p className="text-sm leading-[1.5] text-muted-foreground">
        {USER_ERROR_COPY.unexpectedCrash.description}
      </p>
      <Button type="button" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </div>
  );
}
