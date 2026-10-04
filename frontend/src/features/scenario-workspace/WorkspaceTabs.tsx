import { useId } from "react";
import { NavLink, useMatch } from "react-router";

type WorkspaceTabsProps = Readonly<{ scenarioId: string }>;

export function WorkspaceTabs({ scenarioId }: WorkspaceTabsProps) {
  const resultsExplanationId = useId();
  // The Results tab points at the run being viewed (EXPERIENCE.md); with no run
  // in the URL it stays disabled. `Runs` is `end`-matched so it is not also
  // highlighted while a run's results are open.
  const selectedRunId = useMatch("/scenarios/:scenarioId/runs/:runId")?.params
    .runId;
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `inline-flex min-h-11 items-center border-b-2 px-3 text-sm font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 ${
      isActive
        ? "border-primary text-primary"
        : "border-transparent text-muted-foreground hover:text-foreground"
    }`;

  return (
    <nav
      aria-label="Scenario workspace"
      className="mt-3 overflow-x-auto border-b border-border"
    >
      <div className="flex min-w-max items-start whitespace-nowrap">
        {/* No Chat tab: chat is the workspace's side panel (ChatPanel). */}
        <NavLink className={linkClass} to={`/scenarios/${scenarioId}/data`}>
          Scenario Data
        </NavLink>
        <NavLink className={linkClass} end to={`/scenarios/${scenarioId}/runs`}>
          Runs
        </NavLink>
        {selectedRunId ? (
          <NavLink
            className={linkClass}
            to={`/scenarios/${scenarioId}/runs/${selectedRunId}`}
          >
            Results
          </NavLink>
        ) : (
          <div className="flex items-center gap-2 px-3">
            {/* aria-disabled has no defined semantics on a plain span (it only
                applies to elements with a widget role), so the real
                accessibility guarantee is this aria-describedby link: a screen
                reader announces "Results" together with the explanation next
                to it, regardless of whether aria-disabled itself is honored. */}
            <span
              aria-describedby={resultsExplanationId}
              aria-disabled="true"
              className="inline-flex min-h-11 items-center text-sm font-medium text-muted-foreground"
            >
              Results
            </span>
            <span
              className="text-xs text-muted-foreground"
              id={resultsExplanationId}
            >
              Results unavailable: select a run.
            </span>
          </div>
        )}
      </div>
    </nav>
  );
}
