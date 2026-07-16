import { ScenarioTable } from "@/components/scenarios/ScenarioTable";

/**
 * The Display-role page title (UI-SPEC Typography, 28px/600/1.2, used once
 * per view) plus the scenario list table (SCEN-01), which is the primary
 * focal point of this view per UI-SPEC's Application Structure. Plan 01-07
 * adds the persistent top-right "New Scenario" header button and its dialog;
 * this plan only mounts the table.
 */
export function Home() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-[28px] leading-[1.2] font-semibold">Scenarios</h1>
      <div className="mt-6">
        <ScenarioTable />
      </div>
    </div>
  );
}
