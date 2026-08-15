import { afterEach, describe, expect, it, vi } from "vitest";

import { consumeOrigin, originElementId, rememberOrigin, type EvidenceOrigin } from "./origin";

const origin: EvidenceOrigin = {
  conversationId: "conversation-1",
  activityId: "activity-1",
  segmentIndex: 2,
  refIndex: 3,
};

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("evidence origin", () => {
  it("uses one stable DOM id and consumes remembered origins once", () => {
    expect(originElementId(origin)).toBe("evidence-origin-activity-1-2-3");
    rememberOrigin(origin);
    expect(consumeOrigin()).toEqual(origin);
    expect(consumeOrigin()).toBeNull();
  });

  it("degrades without throwing when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("disabled");
    });
    expect(() => rememberOrigin(origin)).not.toThrow();

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("disabled");
    });
    expect(consumeOrigin()).toBeNull();
  });
});
