import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { COLUMNS_BY_GROUP } from "./columns";
import { ColumnChooser } from "./ColumnChooser";

describe("ColumnChooser", () => {
  it("keeps required and evidence-revealed fields checked and disabled", async () => {
    render(<ColumnChooser columns={COLUMNS_BY_GROUP.workers} onVisibilityChange={vi.fn()} revealedField="grade" visibleKeys={new Set(COLUMNS_BY_GROUP.workers.map((column) => column.key))} />);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Choose columns" }), { button: 0, ctrlKey: false });
    expect(await screen.findByRole("menuitemcheckbox", { name: /Contact ID/ })).toHaveAttribute("data-disabled");
    expect(screen.getByRole("menuitemcheckbox", { name: /Grade.*Shown for the linked evidence target/ })).toHaveAttribute("data-disabled");
  });

  it("toggles only an optional viewing column", async () => {
    const onVisibilityChange = vi.fn();
    render(<ColumnChooser columns={COLUMNS_BY_GROUP.workers} onVisibilityChange={onVisibilityChange} visibleKeys={new Set(COLUMNS_BY_GROUP.workers.map((column) => column.key))} />);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Choose columns" }), { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByRole("menuitemcheckbox", { name: "Grade" }));
    expect(onVisibilityChange).toHaveBeenCalledWith("grade", false);
  });

  it("closes with Escape, restores trigger focus, and commits nothing", async () => {
    const user = userEvent.setup();
    const onVisibilityChange = vi.fn();
    render(<ColumnChooser columns={COLUMNS_BY_GROUP.workers} onVisibilityChange={onVisibilityChange} visibleKeys={new Set(COLUMNS_BY_GROUP.workers.map((column) => column.key))} />);
    const trigger = screen.getByRole("button", { name: "Choose columns" });
    await user.click(trigger);
    expect(await screen.findByRole("menuitemcheckbox", { name: "Grade" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menuitemcheckbox", { name: "Grade" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onVisibilityChange).not.toHaveBeenCalled();
  });
});
