/**
 * SCEN-01's five list states (UI-SPEC E1), plus the identity/ordering edges
 * called out by the threat model and this plan's must_haves. Consumes
 * `useScenarios()` directly — no prop-drilling, no local transformation of
 * the response.
 *
 * State-by-state, the deliberate (not accidental) choices:
 *   - Loading: a centered spinner + literal text only. No fake rows are ever
 *     shown before real data exists.
 *   - Empty: replaces the table entirely (no header row over a void). The
 *     "New Scenario" button here is intentionally inert — plan 01-07 wires
 *     the create-scenario dialog onto it; this plan only renders it.
 *   - Error: renders `ErrorBanner` and nothing else — never stale or partial
 *     rows from a previous successful fetch.
 *   - Populated: rows render in the exact order `useScenarios()` returns
 *     (the server's own newest-first ordering) — no client-side re-ordering
 *     is applied here or anywhere in this file. Keyed by `id`, never `name`,
 *     because scenario names are not unique.
 *   - Overflow: the table body scrolls inside a fixed-height container past
 *     roughly 10 rows; no page-by-page navigation control exists.
 *
 * No row-count label is rendered anywhere (UI-SPEC E1/zero-one-many): one
 * row and many rows share identical chrome.
 *
 * `name` is rendered only as a JSX text child (T-1-03) — React's default
 * text-node escaping is the complete mitigation; no raw-HTML injection API
 * is used or imported here.
 *
 * `onCreateScenario` (plan 01-07): the empty-state "New Scenario" button was
 * left deliberately inert by plan 01-06 — this optional callback is how
 * `Home` wires it to the same create-scenario dialog as the header button,
 * without this component owning any dialog-open state itself.
 */
import { useNavigate } from "react-router";
import { LoaderCircle } from "lucide-react";

import { useScenarios } from "@/hooks/useScenarios";
import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function ScenarioTable({
  onCreateScenario,
}: {
  onCreateScenario?: () => void;
} = {}) {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useScenarios();

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <LoaderCircle
          className="size-6 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Loading scenarios…
        </p>
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner error={error} />;
  }

  const scenarios = data ?? [];

  if (scenarios.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h2 className="text-[20px] leading-[1.2] font-semibold">
          No scenarios yet
        </h2>
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Create one from a fixture to get started.
        </p>
        <Button type="button" onClick={onCreateScenario}>
          New Scenario
        </Button>
      </div>
    );
  }

  return (
    <div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Fixture</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {scenarios.map((scenario) => (
            <TableRow
              key={scenario.id}
              tabIndex={0}
              className="cursor-pointer"
              onClick={() => navigate(`/scenarios/${scenario.id}`)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  navigate(`/scenarios/${scenario.id}`);
                }
              }}
            >
              <TableCell>{scenario.name}</TableCell>
              <TableCell className="font-mono">{scenario.fixture}</TableCell>
              <TableCell>{scenario.created_at}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
