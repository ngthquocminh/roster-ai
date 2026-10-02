import { describe, expect, it } from "vitest";

import type { Proposal, ProposalConstraintInput } from "@/api/proposals";
import { rowsEqual, stateLine, validateRow, type EditRow } from "./draftEdits";

const input = (overrides: Partial<ProposalConstraintInput>): ProposalConstraintInput => ({
  kind: "set_max_hours", group: "workers", record_id: "w1", related_group: null,
  related_record_id: null, n: null, factor: null, max_hours: null, start_minute: null,
  end_minute: null, schema_version: "1", ...overrides,
});
const row = (overrides: Partial<ProposalConstraintInput>): EditRow => ({ input: input(overrides), description: "d" });

describe("validateRow (mirrors backend/application/drafting/resolve.py, C10)", () => {
  it("n is a whole number above 0", () => {
    const of = (n: number | null) => validateRow(input({ kind: "set_min_workers_per_task", n }), 100);
    expect(of(1)).toEqual({});
    for (const bad of [0, -1, 1.5, null]) expect(of(bad).n).toBeTruthy();
  });

  it("factor and max_hours are NOT integers: fractional values are valid", () => {
    expect(validateRow(input({ kind: "scale_demand", factor: 0.5 }), 100)).toEqual({});
    expect(validateRow(input({ kind: "set_max_hours", max_hours: 37.5 }), 100)).toEqual({});
    expect(validateRow(input({ kind: "scale_demand", factor: 0 }), 100).factor).toBeTruthy();
    expect(validateRow(input({ kind: "scale_demand", factor: Number.POSITIVE_INFINITY }), 100).factor).toBeTruthy();
  });

  it("max_hours is at most 56", () => {
    expect(validateRow(input({ max_hours: 56 }), 100)).toEqual({});
    expect(validateRow(input({ max_hours: 56.5 }), 100).max_hours).toMatch(/at most 56/);
    expect(validateRow(input({ max_hours: 0 }), 100).max_hours).toBeTruthy();
  });

  it("lock_worker_shift: 0 <= start < end <= horizon, all whole", () => {
    // `null` means "horizon unavailable" (a default parameter would swallow `undefined`).
    const lock = (start: number | null, end: number | null, horizon: number | null = 100) =>
      validateRow(input({ kind: "lock_worker_shift", start_minute: start, end_minute: end }), horizon ?? undefined);
    expect(lock(0, 100)).toEqual({});
    expect(lock(10, 20)).toEqual({});
    expect(lock(-1, 20).start_minute).toBeTruthy();
    expect(lock(20, 20).start_minute).toBeTruthy();
    expect(lock(20, 20).end_minute).toBeTruthy();
    expect(lock(1.5, 20).start_minute).toBeTruthy();
    expect(lock(10, 20.5).end_minute).toBeTruthy();
    expect(lock(10, 101).end_minute).toMatch(/at most 100/);
    expect(lock(null, 20).start_minute).toBeTruthy();
    // Only the horizon bound is skipped while the horizon is unavailable.
    expect(lock(10, 1_000_000, null)).toEqual({});
    expect(lock(30, 20, null).end_minute).toBeTruthy();
  });

  it("exclude_worker_from_task has nothing to validate", () => {
    expect(validateRow(input({ kind: "exclude_worker_from_task" }), 100)).toEqual({});
  });
});

describe("rowsEqual", () => {
  it("compares every editable argument and the row count", () => {
    expect(rowsEqual([row({ max_hours: 40 })], [row({ max_hours: 40 })])).toBe(true);
    expect(rowsEqual([row({ max_hours: 40 })], [row({ max_hours: 41 })])).toBe(false);
    expect(rowsEqual([row({ max_hours: 40 })], [row({ max_hours: 40 }), row({ max_hours: 40 })])).toBe(false);
    expect(rowsEqual([row({ start_minute: 1 })], [row({ start_minute: null })])).toBe(false);
    expect(rowsEqual([row({ record_id: "w1" })], [row({ record_id: "w2" })])).toBe(false);
  });
});

describe("stateLine (Decision 14's table, verbatim)", () => {
  const p = (overrides: Record<string, unknown>) => ({
    state: "active", stale: false, version_ordinal: 3, ended_by: null,
    applied_version_ordinal: null, ...overrides,
  }) as unknown as Proposal;

  it.each([
    [{}, "Working draft · v3"],
    [{ version_ordinal: null }, "Working draft"],
    [{ stale: true }, "Working draft · out of date"],
    [{ state: "rejected", ended_by: "planner" }, "Discarded"],
    [{ state: "rejected", ended_by: null }, "Discarded"],
    [{ state: "rejected", ended_by: "assistant" }, "Discarded by assistant"],
    [{ state: "rejected", ended_by: "system" }, "Replaced by a newer draft"],
    [{ state: "applied", ended_by: "system", applied_version_ordinal: 2 }, "Applied to baseline — v2 promoted"],
    // A promotion recorded before the lifecycle columns carries no ordinal.
    [{ state: "applied", ended_by: "system", applied_version_ordinal: null }, "Applied to baseline"],
    // An ended state wins over staleness.
    [{ state: "rejected", ended_by: "planner", stale: true }, "Discarded"],
  ])("%j", (overrides, line) => expect(stateLine(p(overrides))).toBe(line));
});
