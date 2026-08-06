import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";

import { WorkspaceTabs } from "./WorkspaceTabs";

const scenarioId = "scenario-a";

it("renders ordered real routes, active semantics, and an explained disabled result", () => {
  render(
    <MemoryRouter initialEntries={[`/scenarios/${scenarioId}/data`]}>
      <WorkspaceTabs scenarioId={scenarioId} />
    </MemoryRouter>,
  );

  const navigation = screen.getByRole("navigation", { name: "Scenario workspace" });
  expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Chat",
    "Scenario Data",
    "Runs",
  ]);
  expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", `/scenarios/${scenarioId}`);
  const active = screen.getByRole("link", { name: "Scenario Data" });
  expect(active).toHaveAttribute("href", `/scenarios/${scenarioId}/data`);
  expect(active).toHaveAttribute("aria-current", "page");
  expect(active).toHaveClass("border-primary", "text-primary");
  expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("href", `/scenarios/${scenarioId}/runs`);
  expect(within(navigation).queryByRole("link", { name: "Results" })).not.toBeInTheDocument();
  expect(within(navigation).queryByRole("button", { name: "Results" })).not.toBeInTheDocument();
  expect(screen.getByText("Results", { selector: "[aria-disabled='true']" })).toBeInTheDocument();
  expect(screen.getByText("Results unavailable: select a run.")).toBeVisible();
});
