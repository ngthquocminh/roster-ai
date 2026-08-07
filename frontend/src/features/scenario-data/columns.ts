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
  essential: boolean;
  monospace?: boolean;
  sortKey?: string;
  copyType?: string;
};

export const COLUMNS_BY_GROUP = {
  "work-areas-and-tasks": [
    { key: "task_id", header: "Task ID", required: true, essential: true, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "name", header: "Name", required: true, essential: true, sortKey: "name" },
    { key: "function", header: "Function", required: false, essential: true, sortKey: "function" },
    { key: "area_id", header: "Area ID", required: false, essential: false, monospace: true, sortKey: "area_id", copyType: "Area ID" },
    { key: "area_name", header: "Area name", required: false, essential: false, sortKey: "area_name" },
    { key: "unit_type_id", header: "Unit type ID", required: false, essential: false, monospace: true },
  ],
  workers: [
    { key: "contact_id", header: "Contact ID", required: true, essential: true, monospace: true, sortKey: "contact_id", copyType: "Contact ID" },
    { key: "name", header: "Name", required: true, essential: true, sortKey: "name" },
    { key: "employment_type", header: "Employment type", required: false, essential: true, sortKey: "employment_type" },
    { key: "grade", header: "Grade", required: false, essential: false, sortKey: "grade" },
    { key: "eba", header: "EBA", required: false, essential: false },
    { key: "contracted_hours", header: "Contracted hours", required: false, essential: false, sortKey: "contracted_hours" },
    { key: "qualifications", header: "Qualifications", required: false, essential: false },
    { key: "availability_windows", header: "Availability windows", required: false, essential: false },
  ],
  demand: [
    { key: "record_id", header: "Record ID", required: true, essential: true, monospace: true, copyType: "Record ID" },
    { key: "family", header: "Family", required: false, essential: true, sortKey: "family" },
    { key: "task_id", header: "Task ID", required: false, essential: false, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "area_id", header: "Area ID", required: false, essential: false, monospace: true, copyType: "Area ID" },
    { key: "window", header: "Window", required: true, essential: true, sortKey: "start_minute" },
    { key: "amount", header: "Amount", required: false, essential: true, sortKey: "amount" },
    { key: "unit", header: "Unit", required: false, essential: true },
  ],
  "baseline-assignments": [
    { key: "record_id", header: "Record ID", required: true, essential: true, monospace: true, copyType: "Record ID" },
    { key: "worker_id", header: "Worker ID", required: false, essential: true, monospace: true, sortKey: "worker_id", copyType: "Worker ID" },
    { key: "task_id", header: "Task ID", required: false, essential: true, monospace: true, sortKey: "task_id", copyType: "Task ID" },
    { key: "shift_id", header: "Shift ID", required: false, essential: false, monospace: true, copyType: "Shift ID" },
    { key: "window", header: "Window", required: true, essential: true, sortKey: "start_minute" },
  ],
  locks: [
    { key: "record_id", header: "Record ID", required: true, essential: true, monospace: true, copyType: "Record ID" },
    { key: "target_type", header: "Target type", required: false, essential: true, sortKey: "target_type" },
    { key: "target_ref", header: "Target ref", required: true, essential: true, monospace: true, sortKey: "target_ref", copyType: "Target ref" },
    { key: "scope", header: "Scope", required: false, essential: false, sortKey: "scope" },
    { key: "source", header: "Source", required: false, essential: false, sortKey: "source" },
  ],
  "constraints-and-objectives": [
    { key: "record_id", header: "Record ID", required: true, essential: true, monospace: true, copyType: "Record ID" },
    { key: "constraint_type", header: "Constraint type", required: true, essential: true, sortKey: "constraint_type" },
    { key: "value", header: "Value", required: false, essential: true },
    { key: "value_type", header: "Value type", required: false, essential: false, sortKey: "value_type" },
  ],
} as const satisfies Record<ScenarioDataListGroup, readonly ColumnDef[]>;
