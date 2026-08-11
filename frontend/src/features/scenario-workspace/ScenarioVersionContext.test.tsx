import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";

import { ScenarioVersionContext } from "./ScenarioVersionContext";


const context = {
  schema_version: "v1",
  scenario_name: "Fixture A",
  scenario_id: "11111111-1111-4111-8111-111111111111",
  scenario_version_id: "33333333-3333-4333-8333-333333333333",
  fixture_version: "v1",
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  site_id: "22222222-2222-4222-8222-222222222222",
  baseline_schedule_version: null,
};

it("renders and focuses all four persistent context fields", async () => {
  render(
    <MemoryRouter>
      <ScenarioVersionContext context={context} />
    </MemoryRouter>,
  );

  const heading = screen.getByRole("heading", { name: "Fixture A" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(screen.getByText(context.scenario_id)).toHaveClass("font-mono");
  expect(screen.getByText(context.scenario_id)).toHaveClass("break-all");
  expect(screen.getByText(context.scenario_id)).toHaveAttribute(
    "title",
    context.scenario_id,
  );
  expect(screen.getByText("v1")).toHaveClass("font-mono");
  expect(screen.getByText("Not established")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Change scenario" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(screen.getByRole("link", { name: "Change scenario" })).toHaveClass(
    "min-h-11",
    "focus-visible:ring-3",
  );
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

it("renders an established baseline literally when one becomes available", () => {
  render(
    <MemoryRouter>
      <ScenarioVersionContext
        context={{ ...context, baseline_schedule_version: "baseline-7" }}
      />
    </MemoryRouter>,
  );

  expect(screen.getByText("baseline-7")).toHaveClass("font-mono");
  expect(screen.queryByText("Not established")).not.toBeInTheDocument();
});
