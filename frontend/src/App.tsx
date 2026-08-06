import { createBrowserRouter, Outlet, type RouteObject } from "react-router";

import { AppBar } from "@/components/layout/AppBar";
import { RootErrorBoundary } from "@/components/layout/RootErrorBoundary";
import { FixtureCatalogue } from "@/routes/FixtureCatalogue";
import { RequireSession } from "@/routes/RequireSession";
import { ScenarioChat } from "@/routes/ScenarioChat";
import { ScenarioData } from "@/routes/ScenarioData";
import { ScenarioResults } from "@/routes/ScenarioResults";
import { ScenarioRuns } from "@/routes/ScenarioRuns";
import { ScenarioWorkspace } from "@/routes/ScenarioWorkspace";
import { SignIn } from "@/routes/SignIn";

/**
 * Persistent global app bar (UI-SPEC tier 1 nav) + an `Outlet` for whichever
 * top-level view is active. Mounted as the root route's component.
 */
function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <AppBar />
      <Outlet />
    </div>
  );
}

/**
 * Governed planner route tree: the fixture catalogue at `/` and one
 * immutable scenario workspace at `/scenarios/:scenarioId`.
 *
 * Exported as a plain route-config array (rather than only the constructed
 * browser router) so `router.test.tsx` can build a `createMemoryRouter`
 * against the exact same route tree the app ships — deep-link tests then
 * prove real route ranking instead of a hand-duplicated test-only config
 * that could silently drift from what actually ships.
 *
 * The root route's crash-backstop wiring below covers two distinct failures
 * at once: a render exception anywhere below the root, and an unmatched URL
 * (react-router surfaces a no-match as a route error) — without it, an
 * unknown path renders react-router's own default error page, a
 * developer-facing artifact that violates SHELL-04.
 */
export const routes: RouteObject[] = [
  {
    path: "/signin",
    Component: SignIn,
    errorElement: <RootErrorBoundary />,
  },
  {
    Component: RequireSession,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        path: "/",
        Component: RootLayout,
        errorElement: <RootErrorBoundary />,
        children: [
          { index: true, Component: FixtureCatalogue },
          {
            path: "scenarios/:scenarioId",
            Component: ScenarioWorkspace,
            children: [
              { index: true, Component: ScenarioChat },
              { path: "data", Component: ScenarioData },
              { path: "runs", Component: ScenarioRuns },
              { path: "runs/:runId", Component: ScenarioResults },
            ],
          },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
