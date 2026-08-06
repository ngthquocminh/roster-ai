import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useConstraintsAndObjectives: vi.fn() }));
import { useConstraintsAndObjectives } from "@/hooks/useScenarioProjection";
import { ConstraintsPanel } from "./ConstraintsPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "ConstraintsPanel", caption: "Constraints and objectives", Panel: ConstraintsPanel, hook: vi.mocked(useConstraintsAndObjectives), columnHeaders: 4, expected: "max_hours", data: { items: [{ record_id: "c1", constraint_type: "max_hours", value: "8", value_type: "number" }] } });
