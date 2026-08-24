import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioContext", () => ({ useScenarioContext: vi.fn() }));
vi.mock("@/api/scheduleRuns");

import { getScheduleRunResult } from "@/api/scheduleRuns";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { ScenarioResults } from "./ScenarioResults";
import { ScenarioWorkspace } from "./ScenarioWorkspace";

const scenarioId = "11111111-1111-4111-8111-111111111111";
const runId = "22222222-2222-4222-8222-222222222222";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useScenarioContext).mockReturnValue({
    data: {
      schema_version: "v1", scenario_name: "Fixture A", scenario_id: scenarioId,
      scenario_version_id: "33333333-3333-4333-8333-333333333333",
      fixture_version: "v1", checksum_algorithm: "sha256",
      checksum_schema_version: "rfc8785-v1", checksum_digest: "a".repeat(64),
      site_id: "44444444-4444-4444-8444-444444444444", baseline_schedule_version: null,
    }, error: null, isError: false, isPending: false, refetch: vi.fn(),
  } as never);
});

it("keeps the workspace shell and peer tabs available when Results fetch fails", async () => {
  vi.mocked(getScheduleRunResult).mockRejectedValue({ status: 500 });
  const router = createMemoryRouter([{
    path: "/scenarios/:scenarioId", Component: ScenarioWorkspace,
    children: [{ path: "runs/:runId", Component: ScenarioResults }],
  }], { initialEntries: [`/scenarios/${scenarioId}/runs/${runId}`] });

  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);

  expect(await screen.findByText("Couldn't load this content.")).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Scenario workspace" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", `/scenarios/${scenarioId}`);
  expect(screen.getByRole("link", { name: "Scenario Data" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Runs" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Fixture A" })).toBeInTheDocument();
});
