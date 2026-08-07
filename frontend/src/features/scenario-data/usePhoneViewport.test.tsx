import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePhoneViewport } from "./usePhoneViewport";

function mockMatchMedia(initialMatches: boolean) {
  let listener: ((event: MediaQueryListEvent) => void) | undefined;
  const mql = {
    matches: initialMatches,
    media: "(max-width: 767px)",
    onchange: null,
    addEventListener: vi.fn((_event: string, handler: (event: MediaQueryListEvent) => void) => {
      listener = handler;
    }),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
  vi.mocked(window.matchMedia).mockReturnValue(mql);
  return {
    fireChange(matches: boolean) {
      mql.matches = matches;
      listener?.({ matches } as MediaQueryListEvent);
    },
    mql,
  };
}

beforeEach(() => {
  mockMatchMedia(false);
});

describe("usePhoneViewport", () => {
  it("reflects the initial matchMedia state", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => usePhoneViewport());
    expect(result.current).toBe(true);
  });

  it("flips live when the media query change fires, without a remount", () => {
    const { fireChange } = mockMatchMedia(false);
    const { result } = renderHook(() => usePhoneViewport());
    expect(result.current).toBe(false);
    act(() => fireChange(true));
    expect(result.current).toBe(true);
    act(() => fireChange(false));
    expect(result.current).toBe(false);
  });

  it("unsubscribes the change listener on unmount", () => {
    const { mql } = mockMatchMedia(false);
    const { unmount } = renderHook(() => usePhoneViewport());
    expect(mql.addEventListener).toHaveBeenCalledWith("change", expect.any(Function));
    unmount();
    expect(mql.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
