import { NavLink, Outlet, useMatch, useParams } from "react-router";

import { cn } from "@/lib/utils";

/**
 * Persistent three-tab nav within `/scenarios/:scenarioId/*` (UI-SPEC
 * Application Structure, tier 2) + an `Outlet` for whichever tab body is
 * active. Phases 2-4 replace the placeholder body behind a tab, not the tab
 * itself.
 *
 * Two traps this component exists to avoid (see RESEARCH.md / plan
 * annotations):
 * 1. Editor sits at this layout's *index* route (`/scenarios/:scenarioId`),
 *    which is a URL *prefix* of Runs and Results. `NavLink`'s `end` prop is
 *    required on both Editor and Runs so a nested route doesn't also mark
 *    its parent tab active (SHELL-03/precision).
 * 2. Results has no static path to link to — `runs/:runId` requires a
 *    runId nothing in Phase 1 produces. It renders as a disabled tab rather
 *    than linking somewhere invented; the route itself stays deep-linkable
 *    by URL (criterion 3), only the in-app link source is deferred to
 *    Phase 3 (first run produced).
 */
export function ScenarioLayout() {
  const { scenarioId } = useParams();
  const resultsMatch = useMatch("/scenarios/:scenarioId/runs/:runId");

  const tabClassName = ({ isActive }: { isActive: boolean }) =>
    cn(
      "inline-flex h-8 items-center border-b-2 px-2.5 text-sm font-medium transition-colors",
      isActive
        ? "border-[#4F46E5] text-[#4F46E5]"
        : "border-transparent text-muted-foreground hover:text-foreground",
    );

  return (
    <div>
      <nav
        aria-label="Scenario views"
        className="border-b border-border bg-[#F5F5F5] px-6"
      >
        <ul className="flex gap-4">
          <li>
            <NavLink to={`/scenarios/${scenarioId}`} end className={tabClassName}>
              Editor
            </NavLink>
          </li>
          <li>
            <NavLink
              to={`/scenarios/${scenarioId}/runs`}
              end
              className={tabClassName}
            >
              Runs
            </NavLink>
          </li>
          <li>
            <button
              type="button"
              disabled
              aria-disabled="true"
              aria-current={resultsMatch ? "page" : undefined}
              className={cn(
                "inline-flex h-8 cursor-not-allowed items-center border-b-2 px-2.5 text-sm font-medium",
                resultsMatch
                  ? "border-[#4F46E5] text-[#4F46E5]"
                  : "border-transparent text-muted-foreground/60",
              )}
            >
              Results
            </button>
          </li>
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}
