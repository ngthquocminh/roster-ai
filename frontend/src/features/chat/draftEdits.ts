/**
 * Pure helpers for the Draft card's in-place editor (Story 5.11 Decision 14).
 *
 * Kept out of the component so the validation rules and the edit-buffer shape
 * can be unit-tested without rendering, and so `ActivityTimeline` can hold the
 * buffers (Decision 13) without importing a component's internals.
 */
import {
  toConstraintInput,
  type Proposal,
  type ProposalConstraintInput,
} from "@/api/proposals";

/** One editable row: the UNTRUSTED wire shape plus the description it was seeded with. */
export type EditRow = Readonly<{
  input: ProposalConstraintInput;
  /** Server-composed at the version the row came from; never echoed back. */
  description: string;
}>;

/**
 * The planner's unsaved edits for one draft. `baseVersionId` is the server
 * version the rows were seeded from, so a version that moves underneath them is
 * detectable instead of silently overwriting or dropping the edits (C8).
 */
export type EditBuffer = Readonly<{
  baseVersionId: string;
  rows: readonly EditRow[];
}>;

export type EditableField = "n" | "factor" | "max_hours" | "start_minute" | "end_minute";

export type RowErrors = Partial<Record<EditableField, string>>;

/** Mirrors `HARD_MAX_HOURS_PER_WEEK` in `backend/application/drafting/resolve.py`. */
export const MAX_HOURS_PER_WEEK = 56;

export function rowsFromProposal(proposal: Proposal): EditRow[] {
  return proposal.constraints.map((constraint) => ({
    input: toConstraintInput(constraint),
    description: constraint.description ?? "",
  }));
}

const COMPARED: readonly (keyof ProposalConstraintInput)[] = [
  "kind", "group", "record_id", "related_group", "related_record_id",
  "n", "factor", "max_hours", "start_minute", "end_minute",
];

export function rowsEqual(a: readonly EditRow[], b: readonly EditRow[]): boolean {
  return a.length === b.length && a.every((row, index) =>
    COMPARED.every((key) => (row.input[key] ?? null) === (b[index].input[key] ?? null)),
  );
}

const isWhole = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isInteger(value);
const isFinitePositive = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value) && value > 0;

/**
 * The resolver's argument bounds, so obvious mistakes never leave the browser
 * (C10): `n`, `start_minute` and `end_minute` are whole numbers; `factor` and
 * `max_hours` are finite numbers. The server resolver stays the authority.
 * `horizon` is the scenario's `horizon_minutes`; its bound is skipped only while
 * it is unavailable.
 */
export function validateRow(
  input: ProposalConstraintInput,
  horizon: number | undefined,
): RowErrors {
  switch (input.kind) {
    case "set_min_workers_per_task":
      return isWhole(input.n) && input.n > 0
        ? {}
        : { n: "Minimum workers must be a whole number greater than 0." };
    case "scale_demand":
      return isFinitePositive(input.factor)
        ? {}
        : { factor: "Demand factor must be a number greater than 0." };
    case "set_max_hours":
      return isFinitePositive(input.max_hours) && input.max_hours <= MAX_HOURS_PER_WEEK
        ? {}
        : { max_hours: `Maximum hours must be a number greater than 0 and at most ${MAX_HOURS_PER_WEEK}.` };
    case "lock_worker_shift": {
      const { start_minute: start, end_minute: end } = input;
      const errors: RowErrors = {};
      if (!isWhole(start) || start < 0) {
        errors.start_minute = "Start minute must be a whole number, 0 or more.";
      }
      if (!isWhole(end)) {
        errors.end_minute = "End minute must be a whole number.";
      } else if (horizon !== undefined && end > horizon) {
        errors.end_minute = `End minute must be at most ${horizon}.`;
      }
      if (isWhole(start) && start >= 0 && isWhole(end)) {
        if (start >= end) {
          errors.start_minute ??= "Start minute must be before the end minute.";
          errors.end_minute ??= "End minute must be after the start minute.";
        }
      }
      return errors;
    }
    default:
      // `exclude_worker_from_task` carries no argument to edit.
      return {};
  }
}

/** The one state line a draft shows beside its title (Decision 14's table). */
export function stateLine(proposal: Proposal): string {
  if (proposal.state === "applied") {
    return proposal.applied_version_ordinal != null
      ? `Applied to baseline — v${proposal.applied_version_ordinal} promoted`
      : "Applied to baseline";
  }
  if (proposal.state === "rejected") {
    if (proposal.ended_by === "assistant") return "Discarded by assistant";
    if (proposal.ended_by === "system") return "Replaced by a newer draft";
    return "Discarded";
  }
  if (proposal.stale) return "Working draft · out of date";
  return proposal.version_ordinal != null
    ? `Working draft · v${proposal.version_ordinal}`
    : "Working draft";
}
