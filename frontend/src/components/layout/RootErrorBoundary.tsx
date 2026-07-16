import { useRouteError } from "react-router";

import { Button } from "@/components/ui/button";

/**
 * The crash backstop (SHELL-04). Mounted as the root route's `errorElement`
 * in App.tsx — one wiring that covers two distinct failures:
 *   - a render exception anywhere below the root, and
 *   - an unmatched URL (react-router surfaces a no-match as a route error,
 *     so an unknown path lands here too, instead of react-router's own
 *     developer-facing default error page).
 *
 * Renders only UI-SPEC's fixed crash-backstop copy — never the caught
 * error's message or stack (T-1-02, ASVS V7). The error is accepted only so
 * it can be logged to the console for whoever can act on it; the body copy
 * already tells the user that's where the diagnostic detail lives.
 */
export function RootErrorBoundary() {
  const error = useRouteError();

  // eslint-disable-next-line no-console
  console.error(error);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-[20px] leading-[1.2] font-semibold">
        Something went wrong.
      </h1>
      <p className="text-sm leading-[1.5] text-muted-foreground">
        Reload the page. If this keeps happening, check the browser console.
      </p>
      <Button type="button" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </div>
  );
}
