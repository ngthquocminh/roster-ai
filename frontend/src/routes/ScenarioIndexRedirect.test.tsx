import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { expect, it } from "vitest";

import { ScenarioIndexRedirect } from "./ScenarioIndexRedirect";

const SCENARIO = "33333333-3333-3333-3333-333333333333";

function DataProbe() {
  const location = useLocation();
  return <p>Data {location.search} {JSON.stringify(location.state)}</p>;
}

it("sends the old Chat URL to Scenario Data, keeping the search and history state", () => {
  const router = createMemoryRouter(
    [
      {
        path: "/scenarios/:scenarioId",
        children: [
          { index: true, Component: ScenarioIndexRedirect },
          { path: "data", Component: DataProbe },
        ],
      },
    ],
    {
      initialEntries: [
        { pathname: `/scenarios/${SCENARIO}`, search: "?conversation=c1", state: { evidenceOrigin: "o" } },
      ],
    },
  );

  render(<RouterProvider router={router} />);

  // Return to claim lands here: the conversation and the evidence origin must
  // both reach the chat panel.
  expect(router.state.location.pathname).toBe(`/scenarios/${SCENARIO}/data`);
  expect(screen.getByText(`Data ?conversation=c1 {"evidenceOrigin":"o"}`)).toBeInTheDocument();
});
