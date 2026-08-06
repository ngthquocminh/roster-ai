import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({ useScenarioOverview: vi.fn() }));
import { useScenarioOverview } from "@/hooks/useScenarioProjection";
import { OverviewPanel } from "./OverviewPanel";
import { panelTestContract } from "./panelTestContract";

panelTestContract({ name: "OverviewPanel", caption: "Overview", Panel: OverviewPanel, hook: vi.mocked(useScenarioOverview), emptyData: null, columnHeaders: 0, expected: "Fixture A", data: { scenario_name: "Fixture A", scenario_id: "scenario-a", fixture_version: "v1", baseline_schedule_version: null, horizon_start: "2026-01-01T00:00:00Z", horizon_minutes: 1440, site_timezone: "UTC", projection_generated_at: "2026-01-01T01:00:00Z", work_area_count: 1, task_count: 2, worker_count: 3, demand_interval_count: 4, baseline_assignment_count: 0, lock_count: 0, constraint_count: 5 } });
