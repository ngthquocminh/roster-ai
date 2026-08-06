import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReconnectBanner } from "./ReconnectBanner";

describe("ReconnectBanner", () => {
  it.each([
    ["disconnected", "Connection lost."],
    ["reconnecting", "Reconnecting…"],
    ["reconnected", "Connection restored."],
  ] as const)("renders the %s reconnect state literally", (state, copy) => {
    render(<ReconnectBanner state={state} />);

    expect(screen.getByRole("alert")).toHaveTextContent(copy);
  });
});
