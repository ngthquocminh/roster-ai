import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

const SCENARIO = "33333333-3333-3333-3333-333333333333";

function renderComposer(onSend: (text: string) => Promise<unknown>, isPending = false) {
  return render(
    <MemoryRouter>
      <Composer isPending={isPending} onSend={onSend} scenarioId={SCENARIO} />
    </MemoryRouter>,
  );
}

describe("Composer", () => {
  it("keeps Enter as a newline without submitting", async () => { const send = vi.fn(); renderComposer(send); const box = screen.getByRole("textbox"); await userEvent.type(box, "line{enter}two"); expect(box).toHaveValue("line\ntwo"); expect(send).not.toHaveBeenCalled(); });
  it.each([{ ctrlKey: true }, { metaKey: true }])("submits with the command shortcut", async (modifier) => { const send = vi.fn().mockResolvedValue(undefined); renderComposer(send); const box = screen.getByRole("textbox"); fireEvent.change(box, { target: { value: "inspect" } }); fireEvent.keyDown(box, { key: "Enter", ...modifier }); await waitFor(() => expect(send).toHaveBeenCalledWith("inspect")); });
  it("submits with the visible Send button", async () => { const send = vi.fn().mockResolvedValue(undefined); renderComposer(send); await userEvent.type(screen.getByRole("textbox"), "inspect"); await userEvent.click(screen.getByRole("button", { name: "Send" })); expect(send).toHaveBeenCalledWith("inspect"); });
  it("retains the draft, keeps retry live, and links trusted Scenario Data after rejection", async () => {
    const send = vi.fn().mockRejectedValue(new Error("offline"));
    renderComposer(send);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "keep me");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(send).toHaveBeenCalled());
    expect(box).toHaveValue("keep me");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Open Scenario Data" })).toHaveAttribute(
      "href",
      `/scenarios/${SCENARIO}/data`,
    );
  });

  it("sends once when the command shortcut repeats before isPending propagates", async () => {
    // `isPending` is a prop and arrives a render late. Decision 4 ships no
    // idempotency key, so a repeated keystroke that got through would persist
    // two messages and two agent runs.
    let resolve: (value: unknown) => void = () => {};
    const send = vi.fn().mockImplementation(() => new Promise((r) => { resolve = r; }));
    renderComposer(send);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "inspect" } });

    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(box, { key: "Enter", ctrlKey: true });

    await waitFor(() => expect(send).toHaveBeenCalled());
    expect(send).toHaveBeenCalledTimes(1);
    resolve(undefined);
    await waitFor(() => expect(box).toHaveValue(""));
  });
});
