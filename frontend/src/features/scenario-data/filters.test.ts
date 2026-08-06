import { describe, expect, it } from "vitest";

import { FILTERS_BY_GROUP } from "./filters";

describe("scenario data filter descriptors", () => {
  it("matches the backend parameter vocabulary one-for-one", () => {
    expect(Object.fromEntries(Object.entries(FILTERS_BY_GROUP).map(([group, filters]) => [group, filters.map((filter) => filter.param)]))).toEqual({
      "work-areas-and-tasks": ["task_id", "name_contains", "function", "area_id"],
      workers: ["contact_id", "name_contains", "employment_type", "grade", "qualified_task_id"],
      demand: ["family", "task_id", "area_id", "start_minute_gte", "end_minute_lte"],
      "baseline-assignments": ["worker_id", "task_id", "shift_id"],
      locks: ["target_type", "target_ref", "scope", "source"],
      "constraints-and-objectives": ["constraint_type", "value_type"],
    });
  });

  it("uses a select only for demand family and numbers only for minute bounds", () => {
    const demand = FILTERS_BY_GROUP.demand;
    expect(demand.find((filter) => filter.param === "family")).toMatchObject({ kind: "select", options: ["outbound", "inbound", "indirect"] });
    expect(demand.filter((filter) => filter.kind === "number").map((filter) => filter.param)).toEqual(["start_minute_gte", "end_minute_lte"]);
  });
});
