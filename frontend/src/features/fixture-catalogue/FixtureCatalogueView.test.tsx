import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { FixtureCatalogueView } from "./FixtureCatalogueView";


const entry = {
  schema_version: "v1",
  scenario_id: "11111111-1111-4111-8111-111111111111",
  fixture_id: "fixture-a",
  scenario_name: "Fixture A",
  scenario_version_id: "22222222-2222-4222-8222-222222222222",
  fixture_version: "v1",
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  imported_at: "2026-07-24T09:30:00Z",
  site_id: "33333333-3333-4333-8333-333333333333",
};

// Deliberately sorts BEFORE `entry` alphabetically while the server returns it
// second, so any client-side re-sort (or a reversed map) changes the rendered
// order and fails the ordering test below.
const earlierByName = {
  ...entry,
  scenario_id: "44444444-4444-4444-8444-444444444444",
  fixture_id: "fixture-b",
  scenario_name: "Alpha Fixture",
  scenario_version_id: "55555555-5555-4555-8555-555555555555",
  fixture_version: "v2",
  imported_at: "2026-07-25T11:00:00Z",
};

function renderView(
  props: Partial<React.ComponentProps<typeof FixtureCatalogueView>> = {},
) {
  const onRetry = vi.fn();
  const utils = render(
    <MemoryRouter>
      <FixtureCatalogueView
        data={undefined}
        isError={false}
        isPending={false}
        onRetry={onRetry}
        {...props}
      />
    </MemoryRouter>,
  );
  return { ...utils, onRetry };
}

describe("FixtureCatalogueView", () => {
  it("renders skeleton rows and the required cold-loading copy", () => {
    const { container } = renderView({ isPending: true });

    expect(screen.getByText("Loading predefined scenarios…")).toBeInTheDocument();
    // Exactly 3 rows x 4 columns. A regression collapsing the skeleton to a
    // single bar previously passed a `> 0` assertion.
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(12);
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  });

  it("renders the bounded empty state without a creation action", () => {
    renderView({ data: [] });

    expect(
      screen.getByText("No predefined scenarios are available."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders the safe unavailable copy and retries", () => {
    const { onRetry } = renderView({ isError: true });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Couldn't load this content.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("keeps cached rows visible with the required stale label and retry", () => {
    renderView({ data: [entry], isError: true });

    expect(
      screen.getByText("Saved catalogue — refresh unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fixture A" })).toHaveAttribute(
      "href",
      `/scenarios/${entry.scenario_id}`,
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("preserves the server-defined row order rather than sorting client-side", () => {
    renderView({ data: [entry, earlierByName] });

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    // rows[0] is the header row.
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByRole("link")).toHaveTextContent("Fixture A");
    expect(within(rows[2]).getByRole("link")).toHaveTextContent("Alpha Fixture");
  });

  it("renders one real scenario link per row", () => {
    renderView({ data: [entry, earlierByName] });

    expect(
      screen.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual([
      `/scenarios/${entry.scenario_id}`,
      `/scenarios/${earlierByName.scenario_id}`,
    ]);
  });

  it("renders a semantic table with the specified columns", () => {
    renderView({ data: [entry] });

    expect(screen.getByRole("table")).toHaveAccessibleName(
      "Predefined scenario fixture versions",
    );
    expect(
      screen.getAllByRole("columnheader").map((header) => [
        header.textContent,
        header.getAttribute("scope"),
      ]),
    ).toEqual([
      ["Scenario name", "col"],
      ["Scenario ID", "col"],
      ["Fixture version", "col"],
      ["Imported at", "col"],
    ]);
    expect(screen.getByText("2026-07-24 09:30")).toBeInTheDocument();
  });

  it("exposes no mutation affordance of any kind in the loaded table", () => {
    const { container } = renderView({ data: [entry, earlierByName] });

    // Enumerate what IS present rather than probing for a guessed set of
    // labels: the previous regex matched none of the controls the story
    // actually forbids ("New Scenario", "+", an overflow menu), so inserting
    // one left every test green.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(
      screen.getAllByRole("link").map((link) => link.textContent),
    ).toEqual(["Fixture A", "Alpha Fixture"]);
    expect(
      container.querySelectorAll("input, select, textarea, form"),
    ).toHaveLength(0);
    expect(container.querySelectorAll("[contenteditable]")).toHaveLength(0);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryAllByRole("menu")).toHaveLength(0);
    expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
  });

  it("marks skeletons so animation is suppressed under reduced motion", () => {
    const { container } = renderView({ isPending: true });

    const skeletons = Array.from(
      container.querySelectorAll('[data-slot="skeleton"]'),
    );
    expect(skeletons).toHaveLength(12);
    for (const skeleton of skeletons) {
      expect(skeleton).toHaveClass("motion-reduce:animate-none");
    }
  });

  it("keeps the status region mounted across state changes so updates announce", () => {
    const { container, rerender } = renderView({ isPending: true });

    const region = container.querySelector('[aria-live="polite"]');
    expect(region).not.toBeNull();
    expect(region).toHaveAttribute("aria-busy", "true");

    rerender(
      <MemoryRouter>
        <FixtureCatalogueView
          data={[entry]}
          isError={false}
          isPending={false}
          onRetry={vi.fn()}
        />
      </MemoryRouter>,
    );

    // Same DOM node, mutated content — a replaced region announces nothing.
    expect(container.querySelector('[aria-live="polite"]')).toBe(region);
    expect(region).toHaveAttribute("aria-busy", "false");
  });
});
