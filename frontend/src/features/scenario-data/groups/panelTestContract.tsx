import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

type Contract = {
  name: string;
  caption: string;
  Panel: ComponentType<{ scenarioId: string }>;
  hook: Mock;
  data: unknown;
  expected: string;
  columnHeaders: number;
  emptyData?: unknown;
};

export function panelTestContract({ Panel, caption, columnHeaders, data, emptyData = { items: [] }, expected, hook, name }: Contract) {
  const refetch = vi.fn();
  beforeEach(() => { hook.mockReset(); refetch.mockReset(); });
  describe(name, () => {
    it("renders loading, error/retry, and empty states", () => {
      hook.mockReturnValue({ data: undefined, isError: false, isPending: true, refetch });
      const { rerender } = render(<Panel scenarioId="scenario-a" />);
      expect(screen.getByRole("status", { name: "Loading scenario data" })).toBeInTheDocument();
      hook.mockReturnValue({ data: undefined, error: { status: 503 }, isError: true, isPending: false, refetch });
      rerender(<Panel scenarioId="scenario-a" />);
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(refetch).toHaveBeenCalledOnce();
      hook.mockReturnValue({ data: emptyData, isError: false, isPending: false, refetch });
      rerender(<Panel scenarioId="scenario-a" />);
      expect(screen.getByText("This fixture has no records in this group.")).toBeInTheDocument();
    });

    it("shows a non-retryable explanation for a terminal (404/422) failure", () => {
      hook.mockReturnValue({ data: undefined, error: { status: 404 }, isError: true, isPending: false, refetch });
      render(<Panel scenarioId="scenario-a" />);
      expect(screen.getByText("Scenario not found")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    });

    it("renders a captioned semantic read-only table", () => {
      hook.mockReturnValue({ data, isError: false, isPending: false, refetch });
      const { container } = render(<Panel scenarioId="scenario-a" />);
      expect(screen.getByText(caption, { selector: "caption" })).toBeInTheDocument();
      expect(screen.getByText(expected)).toBeInTheDocument();
      expect(container.querySelectorAll('th[scope="col"]')).toHaveLength(columnHeaders);
      expect(container.querySelector("input, select, [contenteditable='true']")).toBeNull();
      expect(container.querySelector("a, [role='button']")).toBeNull();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });
  });
}
