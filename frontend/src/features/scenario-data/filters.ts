import type { ScenarioDataListGroup } from "./columns";

export type FilterDef = {
  param: string;
  label: string;
  kind: "text" | "number" | "select";
  options?: readonly string[];
};

export const FILTERS_BY_GROUP = {
  "work-areas-and-tasks": [
    { param: "task_id", label: "Task ID", kind: "text" },
    { param: "name_contains", label: "Name contains", kind: "text" },
    { param: "function", label: "Function", kind: "text" },
    { param: "area_id", label: "Area ID", kind: "text" },
  ],
  workers: [
    { param: "contact_id", label: "Contact ID", kind: "text" },
    { param: "name_contains", label: "Name contains", kind: "text" },
    { param: "employment_type", label: "Employment type", kind: "text" },
    { param: "grade", label: "Grade", kind: "text" },
    { param: "qualified_task_id", label: "Qualified task ID", kind: "text" },
  ],
  demand: [
    { param: "family", label: "Family", kind: "select", options: ["outbound", "inbound", "indirect"] },
    { param: "task_id", label: "Task ID", kind: "text" },
    { param: "area_id", label: "Area ID", kind: "text" },
    { param: "start_minute_gte", label: "Start minute at or after", kind: "number" },
    { param: "end_minute_lte", label: "End minute at or before", kind: "number" },
  ],
  "baseline-assignments": [
    { param: "worker_id", label: "Worker ID", kind: "text" },
    { param: "task_id", label: "Task ID", kind: "text" },
    { param: "shift_id", label: "Shift ID", kind: "text" },
  ],
  locks: [
    { param: "target_type", label: "Target type", kind: "text" },
    { param: "target_ref", label: "Target ref", kind: "text" },
    { param: "scope", label: "Scope", kind: "text" },
    { param: "source", label: "Source", kind: "text" },
  ],
  "constraints-and-objectives": [
    { param: "constraint_type", label: "Constraint type", kind: "text" },
    { param: "value_type", label: "Value type", kind: "text" },
  ],
} as const satisfies Record<ScenarioDataListGroup, readonly FilterDef[]>;
