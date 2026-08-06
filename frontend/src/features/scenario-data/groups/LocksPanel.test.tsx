import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useLocks: vi.fn() }));
import { useLocks } from "@/hooks/useScenarioProjection";
import { LocksPanel } from "./LocksPanel";
import { panelTestContract } from "./panelTestContract";
panelTestContract({ name: "LocksPanel", caption: "Locks", Panel: LocksPanel, hook: vi.mocked(useLocks), columnHeaders: 5, expected: "manual", data: { items: [{ record_id: "l1", target_type: "worker", target_ref: "worker-1", scope: "shift", source: "manual" }] } });
