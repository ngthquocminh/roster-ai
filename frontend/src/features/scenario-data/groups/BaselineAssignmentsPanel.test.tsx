import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useBaselineAssignments: vi.fn() }));
import { useBaselineAssignments } from "@/hooks/useScenarioProjection";
import { BaselineAssignmentsPanel } from "./BaselineAssignmentsPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "BaselineAssignmentsPanel", caption: "Baseline assignments", Panel: BaselineAssignmentsPanel, hook: vi.mocked(useBaselineAssignments), columnHeaders: 5, expected: "worker-1", data: { items: [{ record_id: "a1", worker_id: "worker-1", task_id: "task-1", shift_id: null, start_minute: 480, end_minute: 960 }] } });
