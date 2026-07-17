/**
 * SCEN-03/D-01/D-02 durable Applied Overrides list (UI-SPEC E2). Takes the
 * raw `useOverrides(id, {enabled})` query-result object as a prop — not a
 * `scenarioId` — mirroring `ScenarioHeader`'s shape so plan 02-06's
 * `Editor` can pass the dependent-query result straight through.
 *
 * Copies `ScenarioTable.tsx`'s loading/error/empty/populated/overflow state
 * machine (see that file's header comment for the identical rationale):
 *   - Loading: centered spinner + literal "Loading overrides…" text only.
 *   - Error: reuses `ErrorBanner` — no partial/stale rows are ever shown.
 *   - Empty: replaces the list entirely with "No constraints applied yet".
 *   - Populated: one row per override, `override.parsed_constraint`
 *     rendered VERBATIM (D-02) — never the raw `{tool, args}` object
 *     (CONS-02). A legacy override (parsed_constraint null/undefined)
 *     renders the "{Tool Label}: key=value" fallback instead, italic +
 *     muted, with a "(legacy entry)" caption — honest about lower fidelity
 *     rather than inventing a humanized sentence the client cannot safely
 *     construct (it lacks task/member name lookups).
 *   - Overflow: `max-h-[420px] overflow-y-auto` container, same class as
 *     `ScenarioTable`'s.
 *
 * Rows are keyed by `override.id`, never index, and rendered in exactly the
 * order `data` is received — no client-side re-sort anywhere in this file
 * (same principle as `ScenarioTable`'s comment).
 *
 * `parsed_constraint` / legacy args values are rendered only as JSX text
 * children (T-02-10) — React's default text-node escaping is the complete
 * mitigation; no dangerouslySetInnerHTML anywhere in this file.
 */
import { LoaderCircle } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { toolLabel } from "@/lib/toolLabels";
import type { components } from "@/api/schema";

type OverrideOut = components["schemas"]["OverrideOut"];

function legacyFallbackText(override: OverrideOut): string {
  const argsText = Object.entries(override.args)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(", ");
  return `${toolLabel(override.tool)}: ${argsText}`;
}

export function OverridesList({
  overridesQuery,
}: {
  overridesQuery: UseQueryResult<OverrideOut[], unknown>;
}) {
  const { data, isLoading, isError, error } = overridesQuery;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <LoaderCircle
          className="size-6 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Loading overrides…
        </p>
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner error={error} />;
  }

  const overrides = data ?? [];

  if (overrides.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h2 className="text-[20px] leading-[1.2] font-semibold">
          No constraints applied yet
        </h2>
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Type a plain-English constraint below to add one.
        </p>
      </div>
    );
  }

  return (
    <div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
      {overrides.map((override) => (
        <div
          key={override.id}
          className="border-b border-border px-4 py-2 last:border-b-0"
        >
          {override.parsed_constraint ? (
            <p className="text-sm leading-[1.5]">
              {override.parsed_constraint}
            </p>
          ) : (
            <div>
              <p className="text-sm leading-[1.5] text-muted-foreground italic">
                {legacyFallbackText(override)}
              </p>
              <p className="text-xs leading-[1.2] text-muted-foreground">
                (legacy entry)
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
