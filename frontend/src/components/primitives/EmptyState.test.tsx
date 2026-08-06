import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders an empty explanation with at most one supplied action", () => {
    render(
      <EmptyState
        action={<a href="/fixtures">Return to fixtures</a>}
        explanation="No records match this view."
      />,
    );

    expect(screen.getByText("No records match this view.")).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
