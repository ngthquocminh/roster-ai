import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useSession", () => ({
  useSession: vi.fn(),
  useSignOut: vi.fn(),
}));
vi.mock("@/hooks/useFixtureCatalogue", () => ({
  useFixtureCatalogue: vi.fn(),
}));
vi.mock("@/hooks/useScenarioContext", () => ({
  useScenarioContext: vi.fn(),
}));
vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(), useWorkAreasAndTasks: vi.fn(), useWorkers: vi.fn(),
  useDemand: vi.fn(), useBaselineAssignments: vi.fn(), useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
}));

import { routes } from "@/App";
import { RootErrorBoundary } from "@/components/layout/RootErrorBoundary";
import { useFixtureCatalogue } from "@/hooks/useFixtureCatalogue";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import * as projectionHooks from "@/hooks/useScenarioProjection";
import { useSession, useSignOut } from "@/hooks/useSession";


const mockUseSession = useSession as unknown as ReturnType<typeof vi.fn>;
const mockUseSignOut = useSignOut as unknown as ReturnType<typeof vi.fn>;
const mockCatalogue =
  useFixtureCatalogue as unknown as ReturnType<typeof vi.fn>;
const mockContext =
  useScenarioContext as unknown as ReturnType<typeof vi.fn>;
const scenarioId = "11111111-1111-4111-8111-111111111111";

beforeEach(() => {
  mockUseSession.mockReturnValue({
    data: {
      app_user_id: "00000000-0000-0000-0000-000000000001",
      site_id: "00000000-0000-0000-0000-000000000002",
      csrf_token: "csrf",
      expires_at: "2030-01-01T00:00:00Z",
    },
    isPending: false,
    isError: false,
  });
  mockUseSignOut.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({
      postLogoutRedirectUrl: null,
    }),
    isPending: false,
  });
  mockCatalogue.mockReturnValue({
    data: [],
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });
  mockContext.mockReturnValue({
    data: {
      schema_version: "v1",
      scenario_name: "Fixture A",
      scenario_id: scenarioId,
      fixture_version: "v1",
      checksum_algorithm: "sha256",
      checksum_schema_version: "rfc8785-v1",
      checksum_digest: "a".repeat(64),
      site_id: "00000000-0000-0000-0000-000000000002",
      baseline_schedule_version: null,
    },
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });
  const empty = { data: { items: [] }, error: null, isError: false, isPending: false, refetch: vi.fn() };
  vi.mocked(projectionHooks.useScenarioOverview).mockReturnValue({
    data: { scenario_name: "Fixture A", scenario_id: scenarioId, fixture_version: "v1", baseline_schedule_version: null, horizon_start: "2026-01-01T00:00:00Z", horizon_minutes: 1440, site_timezone: "UTC", projection_generated_at: "2026-01-01T01:00:00Z", work_area_count: 1, task_count: 2, worker_count: 3, demand_interval_count: 4, baseline_assignment_count: 0, lock_count: 0, constraint_count: 5 },
    error: null, isError: false, isPending: false, refetch: vi.fn(),
  } as never);
  vi.mocked(projectionHooks.useWorkAreasAndTasks).mockReturnValue(empty as never);
  vi.mocked(projectionHooks.useWorkers).mockReturnValue(empty as never);
  vi.mocked(projectionHooks.useDemand).mockReturnValue(empty as never);
  vi.mocked(projectionHooks.useBaselineAssignments).mockReturnValue(empty as never);
  vi.mocked(projectionHooks.useLocks).mockReturnValue(empty as never);
  vi.mocked(projectionHooks.useConstraintsAndObjectives).mockReturnValue(empty as never);
});

function renderAt(path: string) {
  const memoryRouter = createMemoryRouter(routes, {
    initialEntries: [path],
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={memoryRouter} />
    </QueryClientProvider>,
  );
  return { ...rendered, memoryRouter };
}

describe("governed route tree", () => {
  it("redirects an unauthenticated deep link to /signin with return_to", async () => {
    mockUseSession.mockReturnValue({
      data: null,
      isPending: false,
      isError: false,
    });

    const { memoryRouter } = renderAt(`/scenarios/${scenarioId}`);

    await waitFor(() =>
      expect(memoryRouter.state.location.pathname).toBe("/signin"),
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      `http://localhost:5173/api/v1/auth/login?return_to=%2Fscenarios%2F${scenarioId}`,
    );
  });

  it("does not bounce an authenticated user on a transient session-check error", () => {
    mockUseSession.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
    });

    const { memoryRouter } = renderAt(`/scenarios/${scenarioId}`);

    expect(screen.getByText("Couldn't load this content.")).toBeInTheDocument();
    expect(memoryRouter.state.location.pathname).toBe(
      `/scenarios/${scenarioId}`,
    );
  });

  it("mounts the fixture catalogue at /", () => {
    renderAt("/");

    expect(
      screen.getByRole("heading", { name: "Fixture catalogue" }),
    ).toBeInTheDocument();
  });

  it("mounts the scenario workspace at /scenarios/:scenarioId", () => {
    renderAt(`/scenarios/${scenarioId}`);

    expect(
      screen.getByRole("heading", { name: "Fixture A" }),
    ).toBeInTheDocument();
    expect(screen.getByText(scenarioId)).toBeInTheDocument();
    expect(mockContext).toHaveBeenCalledWith(scenarioId);
  });

  it("mounts Scenario Data and the Runs/Results peer routes", () => {
    let rendered = renderAt(`/scenarios/${scenarioId}/data`);
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Overview", { selector: "caption" })).toBeInTheDocument();
    rendered.unmount();

    rendered = renderAt(`/scenarios/${scenarioId}/runs`);
    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    rendered.unmount();

    rendered = renderAt(`/scenarios/${scenarioId}/runs/run-1`);
    expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
    rendered.unmount();
  });

  it("keeps the persistent app bar on both governed routes", () => {
    for (const path of ["/", `/scenarios/${scenarioId}`]) {
      const { unmount } = renderAt(path);
      expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
        "href",
        "/",
      );
      unmount();
    }
  });

  it("routes unknown paths to RootErrorBoundary", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const path of ["/nope"]) {
      const { unmount } = renderAt(path);
      expect(
        screen.getByRole("heading", { name: "Something went wrong." }),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Reload the page and try again."),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Reload" }),
      ).toBeInTheDocument();
      expect(screen.queryByText(/browser console/i)).not.toBeInTheDocument();
      unmount();
    }
    vi.restoreAllMocks();
  });
});

/**
 * RootErrorBoundary still ships and has no test file of its own, so this is
 * its only coverage — the assertions below are kept whole rather than
 * trimmed to the heading. None of them depend on the retired legacy routes.
 */
describe("route crash backstop", () => {
  it("renders RootErrorBoundary without diagnostics when a child throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    function Throws(): never {
      throw new Error(
        "RuntimeError: boom — simulated render crash at C:\\srv\\backend\\api\\main.py",
      );
    }
    const router = createMemoryRouter(
      [
        {
          path: "/",
          Component: Throws,
          errorElement: <RootErrorBoundary />,
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);

    expect(
      screen.getByRole("heading", { name: "Something went wrong." }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reload the page and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.queryByText(/RuntimeError/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/boom — simulated render crash/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/main\.py/)).not.toBeInTheDocument();
    expect(screen.queryByText(/browser console/i)).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
