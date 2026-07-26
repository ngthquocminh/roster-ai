import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";

vi.mock("@/hooks/useSession", () => ({
  useSession: vi.fn(),
  useSignOut: vi.fn(),
}));

import { routes } from "@/App";
import { RootErrorBoundary } from "@/components/layout/RootErrorBoundary";
import { useSession, useSignOut } from "@/hooks/useSession";


const mockUseSession = useSession as unknown as ReturnType<typeof vi.fn>;
const mockUseSignOut = useSignOut as unknown as ReturnType<typeof vi.fn>;

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
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  });
});

/**
 * SHELL-03 coverage: proves the four-route shell deep-links correctly and
 * that the persistent two-tier nav (app bar + scenario tab nav) mounts on
 * the right routes with the right tab marked active.
 *
 * Builds a `createMemoryRouter` from the exact same `routes` config `App.tsx`
 * ships (not a hand-duplicated test-only tree) — so a route-ranking bug in
 * production would fail here too, not just in a copy.
 *
 * Wrapped in a fresh `QueryClientProvider` per render (plan 01-06 added):
 * `Home` now mounts `ScenarioTable`, which calls `useScenarios()`. In the
 * real app `main.tsx` provides this above the router; this test builds its
 * own router directly, so it needs the same provider or `useQuery` throws.
 * A real (unmocked) `listScenarios()` call is expected to reject in jsdom
 * (no backend, no `fetch`) — these tests never assert on the resulting
 * error/loading UI, only on nav/shell chrome that renders regardless.
 */
function renderAt(path: string) {
  const memoryRouter = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={memoryRouter} />
    </QueryClientProvider>,
  );
}

describe("router: four-route shell (SHELL-03)", () => {
  it("redirects an unauthenticated deep link to /signin", async () => {
    mockUseSession.mockReturnValue({
      data: null,
      isPending: false,
      isError: false,
    });
    const memoryRouter = createMemoryRouter(routes, {
      initialEntries: ["/scenarios/abc123/runs"],
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={memoryRouter} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(memoryRouter.state.location.pathname).toBe("/signin"));
    expect(
      screen.getByRole("link", { name: "Sign in" }),
    ).toHaveAttribute("href", "http://localhost:5173/api/v1/auth/login");
  });

  it("mounts Home at /", () => {
    renderAt("/");
    expect(
      screen.getByRole("heading", { name: "Scenarios" }),
    ).toBeInTheDocument();
  });

  it("mounts the Editor at /scenarios/:scenarioId (index)", () => {
    // `@/api/scenarios` is intentionally unmocked here (see file header
    // comment) — the real `getScenario` fetch has nowhere to resolve in
    // jsdom, so the assertion targets the synchronous initial-render state
    // (`useScenario`'s query is `isLoading` before the fetch ever settles),
    // not a later success/error outcome. Full Editor behavior (populated,
    // 404-gate, transcript) is covered by `Editor.test.tsx`.
    renderAt("/scenarios/abc123");
    expect(screen.getByText("Loading scenario…")).toBeInTheDocument();
  });

  it("mounts the real RunHistory view at /scenarios/:scenarioId/runs — not the Editor index with scenarioId 'runs' [edge: SHELL-03/precision]", () => {
    renderAt("/scenarios/abc123/runs");
    expect(
      screen.getByRole("heading", { name: "Run History" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Run Scenario" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Loading scenario…"),
    ).not.toBeInTheDocument();
    // Route ranking has teeth: no element anywhere renders a scenarioId of
    // "runs" — the only place the word "runs" may legitimately appear is the
    // "Runs" tab label and the "Run History" heading already asserted above,
    // never a literal id value.
    expect(screen.queryByText(/scenarioId.*runs/i)).not.toBeInTheDocument();
  });

  it("mounts the real ResultsView at /scenarios/:scenarioId/runs/:runId", () => {
    // `@/hooks/useRun` is intentionally unmocked here (matching the Editor
    // and RunHistory route tests above) — the real `getRun` fetch has
    // nowhere to resolve in jsdom, so the assertion targets ResultsView's
    // synchronous initial-render state (`useRun`'s query is `isLoading`
    // before the fetch ever settles), not a later branch. Full ResultsView
    // branching (D-12 status gate, RES-05 isolation) is covered by
    // ResultsView.test.tsx.
    renderAt("/scenarios/abc123/runs/run789");
    expect(screen.getByText("Loading run…")).toBeInTheDocument();
  });

  it("renders the app bar with a link to / on all four routes", () => {
    for (const path of [
      "/",
      "/scenarios/abc123",
      "/scenarios/abc123/runs",
      "/scenarios/abc123/runs/run789",
    ]) {
      const { unmount } = renderAt(path);
      const homeLink = screen.getByRole("link", { name: "Home" });
      expect(homeLink).toHaveAttribute("href", "/");
      unmount();
    }
  });

  it("renders the three-tab nav on all three /scenarios/:scenarioId/* routes and not on /", () => {
    renderAt("/");
    expect(
      screen.queryByRole("navigation", { name: "Scenario views" }),
    ).not.toBeInTheDocument();

    for (const path of [
      "/scenarios/abc123",
      "/scenarios/abc123/runs",
      "/scenarios/abc123/runs/run789",
    ]) {
      const { unmount } = renderAt(path);
      expect(
        screen.getByRole("navigation", { name: "Scenario views" }),
      ).toBeInTheDocument();
      unmount();
    }
  });

  it("marks the Editor tab active on /scenarios/:scenarioId and no other tab", () => {
    renderAt("/scenarios/abc123");
    expect(screen.getByRole("link", { name: "Editor" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("link", { name: "Runs" }),
    ).not.toHaveAttribute("aria-current");
    expect(
      screen.getByRole("button", { name: "Results" }),
    ).not.toHaveAttribute("aria-current");
  });

  it("marks the Runs tab active on /scenarios/:scenarioId/runs and NOT the Editor tab", () => {
    renderAt("/scenarios/abc123/runs");
    expect(
      screen.getByRole("link", { name: "Editor" }),
    ).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks the (disabled) Results tab active on /scenarios/:scenarioId/runs/:runId", () => {
    renderAt("/scenarios/abc123/runs/run789");
    expect(
      screen.getByRole("link", { name: "Editor" }),
    ).not.toHaveAttribute("aria-current");
    expect(
      screen.getByRole("link", { name: "Runs" }),
    ).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "Results" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

});

/**
 * SHELL-04 coverage: the crash backstop. One `errorElement` wiring on the
 * root route covers both an unmatched URL and a render exception anywhere
 * below the root — react-router surfaces a no-match as a route error, so
 * both land on RootErrorBoundary rather than a blank screen.
 */
describe("router: crash backstop (SHELL-04)", () => {
  it("renders RootErrorBoundary's heading, body, and Reload button on an undeclared path [edge: SHELL-03/boundary]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderAt("/nope");

    expect(
      screen.getByRole("heading", { name: "Something went wrong." }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reload the page and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.queryByText(/browser console/i)).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders RootErrorBoundary, not a white screen, when a child route component throws during render", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    function Throws(): never {
      throw new Error(
        "RuntimeError: boom — simulated render crash at C:\\srv\\backend\\api\\main.py",
      );
    }

    const throwRouter = createMemoryRouter(
      [
        {
          path: "/",
          Component: Throws,
          errorElement: <RootErrorBoundary />,
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={throwRouter} />);

    expect(
      screen.getByRole("heading", { name: "Something went wrong." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Reload the page and try again.")).toBeInTheDocument();
    expect(screen.queryByText(/RuntimeError/)).not.toBeInTheDocument();
    expect(screen.queryByText(/boom — simulated render crash/)).not.toBeInTheDocument();
    expect(screen.queryByText(/main\.py/)).not.toBeInTheDocument();
    expect(screen.queryByText(/browser console/i)).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
