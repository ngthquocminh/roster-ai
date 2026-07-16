import { createBrowserRouter, Outlet, type RouteObject } from "react-router";

import { AppBar } from "@/components/layout/AppBar";
import { RootErrorBoundary } from "@/components/layout/RootErrorBoundary";
import { EditorPlaceholder } from "@/routes/EditorPlaceholder";
import { Home } from "@/routes/Home";
import { ResultsPlaceholder } from "@/routes/ResultsPlaceholder";
import { RunsPlaceholder } from "@/routes/RunsPlaceholder";
import { ScenarioLayout } from "@/routes/ScenarioLayout";

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
 * SHELL-03's four-route shell, exactly per UI-SPEC's Application Structure
 * route table: `/`, `/scenarios/:scenarioId`, `/scenarios/:scenarioId/runs`,
 * `/scenarios/:scenarioId/runs/:runId`. Editor sits at ScenarioLayout's
 * *index* route, not a `/editor` segment UI-SPEC never specified.
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
    path: "/",
    Component: RootLayout,
    errorElement: <RootErrorBoundary />,
    children: [
      { index: true, Component: Home },
      {
        path: "scenarios/:scenarioId",
        Component: ScenarioLayout,
        children: [
          { index: true, Component: EditorPlaceholder },
          { path: "runs", Component: RunsPlaceholder },
          { path: "runs/:runId", Component: ResultsPlaceholder },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
