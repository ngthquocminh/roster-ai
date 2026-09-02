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

// Story 4.6 code review. Decision 10 replaced `disabled:opacity-50` on the outline
// variant because dimming near-black text over white composites to #848484 (3.74:1,
// axe measured #858585 / 3.69:1) during the window where the control is enabled but
// `transition-all` is still interpolating back. The replacement pair paints its own
// background, so the ratio no longer depends on the surface behind the button --
// but `bg-muted` + `text-foreground` is byte-identical to this variant's OWN hover
// treatment, which made a disabled control read as a highlighted one.
describe("Button outline disabled treatment", () => {
  const classesOf = (name: string) =>
    new Set(Array.from(screen.getByRole("button", { name }).classList));

  it("distinguishes disabled from hover by something other than colour", () => {
    render(<Button disabled type="button" variant="outline">Refreshing…</Button>);
    const classes = classesOf("Refreshing…");

    // The colour half is deliberately shared with hover; the shape half is what
    // separates them, and it is not a colour, so it survives any re-theming.
    expect(classes).toContain("disabled:bg-muted");
    expect(classes).toContain("disabled:text-foreground");
    expect(classes).toContain("disabled:border-dashed");

    const disabledOnly = Array.from(classes)
      .filter((token) => token.startsWith("disabled:"))
      .map((token) => token.slice("disabled:".length));
    const hoverOnly = Array.from(classes)
      .filter((token) => token.startsWith("hover:"))
      .map((token) => token.slice("hover:".length));
    const sharedWithHover = disabledOnly.filter((token) => hoverOnly.includes(token));

    expect(
      disabledOnly.filter((token) => !sharedWithHover.includes(token)),
      "outline disabled must carry a cue its hover state does not",
    ).not.toEqual([]);
  });

  it("keeps the dimming that produced the measured failure off this variant", () => {
    render(<Button disabled type="button" variant="outline">Refreshing…</Button>);
    expect(classesOf("Refreshing…")).not.toContain("disabled:opacity-50");
  });

  it("leaves every other variant on the shared dimming", () => {
    render(
      <>
        <Button disabled type="button" variant="secondary">Run optimization</Button>
        <Button disabled type="button" variant="default">Approve</Button>
      </>,
    );

    // `--secondary` and `--muted` are the same value in both themes, so putting
    // the outline pair on the shared base made a disabled `secondary` control
    // near-indistinguishable from an enabled one.
    for (const name of ["Run optimization", "Approve"]) {
      expect(classesOf(name)).toContain("disabled:opacity-50");
      expect(classesOf(name)).not.toContain("disabled:bg-muted");
    }
  });
});
