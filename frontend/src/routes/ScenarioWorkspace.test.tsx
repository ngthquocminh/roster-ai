import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
} from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioContext", () => ({
  useScenarioContext: vi.fn(),
}));

import { useScenarioContext } from "@/hooks/useScenarioContext";
import { ScenarioWorkspace } from "./ScenarioWorkspace";


const mockContext =
  useScenarioContext as unknown as ReturnType<typeof vi.fn>;
const scenarioId = "11111111-1111-4111-8111-111111111111";
const context = {
  schema_version: "v1",
  scenario_name: "Fixture A",
  scenario_id: scenarioId,
  fixture_version: "v1",
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  site_id: "22222222-2222-4222-8222-222222222222",
  baseline_schedule_version: null,
};

function renderWorkspace() {
  const router = createMemoryRouter(
    [
      {
        path: "/scenarios/:scenarioId",
        Component: ScenarioWorkspace,
      },
    ],
    { initialEntries: [`/scenarios/${scenarioId}`] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  mockContext.mockReset();
});

it("renders persistent context and only the literal next-surface placeholder", () => {
  mockContext.mockReturnValue({
    data: context,
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  expect(screen.getByRole("heading", { name: "Fixture A" })).toBeInTheDocument();
  expect(
    screen.getByText("Scenario Data will be available in this workspace."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  expect(screen.queryByText("Chat")).not.toBeInTheDocument();
  expect(screen.queryByText("Runs")).not.toBeInTheDocument();
  expect(screen.queryByText("Results")).not.toBeInTheDocument();
});

it("renders and focuses a terminal, non-disclosing not-found view", async () => {
  mockContext.mockReturnValue({
    data: undefined,
    error: { status: 404, detail: "Secret fixture" },
    isError: true,
    isPending: false,
    refetch: vi.fn(),
  });

  renderWorkspace();

  const heading = screen.getByRole("heading", { name: "Scenario not found" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(screen.queryByText("Secret fixture")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to catalogue" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(
    screen.getByRole("link", { name: "Return to catalogue" }),
  ).toHaveClass("min-h-11", "focus-visible:ring-3");
});

it("renders safe retry behavior for non-404 failures", () => {
  const refetch = vi.fn();
  mockContext.mockReturnValue({
    data: undefined,
    error: new Error("database internals"),
    isError: true,
    isPending: false,
    refetch,
  });

  renderWorkspace();

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Couldn't load this content.",
  );
  expect(screen.queryByText("database internals")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalledOnce();
});
