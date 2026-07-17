/**
 * SCEN-03 single-record detail header (UI-SPEC E1/E7). Takes the raw
 * `useScenario(id)` query-result object as a prop — not a `scenarioId` —
 * so plan 02-06's `Editor` can share one `useScenario` instance between
 * this header and `useOverrides`'s dependent-query `enabled` gate
 * (`scenarioQuery.isSuccess`).
 *
 * State-by-state:
 *   - Loading: centered spinner + literal "Loading scenario…" text only.
 *   - Error, 404: the terminal "Scenario not found" view (E7) — this is
 *     what finally resolves Phase 1's bad-deep-link backstop. Branches on
 *     `error.status === 404`, not message text (T-02-12), so a non-404
 *     failure can never be misrendered as "not found".
 *   - Error, non-404: reuses `ErrorBanner` — no new error surface invented.
 *   - Populated: name (Heading role), fixture (monospace, matching
 *     `ScenarioTable`'s fixture-column convention), time_limit_s and
 *     created_at as Label-role captions.
 *
 * `name`/`fixture` are rendered only as JSX text children (T-02-10) —
 * React's default text-node escaping is the complete mitigation; no
 * dangerouslySetInnerHTML anywhere in this file.
 */
import { Link } from "react-router";
import { LoaderCircle } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { buttonVariants } from "@/components/ui/button";
import { getErrorStatus } from "@/lib/errors";
import type { components } from "@/api/schema";

type ScenarioOut = components["schemas"]["ScenarioOut"];

export function ScenarioHeader({
  scenarioQuery,
}: {
  scenarioQuery: UseQueryResult<ScenarioOut, unknown>;
}) {
  const { data, isLoading, isError, error } = scenarioQuery;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <LoaderCircle
          className="size-6 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Loading scenario…
        </p>
      </div>
    );
  }

  if (isError) {
    const status = getErrorStatus(error);
    if (status === 404) {
      return (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <h2 className="text-[20px] leading-[1.2] font-semibold">
            Scenario not found
          </h2>
          <p className="text-sm leading-[1.5] text-muted-foreground">
            It may have been removed, or the link is incorrect.
          </p>
          <Link to="/" className={buttonVariants({ variant: "default" })}>
            Back to Scenarios
          </Link>
        </div>
      );
    }
    return <ErrorBanner error={error} />;
  }

  if (!data) {
    // Unreachable in practice (TanStack Query guarantees data once neither
    // isLoading nor isError) — kept only to satisfy strict null-checking.
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <h1 className="text-[20px] leading-[1.2] font-semibold">{data.name}</h1>
      <p
        className="font-mono truncate text-sm text-muted-foreground"
        title={data.fixture}
      >
        {data.fixture}
      </p>
      <div className="flex gap-4">
        <span className="text-xs leading-[1.2] text-muted-foreground">
          Time limit: {data.time_limit_s}s
        </span>
        <span className="text-xs leading-[1.2] text-muted-foreground">
          Created: {data.created_at}
        </span>
      </div>
    </div>
  );
}
