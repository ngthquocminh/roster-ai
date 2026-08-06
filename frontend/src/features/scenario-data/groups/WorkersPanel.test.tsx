import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useWorkers: vi.fn() }));
import { useWorkers } from "@/hooks/useScenarioProjection";
import { WorkersPanel } from "./WorkersPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "WorkersPanel", caption: "Workers", Panel: WorkersPanel, hook: vi.mocked(useWorkers), columnHeaders: 8, expected: "Alex", data: { items: [{ record_id: "r1", contact_id: "worker-1", name: "Alex", employment_type: "full-time", grade: "G1", eba: "EBA-A", contracted_hours: 38, qualifications: [{ task_id: "task-1", rate: 1.5 }], availability_windows: [{ kind: "availability", start_minute: 480, end_minute: 960 }] }] } });
