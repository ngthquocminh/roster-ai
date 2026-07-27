import { fireEvent, render, screen } from "@testing-library/react";
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

function renderView(
  props: Partial<React.ComponentProps<typeof FixtureCatalogueView>> = {},
) {
  const onRetry = vi.fn();
  render(
    <MemoryRouter>
      <FixtureCatalogueView
        data={undefined}
        error={null}
        isError={false}
        isPending={false}
        onRetry={onRetry}
        {...props}
      />
    </MemoryRouter>,
  );
  return onRetry;
}

describe("FixtureCatalogueView", () => {
  it("renders skeleton rows and the required cold-loading copy", () => {
    const { container } = render(
      <MemoryRouter>
        <FixtureCatalogueView
          data={undefined}
          error={null}
          isError={false}
          isPending
          onRetry={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Loading predefined scenarios…")).toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("renders the bounded empty state without a creation action", () => {
    renderView({ data: [] });

    expect(
      screen.getByText("No predefined scenarios are available."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders safe unavailable copy and retries without exposing diagnostics", () => {
    const onRetry = renderView({
      error: new Error("database password at C:\\secret"),
      isError: true,
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Couldn't load this content.",
    );
    expect(screen.queryByText(/database password/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("keeps cached rows visible with the required stale label and retry", () => {
    renderView({
      data: [entry],
      error: new Error("offline"),
      isError: true,
    });

    expect(
      screen.getByText("Saved catalogue — refresh unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fixture A" })).toHaveAttribute(
      "href",
      `/scenarios/${entry.scenario_id}`,
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("renders an ordered semantic table of real scenario links only", () => {
    const { container } = render(
      <MemoryRouter>
        <FixtureCatalogueView
          data={[entry]}
          error={null}
          isError={false}
          isPending={false}
          onRetry={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("table")).toHaveAccessibleName(
      "Predefined scenario fixture versions",
    );
    expect(screen.getByRole("columnheader", { name: "Scenario name" })).toHaveAttribute(
      "scope",
      "col",
    );
    expect(screen.getByRole("columnheader", { name: "Scenario ID" })).toHaveAttribute(
      "scope",
      "col",
    );
    expect(screen.getByRole("link", { name: "Fixture A" })).toHaveAttribute(
      "href",
      `/scenarios/${entry.scenario_id}`,
    );
    expect(screen.getByRole("link", { name: "Fixture A" })).toHaveClass(
      "min-h-11",
      "underline",
      "focus-visible:ring-3",
    );
    expect(screen.getByText(entry.scenario_id)).toHaveAttribute(
      "title",
      entry.scenario_id,
    );
    expect(screen.getByText(entry.scenario_id)).toHaveClass("break-all");
    expect(screen.getByRole("table")).toHaveClass("table-fixed");
    expect(screen.getByRole("table").parentElement).toHaveClass(
      "overflow-hidden",
    );
    expect(screen.getByText("2026-07-24 09:30")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /create|upload|import|edit|delete/i,
      }),
    ).not.toBeInTheDocument();
    expect(container.querySelector("[data-state='selected']")).toBeNull();
  });

  it("disables skeleton animation when reduced motion is requested", () => {
    const { container } = render(
      <MemoryRouter>
        <FixtureCatalogueView
          data={undefined}
          error={null}
          isError={false}
          isPending
          onRetry={vi.fn()}
        />
      </MemoryRouter>,
    );

    for (const skeleton of Array.from(
      container.querySelectorAll('[data-slot="skeleton"]'),
    )) {
      expect(skeleton).toHaveClass("motion-reduce:animate-none");
    }
  });
});
