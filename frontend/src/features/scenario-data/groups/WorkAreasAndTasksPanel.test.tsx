import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useWorkAreasAndTasks: vi.fn() }));
import { useWorkAreasAndTasks } from "@/hooks/useScenarioProjection";
import { WorkAreasAndTasksPanel } from "./WorkAreasAndTasksPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "WorkAreasAndTasksPanel", caption: "Work areas and tasks", Panel: WorkAreasAndTasksPanel, hook: vi.mocked(useWorkAreasAndTasks), columnHeaders: 6, expected: "Picking", data: { items: [{ record_id: "r1", task_id: "task-1", name: "Picking", function: "outbound", area_id: "area-1", area_name: "North", unit_type_id: null }] } });
