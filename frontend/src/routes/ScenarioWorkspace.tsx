import { useEffect, useRef } from "react";
import { Link, Outlet, useParams } from "react-router";

import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { ScenarioVersionContext } from "@/features/scenario-workspace/ScenarioVersionContext";
import { WorkspaceTabs } from "@/features/scenario-workspace/WorkspaceTabs";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { getErrorStatus, TERMINAL_STATUSES, USER_ERROR_COPY } from "@/lib/errors";
import { formatTimestamp } from "@/lib/formatTimestamp";


export function ScenarioWorkspace() {
  const { scenarioId = "" } = useParams();
  const query = useScenarioContext(scenarioId);
  const terminalHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorStatus = getErrorStatus(query.error);

  useRedirectOnUnauthorized(errorStatus);

  // Focus moves exactly once, on the settled state. The ref is attached only
  // to terminal headings, so on success this no-ops and ScenarioVersionContext
  // focuses its own heading — previously both fired and a screen reader was
  // interrupted mid-announcement.
  useEffect(() => {
    if (!query.isPending) {
      terminalHeadingRef.current?.focus();
    }
  }, [query.isPending, query.isError, query.data]);

  if (errorStatus === 401) {
    return null;
  }

  if (query.isPending) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-2xl font-semibold">Scenario workspace</h1>
        <p
          aria-live="polite"
          className="mt-3 text-sm text-muted-foreground"
        >
          Loading scenario context…
        </p>
      </main>
    );
  }

  if (query.isError && TERMINAL_STATUSES.has(errorStatus ?? 0)) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1
          className="text-2xl font-semibold outline-none"
          ref={terminalHeadingRef}
          tabIndex={-1}
        >
          Scenario not found
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          The requested scenario is not available.
        </p>
        <Link
          className="mt-5 inline-flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
          to="/"
        >
          Return to catalogue
        </Link>
      </main>
    );
  }

  // A failed background refetch must not tear down the persistent context
  // (AC #3). Mirrors FixtureCatalogueView: only an error with no cached data
  // is fatal; an error *with* data keeps the context and labels it stale.
  if (query.isError && !query.data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1
          className="text-2xl font-semibold outline-none"
          ref={terminalHeadingRef}
          tabIndex={-1}
        >
          Scenario workspace
        </h1>
        <InlineAlert
          action={
            <div className="flex flex-wrap items-center gap-3">
              <Button
                className="min-h-11"
                onClick={() => {
                  void query.refetch();
                }}
                type="button"
                variant="outline"
              >
                Retry
              </Button>
              <Link
                className="inline-flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                to="/"
              >
                Return to catalogue
              </Link>
            </div>
          }
          className="mt-5"
          description={USER_ERROR_COPY.connection.description}
          title={USER_ERROR_COPY.connection.title}
          variant="destructive"
        />
      </main>
    );
  }

  if (!query.data) {
    return null;
  }

  return (
    <main className="px-6 py-8">
      {query.isError ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 px-3 py-2">
          {/* EXPERIENCE.md:122 Scenario Data row — the approved stale label for
              a surface in this workspace. Only the message is a live region;
              the control stays outside it. */}
          <span className="text-sm" role="status">
            Stale — last verified at {formatTimestamp(
              new Date(query.dataUpdatedAt).toISOString(),
            )}
          </span>
          <Button
            className="min-h-11"
            onClick={() => {
              void query.refetch();
            }}
            type="button"
            variant="outline"
          >
            Retry
          </Button>
        </div>
      ) : null}
      <ScenarioVersionContext context={query.data} />
      <WorkspaceTabs scenarioId={scenarioId} />
      <Outlet />
    </main>
  );
}
