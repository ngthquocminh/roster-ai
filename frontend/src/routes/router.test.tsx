import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { routes } from "@/App";
import { RootErrorBoundary } from "@/components/layout/RootErrorBoundary";

/**
 * SHELL-03 coverage: proves the four-route shell deep-links correctly and
 * that the persistent two-tier nav (app bar + scenario tab nav) mounts on
 * the right routes with the right tab marked active.
 *
 * Builds a `createMemoryRouter` from the exact same `routes` config `App.tsx`
 * ships (not a hand-duplicated test-only tree) — so a route-ranking bug in
 * production would fail here too, not just in a copy.
 */
function renderAt(path: string) {
  const memoryRouter = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={memoryRouter} />);
}

describe("router: four-route shell (SHELL-03)", () => {
  it("mounts Home at /", () => {
    renderAt("/");
    expect(
      screen.getByRole("heading", { name: "Scenarios" }),
    ).toBeInTheDocument();
  });

  it("mounts the Editor placeholder at /scenarios/:scenarioId (index)", () => {
    renderAt("/scenarios/abc123");
    expect(
      screen.getByRole("heading", { name: /Editor — not built yet/ }),
    ).toBeInTheDocument();
  });

  it("mounts the Runs placeholder at /scenarios/:scenarioId/runs — not the Editor index with scenarioId 'runs' [edge: SHELL-03/precision]", () => {
    renderAt("/scenarios/abc123/runs");
    expect(
      screen.getByRole("heading", { name: /Runs — not built yet/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: /Editor — not built yet/ }),
    ).not.toBeInTheDocument();
    // Route ranking has teeth: no element anywhere renders a scenarioId of
    // "runs" — the only place the word "runs" may legitimately appear is the
    // "Runs" tab label and the "Runs — not built yet" heading already
    // asserted above, never a literal id value.
    expect(screen.queryByText(/scenarioId.*runs/i)).not.toBeInTheDocument();
  });

  it("mounts the Results placeholder at /scenarios/:scenarioId/runs/:runId", () => {
    renderAt("/scenarios/abc123/runs/run789");
    expect(
      screen.getByRole("heading", { name: /Results — not built yet/ }),
    ).toBeInTheDocument();
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

  it("each placeholder renders the UI-SPEC honest-not-built-yet copy with no mock data", () => {
    renderAt("/scenarios/abc123");
    expect(
      screen.getByText("This view ships in a later phase of the v0.4 milestone."),
    ).toBeInTheDocument();
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
      screen.getByText(
        "Reload the page. If this keeps happening, check the browser console.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders RootErrorBoundary, not a white screen, when a child route component throws during render", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    function Throws(): never {
      throw new Error("boom — simulated render crash");
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
    expect(screen.queryByText(/boom — simulated render crash/)).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
