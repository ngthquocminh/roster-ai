/**
 * WR-03: single typed accessor for an API error's `status`, replacing the
 * three verbatim `(error as { status?: number } | null)?.status` casts that
 * previously lived in `ScenarioHeader`, `ConstraintInput`, and `Editor`.
 */
import { describe, it, expect } from "vitest";

import { getErrorStatus } from "./errors";

describe("getErrorStatus", () => {
  it("returns the numeric status from a { status } error object", () => {
    expect(getErrorStatus({ status: 404 })).toBe(404);
  });

  it("returns undefined for null", () => {
    expect(getErrorStatus(null)).toBeUndefined();
  });

  it("returns undefined for a plain Error with no status field", () => {
    expect(getErrorStatus(new Error("network error"))).toBeUndefined();
  });

  it("returns undefined when status is a non-number value", () => {
    expect(getErrorStatus({ status: "404" })).toBeUndefined();
  });

  it("returns undefined for a primitive (string/number/undefined)", () => {
    expect(getErrorStatus("boom")).toBeUndefined();
    expect(getErrorStatus(500)).toBeUndefined();
    expect(getErrorStatus(undefined)).toBeUndefined();
  });
});
