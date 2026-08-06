import { describe, expect, it } from "vitest";

import { COLUMNS_BY_GROUP } from "./columns";

describe("scenario data column descriptors", () => {
  it("matches the six shipped panel header sets", () => {
    expect(Object.fromEntries(Object.entries(COLUMNS_BY_GROUP).map(([group, columns]) => [group, columns.map((column) => column.header)]))).toEqual({
      "work-areas-and-tasks": ["Task ID", "Name", "Function", "Area ID", "Area name", "Unit type ID"],
      workers: ["Contact ID", "Name", "Employment type", "Grade", "EBA", "Contracted hours", "Qualifications", "Availability windows"],
      demand: ["Record ID", "Family", "Task ID", "Area ID", "Window", "Amount", "Unit"],
      "baseline-assignments": ["Record ID", "Worker ID", "Task ID", "Shift ID", "Window"],
      locks: ["Record ID", "Target type", "Target ref", "Scope", "Source"],
      "constraints-and-objectives": ["Record ID", "Constraint type", "Value", "Value type"],
    });
  });

  it("keeps exactly two required columns in every group", () => {
    for (const columns of Object.values(COLUMNS_BY_GROUP)) {
      expect(columns.filter((column) => column.required)).toHaveLength(2);
    }
  });
});
