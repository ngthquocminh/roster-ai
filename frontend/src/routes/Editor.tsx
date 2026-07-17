/**
 * The composed `/scenarios/:scenarioId` Editor route (SCEN-03 + CONS-01..05).
 * Mounts at ScenarioLayout's index route, replacing the prior placeholder.
 *
 * Owns the session transcript state (D-03, `TranscriptEntryData[]` via
 * `useState`) above both `ConstraintTranscript` and `ConstraintInput` —
 * appended on every outcome via `ConstraintInput`'s `onOutcome` prop, and
 * never reset/cleared on a rejected/clarification/no-match/503 outcome, so
 * CONS-04's "rephrase without losing their place" holds across submissions.
 *
 * Calls `useScenario` exactly once and passes that SAME query-result
 * instance into both `ScenarioHeader` and `useOverrides`'s dependent
 * `enabled` gate (`scenarioQuery.isSuccess`) — no duplicate fetch, per the
 * shared-instance prop contract `02-04-SUMMARY.md`/`02-05-SUMMARY.md`
 * establish. `useApplyConstraint`'s mutation (inside `ConstraintInput`)
 * invalidates the exact `["scenario", scenarioId, "overrides"]` key
 * `useOverrides` reads, so a successful apply refetches the durable list
 * without a manual refresh.
 *
 * 404 gate (E7): only a 404 on `GET /scenarios/{id}` is terminal — Editor
 * early-returns right after `ScenarioHeader` (which renders the "Scenario
 * not found" view itself) so nothing below it (transcript/input/overrides)
 * ever renders. Every other scenario-query state (loading, non-404 error,
 * populated) falls through to the full four-region layout, matching the
 * plan's literal "if 404 → gate, otherwise → render all four regions" shape.
 *
 * Regions render in the UI-SPEC's fixed vertical order, `gap-4` (md/16px)
 * apart: (1) scenario header, (2) constraint transcript, (3) constraint
 * input, (4) "Applied Overrides" Heading-role section title + the list.
 */
import * as React from "react";
import { useParams } from "react-router";

import { ScenarioHeader } from "@/components/editor/ScenarioHeader";
import { OverridesList } from "@/components/editor/OverridesList";
import {
  ConstraintTranscript,
  type TranscriptEntryData,
} from "@/components/editor/ConstraintTranscript";
import { ConstraintInput } from "@/components/editor/ConstraintInput";
import { useScenario } from "@/hooks/useScenario";
import { useOverrides } from "@/hooks/useOverrides";
import { getErrorStatus } from "@/lib/errors";

export function Editor() {
  const { scenarioId } = useParams();
  const scenarioQuery = useScenario(scenarioId as string);
  const overridesQuery = useOverrides(scenarioId as string, {
    enabled: scenarioQuery.isSuccess,
  });
  const [entries, setEntries] = React.useState<TranscriptEntryData[]>([]);

  const appendEntry = React.useCallback((entry: TranscriptEntryData) => {
    setEntries((previous) => [...previous, entry]);
  }, []);

  const errorStatus = getErrorStatus(scenarioQuery.error);
  const isNotFound = scenarioQuery.isError && errorStatus === 404;

  if (isNotFound) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <ScenarioHeader scenarioQuery={scenarioQuery} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-8">
      <ScenarioHeader scenarioQuery={scenarioQuery} />
      <ConstraintTranscript entries={entries} />
      <ConstraintInput
        scenarioId={scenarioId as string}
        onOutcome={appendEntry}
      />
      <div className="flex flex-col gap-2">
        <h2 className="text-[20px] leading-[1.2] font-semibold">
          Applied Overrides
        </h2>
        <OverridesList overridesQuery={overridesQuery} />
      </div>
    </div>
  );
}
