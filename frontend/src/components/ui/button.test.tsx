import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./button";

// Story 3.12 review: the shared `destructive` variant was rewritten from a
// tinted to a solid treatment to clear a real-browser contrast failure, but
// gained no component-layer coverage — the only guard was whichever states the
// new Playwright axe sweep happened to visit. `destructive` renders on Chat,
// Runs, Evidence, and the Fixture Catalogue, so pin the governed pairing here.
describe("Button destructive variant", () => {
  it("renders the solid destructive surface with its governed foreground token", () => {
    render(
      <Button type="button" variant="destructive">
        Reject proposal
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Reject proposal" });
    expect(button).toHaveClass("bg-destructive");
    expect(button).toHaveClass("text-destructive-foreground");
  });

  it("does not pair the destructive surface with a raw color utility", () => {
    render(
      <Button type="button" variant="destructive">
        Cancel
      </Button>,
    );

    // A raw `text-white` does not follow `--destructive` if the palette is
    // re-themed, which is what shipped before this test existed.
    expect(screen.getByRole("button", { name: "Cancel" })).not.toHaveClass("text-white");
  });

  it("leaves the other variants' surfaces untouched", () => {
    render(
      <>
        <Button type="button" variant="outline">Refresh</Button>
        <Button type="button" variant="ghost">Dismiss</Button>
      </>,
    );

    expect(screen.getByRole("button", { name: "Refresh" })).not.toHaveClass("bg-destructive");
    expect(screen.getByRole("button", { name: "Dismiss" })).not.toHaveClass("bg-destructive");
  });
});
