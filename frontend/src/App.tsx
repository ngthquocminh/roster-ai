import { createBrowserRouter, Outlet, type RouteObject } from "react-router";

import { AppBar } from "@/components/layout/AppBar";
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
 * NOTE: the root route's `errorElement` (crash backstop + unmatched-URL
 * catch, SHELL-04) is wired in plan 01-05's Task 2 once RootErrorBoundary
 * exists — not yet present in this Task 1 commit.
 */
export const routes: RouteObject[] = [
  {
    path: "/",
    Component: RootLayout,
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
