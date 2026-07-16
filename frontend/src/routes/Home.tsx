import { useState } from "react";

import { ScenarioTable } from "@/components/scenarios/ScenarioTable";
import { CreateScenarioDialog } from "@/components/scenarios/CreateScenarioDialog";
import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { Button } from "@/components/ui/button";
import { useScenarios } from "@/hooks/useScenarios";
import { useFixtures } from "@/hooks/useFixtures";

/**
 * The Display-role page title (UI-SPEC Typography, 28px/600/1.2, used once
 * per view) plus the scenario list table (SCEN-01), which is the primary
 * focal point of this view per UI-SPEC's Application Structure. This plan
 * (01-07) adds the persistent top-right "New Scenario" header button, wires
 * it and `ScenarioTable`'s empty-state button onto the same
 * `CreateScenarioDialog` instance, and is the single decision point for the
 * backend-unreachable banner (SHELL-04/concurrency edge).
 *
 * `useScenarios()` and `useFixtures()` are also called here (in addition to
 * `ScenarioTable` and `CreateScenarioDialog` calling them internally) purely
 * to read each query's `isError` flag for that banner decision — TanStack
 * Query dedupes by query key, so this adds no extra network request, only
 * an extra subscription to the same cached state.
 *
 * Single-banner rule: `ScenarioTable` already renders its own `ErrorBanner`
 * when the scenarios query fails (unchanged since plan 01-06), so this
 * component only adds a banner for the case `ScenarioTable`'s cannot cover —
 * fixtures failing while scenarios succeeds. When BOTH fail concurrently,
 * `ScenarioTable`'s banner already satisfies "exactly one" and this
 * component's own condition (`!scenariosQuery.isError`) evaluates to false,
 * so no second banner is added. [edge: SHELL-04/concurrency]
 */
export function Home() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const scenariosQuery = useScenarios();
  const fixturesQuery = useFixtures();

  const showFixturesOnlyBanner =
    fixturesQuery.isError && !scenariosQuery.isError;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-[28px] leading-[1.2] font-semibold">Scenarios</h1>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          New Scenario
        </Button>
      </div>
      {showFixturesOnlyBanner && <ErrorBanner error={fixturesQuery.error} />}
      <div className="mt-6">
        <ScenarioTable onCreateScenario={() => setDialogOpen(true)} />
      </div>
      <CreateScenarioDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
