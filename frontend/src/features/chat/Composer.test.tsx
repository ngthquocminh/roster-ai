import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("keeps Enter as a newline without submitting", async () => { const send = vi.fn(); render(<Composer onSend={send} isPending={false} />); const box = screen.getByRole("textbox"); await userEvent.type(box, "line{enter}two"); expect(box).toHaveValue("line\ntwo"); expect(send).not.toHaveBeenCalled(); });
  it.each([{ ctrlKey: true }, { metaKey: true }])("submits with the command shortcut", async (modifier) => { const send = vi.fn().mockResolvedValue(undefined); render(<Composer onSend={send} isPending={false} />); const box = screen.getByRole("textbox"); fireEvent.change(box, { target: { value: "inspect" } }); fireEvent.keyDown(box, { key: "Enter", ...modifier }); await waitFor(() => expect(send).toHaveBeenCalledWith("inspect")); });
  it("submits with the visible Send button", async () => { const send = vi.fn().mockResolvedValue(undefined); render(<Composer onSend={send} isPending={false} />); await userEvent.type(screen.getByRole("textbox"), "inspect"); await userEvent.click(screen.getByRole("button", { name: "Send" })); expect(send).toHaveBeenCalledWith("inspect"); });
  it("retains the draft after a recoverable rejection", async () => { const send = vi.fn().mockRejectedValue(new Error("offline")); render(<Composer onSend={send} isPending={false} />); const box = screen.getByRole("textbox"); await userEvent.type(box, "keep me"); await userEvent.click(screen.getByRole("button", { name: "Send" })); await waitFor(() => expect(send).toHaveBeenCalled()); expect(box).toHaveValue("keep me"); });
});
