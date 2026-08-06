export type ScenarioDataListGroup =
  | "work-areas-and-tasks"
  | "workers"
  | "demand"
  | "baseline-assignments"
  | "locks"
  | "constraints-and-objectives";

export type ColumnDef = {
  key: string;
  header: string;
  required: boolean;
  monospace?: boolean;
  sortKey?: string;
  copyType?: string;
};

export const COLUMNS_BY_GROUP = {
  "work-areas-and-tasks": [
    { key: "task_id", header: "Task ID", required: true, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "name", header: "Name", required: true, sortKey: "name" },
    { key: "function", header: "Function", required: false, sortKey: "function" },
    { key: "area_id", header: "Area ID", required: false, monospace: true, sortKey: "area_id", copyType: "Area ID" },
    { key: "area_name", header: "Area name", required: false, sortKey: "area_name" },
    { key: "unit_type_id", header: "Unit type ID", required: false, monospace: true },
  ],
  workers: [
    { key: "contact_id", header: "Contact ID", required: true, monospace: true, sortKey: "contact_id", copyType: "Contact ID" },
    { key: "name", header: "Name", required: true, sortKey: "name" },
    { key: "employment_type", header: "Employment type", required: false, sortKey: "employment_type" },
    { key: "grade", header: "Grade", required: false, sortKey: "grade" },
    { key: "eba", header: "EBA", required: false },
    { key: "contracted_hours", header: "Contracted hours", required: false, sortKey: "contracted_hours" },
    { key: "qualifications", header: "Qualifications", required: false },
    { key: "availability_windows", header: "Availability windows", required: false },
  ],
  demand: [
    { key: "record_id", header: "Record ID", required: true, monospace: true, copyType: "Record ID" },
    { key: "family", header: "Family", required: false, sortKey: "family" },
    { key: "task_id", header: "Task ID", required: false, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "area_id", header: "Area ID", required: false, monospace: true, copyType: "Area ID" },
    { key: "window", header: "Window", required: true, sortKey: "start_minute" },
    { key: "amount", header: "Amount", required: false, sortKey: "amount" },
    { key: "unit", header: "Unit", required: false },
  ],
  "baseline-assignments": [
    { key: "record_id", header: "Record ID", required: true, monospace: true, copyType: "Record ID" },
    { key: "worker_id", header: "Worker ID", required: false, monospace: true, sortKey: "worker_id", copyType: "Worker ID" },
    { key: "task_id", header: "Task ID", required: false, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "shift_id", header: "Shift ID", required: false, monospace: true, copyType: "Shift ID" },
    { key: "window", header: "Window", required: true, sortKey: "start_minute" },
  ],
  locks: [
    { key: "record_id", header: "Record ID", required: true, monospace: true, copyType: "Record ID" },
    { key: "target_type", header: "Target type", required: false, sortKey: "target_type" },
    { key: "target_ref", header: "Target ref", required: true, monospace: true, sortKey: "target_ref", copyType: "Target ref" },
    { key: "scope", header: "Scope", required: false, sortKey: "scope" },
    { key: "source", header: "Source", required: false, sortKey: "source" },
  ],
  "constraints-and-objectives": [
    { key: "record_id", header: "Record ID", required: true, monospace: true, copyType: "Record ID" },
    { key: "constraint_type", header: "Constraint type", required: true, sortKey: "constraint_type" },
    { key: "value", header: "Value", required: false },
    { key: "value_type", header: "Value type", required: false, sortKey: "value_type" },
  ],
} as const satisfies Record<ScenarioDataListGroup, readonly ColumnDef[]>;
