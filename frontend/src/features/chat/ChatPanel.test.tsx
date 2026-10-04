import { render, screen } from "@testing-library/react";
import { act, type ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./ChatView", () => ({
  // Renders `headerActions` like the real title row does: the expanded
  // panel's collapse toggle lives there.
  ChatView: ({ scenarioId, headerActions }: { scenarioId: string; headerActions?: ReactNode }) => (
    <>
      {headerActions}
      <label>
        Draft for {scenarioId}
        <input />
      </label>
    </>
  ),
}));

import { ChatPanel } from "./ChatPanel";

const SCENARIO = "33333333-3333-3333-3333-333333333333";
const STORAGE_KEY = "shiftmind.chat-panel-expanded";

function renderPanel(initialEntry = `/scenarios/${SCENARIO}/data`) {
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId/*", element: <ChatPanel scenarioId={SCENARIO} /> }],
    { initialEntries: [initialEntry] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

function setNarrow(narrow: boolean) {
  vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
    matches: narrow && query === "(max-width: 1023px)",
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  localStorage.clear();
  setNarrow(false);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatPanel", () => {
  it("starts expanded on desktop with an accessible collapse control", () => {
    renderPanel();

    const toggle = screen.getByRole("button", { name: "Collapse chat" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText(`Draft for ${SCENARIO}`)).toBeVisible();
  });

  it("collapses to a rail without unmounting the chat, and remembers the choice", async () => {
    renderPanel();
    const draft = screen.getByLabelText(`Draft for ${SCENARIO}`);
    await userEvent.type(draft, "unsaved edit");

    await userEvent.click(screen.getByRole("button", { name: "Collapse chat" }));

    const expand = screen.getByRole("button", { name: "Expand chat" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    // Hidden, not unmounted: the same input still holds the unsaved edit.
    expect(draft).not.toBeVisible();
    expect(draft).toHaveValue("unsaved edit");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("false");

    await userEvent.click(expand);
    expect(screen.getByLabelText(`Draft for ${SCENARIO}`)).toBe(draft);
    expect(localStorage.getItem(STORAGE_KEY)).toBe("true");
  });

  it("keeps keyboard focus on the toggle as it moves between title row and rail", async () => {
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Collapse chat" }));
    expect(screen.getByRole("button", { name: "Expand chat" })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Expand chat" }));
    expect(screen.getByRole("button", { name: "Collapse chat" })).toHaveFocus();
  });

  it("restores a stored collapsed state", () => {
    localStorage.setItem(STORAGE_KEY, "false");
    renderPanel();

    expect(screen.getByRole("button", { name: "Expand chat" })).toBeInTheDocument();
  });

  it("falls back to expanded when storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Collapse chat" }));
    expect(screen.getByRole("button", { name: "Expand chat" })).toBeInTheDocument();
  });

  it("opens when the URL names a conversation, even if stored collapsed", () => {
    localStorage.setItem(STORAGE_KEY, "false");
    renderPanel(`/scenarios/${SCENARIO}/data?conversation=c1`);

    expect(screen.getByRole("button", { name: "Collapse chat" })).toBeInTheDocument();
  });

  it("is expanded on its first render when the URL names a conversation", () => {
    // Not after an effect: ChatView restores focus before the panel's effects
    // run, and focus inside `hidden` silently fails.
    localStorage.setItem(STORAGE_KEY, "false");
    setNarrow(true);
    renderPanel(`/scenarios/${SCENARIO}/data?conversation=c1`);

    expect(screen.getByLabelText(`Draft for ${SCENARIO}`)).toBeVisible();
  });

  it("treats an empty conversation param as naming nothing", () => {
    localStorage.setItem(STORAGE_KEY, "false");
    renderPanel(`/scenarios/${SCENARIO}/data?conversation=`);

    expect(screen.getByRole("button", { name: "Expand chat" })).toBeInTheDocument();
  });

  it("closes the narrow drawer when the planner navigates elsewhere, e.g. to evidence", async () => {
    setNarrow(true);
    const router = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Expand chat" }));

    // The chat's own selection write must not close it...
    await act(() => router.navigate(`/scenarios/${SCENARIO}/data?conversation=c1`, { replace: true }));
    expect(screen.getByRole("button", { name: "Collapse chat" })).toBeInTheDocument();

    // ...but a real page change does.
    await act(() => router.navigate(`/scenarios/${SCENARIO}/data?group=demand&conversation=c1`));
    expect(screen.getByRole("button", { name: "Expand chat" })).toBeInTheDocument();
  });

  it("closes the narrow drawer on Escape and returns focus to the toggle", async () => {
    setNarrow(true);
    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Expand chat" }));
    await userEvent.click(screen.getByLabelText(`Draft for ${SCENARIO}`));

    await userEvent.keyboard("{Escape}");

    expect(screen.getByRole("button", { name: "Expand chat" })).toHaveFocus();
  });

  it("starts closed on a narrow viewport and does not persist the drawer state", async () => {
    setNarrow(true);
    renderPanel();

    const expand = screen.getByRole("button", { name: "Expand chat" });
    await userEvent.click(expand);

    expect(screen.getByRole("button", { name: "Collapse chat" })).toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
