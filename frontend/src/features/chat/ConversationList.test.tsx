import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConversationList } from "./ConversationList";

const A = "aaaaaaaa-0000-0000-0000-000000000000";
const B = "bbbbbbbb-0000-0000-0000-000000000000";

function conversation(id: string) {
  return {
    id,
    scenario_id: "33333333-3333-3333-3333-333333333333",
    scenario_version_id: "44444444-4444-4444-4444-444444444444",
    resource_version: 1,
  };
}

function renderList(overrides: Partial<Parameters<typeof ConversationList>[0]> = {}) {
  const onSelect = vi.fn();
  const onArchive = vi.fn();
  const onFocusFallback = vi.fn();
  render(
    <ConversationList
      archivingIds={new Set()}
      conversations={[conversation(A), conversation(B)]}
      onArchive={onArchive}
      onFocusFallback={onFocusFallback}
      onSelect={onSelect}
      selectedId=""
      {...overrides}
    />,
  );
  return { onArchive, onFocusFallback, onSelect };
}

describe("ConversationList", () => {
  it("lays the tabs out as a single, non-wrapping row that scrolls on overflow", () => {
    renderList();

    const list = screen.getByRole("list");
    expect(list.className).toContain("flex-nowrap");
    expect(list.className).toContain("overflow-x-auto");
    expect(list.className).not.toContain("flex-wrap");
  });

  it("keeps the archive affix a sibling of the select tab, not nested inside it", () => {
    renderList();

    // Two distinct, independently-named buttons per conversation. If the
    // archive control were nested inside the select button, this query would
    // either fail (invalid HTML collapses to one accessible node) or the
    // select button's name would pick up the affix's text.
    const select = screen.getByRole("button", { name: `Conversation ${A.slice(0, 8)}` });
    const archive = screen.getByRole("button", { name: `Archive conversation ${A.slice(0, 8)}` });
    expect(select).not.toBe(archive);
    expect(archive.contains(select)).toBe(false);
    expect(select.contains(archive)).toBe(false);
  });

  it("does not archive on a single click — it opens a confirm dialog first", async () => {
    const { onArchive } = renderList();

    await userEvent.click(
      screen.getByRole("button", { name: `Archive conversation ${A.slice(0, 8)}` }),
    );

    expect(onArchive).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Archive conversation" })).toBeInTheDocument();
  });

  it("calls onArchive with the right id once the dialog is confirmed", async () => {
    const { onArchive } = renderList();

    await userEvent.click(
      screen.getByRole("button", { name: `Archive conversation ${B.slice(0, 8)}` }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));

    expect(onArchive).toHaveBeenCalledExactlyOnceWith(B);
  });

  it("does not archive when the dialog is cancelled", async () => {
    const { onArchive } = renderList();

    await userEvent.click(
      screen.getByRole("button", { name: `Archive conversation ${A.slice(0, 8)}` }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onArchive).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("disables only the archiving tab's own affix, not every tab", () => {
    renderList({ archivingIds: new Set([A]) });

    expect(
      screen.getByRole("button", { name: `Archive conversation ${A.slice(0, 8)}` }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: `Archive conversation ${B.slice(0, 8)}` }),
    ).not.toBeDisabled();
  });

  it("keeps both tabs' own archiving state independent when two are in flight at once", () => {
    // Guards the concurrency bug a single shared `archivingId` had: confirming
    // archive on B while A is still in flight must not re-enable A.
    renderList({ archivingIds: new Set([A, B]) });

    expect(
      screen.getByRole("button", { name: `Archive conversation ${A.slice(0, 8)}` }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: `Archive conversation ${B.slice(0, 8)}` }),
    ).toBeDisabled();
  });

  it("renders nothing for an empty conversation list", () => {
    const { container } = render(
      <ConversationList
        archivingIds={new Set()}
        conversations={[]}
        onArchive={vi.fn()}
        onFocusFallback={vi.fn()}
        onSelect={vi.fn()}
        selectedId=""
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
