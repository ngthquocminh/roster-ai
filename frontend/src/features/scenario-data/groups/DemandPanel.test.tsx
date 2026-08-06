import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useDemand: vi.fn() }));
import { useDemand } from "@/hooks/useScenarioProjection";
import { DemandPanel } from "./DemandPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "DemandPanel", caption: "Demand", Panel: DemandPanel, hook: vi.mocked(useDemand), columnHeaders: 7, expected: "headcount", data: { items: [{ record_id: "d1", family: "outbound", task_id: "task-1", area_id: null, start_minute: 480, end_minute: 540, amount: 4, unit: "headcount" }] } });
