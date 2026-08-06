import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InlineAlert } from "./InlineAlert";

describe("InlineAlert", () => {
  it("composes inline alerts with one optional recovery action", () => {
    const onRetry = vi.fn();
    render(
      <InlineAlert
        action={
          <button className="min-h-11" onClick={onRetry} type="button">
            Retry
          </button>
        }
        description="Try the request again."
        title="Connection unavailable"
        variant="destructive"
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Connection unavailableTry the request again.Retry",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
