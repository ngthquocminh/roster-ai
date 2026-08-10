import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { expect, it, vi } from "vitest";

vi.mock("@/features/chat/ChatView", () => ({
  ChatView: ({ scenarioId }: { scenarioId: string }) => (
    <p>Chat for {scenarioId}</p>
  ),
}));

import { ScenarioChat } from "./ScenarioChat";

const SCENARIO = "33333333-3333-3333-3333-333333333333";

it("deep-links to a scenario and renders Chat with the route's scenario id", () => {
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId", Component: ScenarioChat }],
    { initialEntries: [`/scenarios/${SCENARIO}`] },
  );

  render(<RouterProvider router={router} />);

  // The workspace index route is Chat; this asserts the wiring the workspace
  // test deliberately stubs out.
  expect(screen.getByText(`Chat for ${SCENARIO}`)).toBeInTheDocument();
});
