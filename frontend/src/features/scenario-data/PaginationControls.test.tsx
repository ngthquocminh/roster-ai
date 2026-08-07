import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaginationControls } from "./PaginationControls";

describe("PaginationControls", () => {
  it("disables first and previous on the first page and next at the end", () => {
    const onPageChange = vi.fn();
    const { rerender } = render(
      <PaginationControls cursor={0} hasFilters={false} itemCount={50} matchingCount={50} nextCursor={null} onPageChange={onPageChange} totalCount={50} />,
    );
    expect(screen.getByRole("button", { name: "First" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    rerender(<PaginationControls cursor={50} hasFilters={false} itemCount={50} matchingCount={114} nextCursor={100} onPageChange={onPageChange} totalCount={114} />);
    fireEvent.click(screen.getByRole("button", { name: "First" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    fireEvent.click(screen.getByRole("button", { name: "Last" }));
    expect(onPageChange.mock.calls.map(([cursor]) => cursor)).toEqual([0, 0, 100]);
  });

  it("renders both counts when filtered and mirrors the range to a mounted polite region", () => {
    render(<PaginationControls cursor={50} hasFilters itemCount={50} matchingCount={214} nextCursor={100} onPageChange={vi.fn()} totalCount={1203} />);
    const copy = "Showing 51–100 of 214 matching (1,203 total)";
    expect(screen.getByText(copy, { selector: "p" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(copy);
  });

  it("announces zero for an out-of-range stale cursor", () => {
    render(<PaginationControls cursor={100} hasFilters itemCount={0} matchingCount={12} nextCursor={null} onPageChange={vi.fn()} totalCount={1203} />);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 12 matching (1,203 total)");
  });
});
