import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IdentifierCopyButton } from "./IdentifierCopyButton";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("IdentifierCopyButton", () => {
  it("mounts an empty live region before copying the full value", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const { container } = render(
      <IdentifierCopyButton identifierType="Task ID" value="T-104-FULL" />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("");
    fireEvent.click(screen.getByRole("button", { name: "Copy Task ID T-104-FULL" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("T-104-FULL"));
    expect(status).toHaveTextContent("Copied Task ID");
    expect(container.querySelector("input, [type=checkbox]")).toBeNull();
  });

  it("announces a rejected write as unavailable and never reports success", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<IdentifierCopyButton identifierType="Record ID" value="demand:104" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy Record ID demand:104" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copy unavailable. Select the identifier to copy it manually."));
    expect(screen.getByRole("status")).not.toHaveTextContent("Copied Record ID");
  });

  it("announces unavailable when the clipboard API is absent", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    render(<IdentifierCopyButton identifierType="Area ID" value="area-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy Area ID area-1" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copy unavailable. Select the identifier to copy it manually."));
  });
});
