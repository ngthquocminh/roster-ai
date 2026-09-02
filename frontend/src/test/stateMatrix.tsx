import type { ReactNode } from "react";

import { PRIMITIVE_FIXTURES, type PrimitiveFixture } from "@/components/primitives/fixtures";
import { Button } from "@/components/ui/button";

export type StateFamily =
  | "message" | "draft" | "run" | "comparison" | "approval"
  | "terminal-outcome" | "alert" | "skeleton" | "empty-state" | "provenance";

export type StateFixture = Readonly<{
  family: StateFamily;
  state: string;
  render: () => ReactNode;
}>;

/**
 * Exhaustive over `PrimitiveFixture["primitive"]` on purpose: the parameter is the
 * union, not `string`, so adding a primitive to `PRIMITIVE_FIXTURES` without filing
 * it here is a TypeScript error rather than a silent fall-through into `provenance`.
 * Family assignment decides what each state is compared against — distinctness is
 * pairwise WITHIN a family — so a mis-filed primitive quietly changes the proof.
 */
const primitiveFamily = (primitive: PrimitiveFixture["primitive"]): StateFamily => {
  switch (primitive) {
    case "StatusBadge":
      return "run";
    case "InlineAlert":
    case "ReconnectBanner":
      return "alert";
    case "Skeleton":
      return "skeleton";
    case "EmptyState":
      return "empty-state";
    case "EvidenceLink":
    case "EvidenceHighlight":
    case "IdentifierCopyButton":
      return "provenance";
  }
};

const primitiveStates: readonly StateFixture[] = PRIMITIVE_FIXTURES.map((fixture) => ({
  family: primitiveFamily(fixture.primitive),
  state: fixture.state,
  render: () => (
    <section aria-label={`${primitiveFamily(fixture.primitive)}: ${fixture.state}`}>
      {fixture.render()}
    </section>
  ),
}));

const literal = (family: StateFamily, state: string, text: string): StateFixture => ({
  family,
  state,
  render: () => <section aria-label={`${family}: ${state}`}><h3>{state}</h3><p>{text}</p></section>,
});

const customStates: readonly StateFixture[] = [
  literal("message", "planner message", "You asked to compare the saved schedule."),
  literal("message", "grounded agent response", "ShiftMind: 720 minutes, supported by Demand DEM-204."),
  literal("message", "clarification", "Clarification needed: choose one of the named demand records."),
  literal("message", "refusal", "Not supported: this request is outside the available capability."),
  literal("message", "approval rejected", "Approval rejected. The saved baseline did not change."),
  literal("message", "approval expired", "Approval expired. Request a new review before deciding."),
  literal("message", "approval stale", "Approval stale. Refresh the changed binding before deciding."),

  literal("draft", "fresh", "Draft is ready for review and has not changed."),
  literal("draft", "stale", "Draft is stale because the scenario version changed."),
  literal("draft", "rejected", "Draft was rejected and cannot be queued."),
  literal("draft", "queued-for-optimization", "Draft accepted. Optimization is queued."),

  literal("comparison", "populated", "Candidate coverage 95%; overtime 0%; cost decreased by 10%."),
  literal("comparison", "not computed", "Not computed: the baseline metric is absent."),

  {
    family: "approval", state: "pending", render: () => (
      <section aria-label="approval: pending"><h3>Pending approval</h3><p>Review the exact binding before deciding.</p>
        <Button className="min-h-11">Approve</Button><Button className="min-h-11" variant="outline">Reject</Button>
      </section>
    ),
  },
  literal("approval", "pending-overdue", "Pending, overdue. The decision remains available."),
  literal("approval", "rejected", "Approval rejected. No promotion occurred."),
  literal("approval", "expired", "Approval expired before a decision was recorded."),
  literal("approval", "stale", "Approval stale because its binding changed."),
  literal("approval", "consumed", "Approval consumed. The candidate became the baseline."),

  literal("terminal-outcome", "completed", "Run completed with a candidate result."),
  literal("terminal-outcome", "infeasible", "Run infeasible. No feasible schedule was found."),
  literal("terminal-outcome", "timed out", "Run timed out at the configured solver ceiling."),
  literal("terminal-outcome", "cancelled", "Run cancelled by the planner."),
  literal("terminal-outcome", "failed", "Run failed safely. The baseline remains unchanged."),
  literal("terminal-outcome", "approval rejected", "Final outcome: approval rejected."),
  literal("terminal-outcome", "approval expired", "Final outcome: approval expired."),
  literal("terminal-outcome", "approval stale", "Final outcome: approval stale."),
  literal("terminal-outcome", "non-promotable", "Candidate is not promotable; no Approve control is available."),

  literal("empty-state", "intrinsically empty", "No conversation activity exists yet."),
  literal("empty-state", "filtered empty", "No runs match the current filters."),
  literal("provenance", "collapsed item", "Decision provenance item collapsed."),
  literal("provenance", "expanded item with evidence", "Decision provenance expanded with Evidence demand DEM-204."),
  literal("provenance", "expanded item without evidence", "Decision provenance expanded; no evidence references were recorded."),
];

export const STATE_MATRIX: readonly StateFixture[] = [...primitiveStates, ...customStates];
