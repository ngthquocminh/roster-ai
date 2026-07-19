/**
 * D-06/RES-06 coverage for the coverage-honesty caveat: renders nothing when
 * empty (no chrome at all), renders a single Alert for one or many warnings
 * (never stacked banners), and every string renders verbatim.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { WarningsBanner } from "./WarningsBanner";

describe("WarningsBanner: empty [UI-SPEC E2/empty-hidden]", () => {
  it("renders nothing — not even empty chrome", () => {
    const { container } = render(<WarningsBanner warnings={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("WarningsBanner: one warning [UI-SPEC E2/populated]", () => {
  it("renders the 'Heads up' title and the warning text", () => {
    render(<WarningsBanner warnings={["a"]} />);

    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("a")).toBeInTheDocument();
  });
});

describe("WarningsBanner: many warnings [UI-SPEC E2/zero-one-many]", () => {
  it("renders both strings inside a single banner, not two stacked banners", () => {
    render(<WarningsBanner warnings={["a", "b"]} />);

    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });
});
