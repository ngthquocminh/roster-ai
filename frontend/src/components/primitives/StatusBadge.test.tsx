import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders literal status text and an accessible name", () => {
    render(<StatusBadge status="queued" />);

    expect(screen.getByLabelText("queued")).toHaveTextContent("queued");
  });
});
