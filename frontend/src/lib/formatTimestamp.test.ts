/**
 * Unit tests for formatTimestamp (gap G-03-1 / RUN-04) — pins the exact
 * real-world backend timestamp shapes (32-char microsecond+offset, and the
 * shorter Z-suffixed form) and the defensive fallback for unrecognized
 * input, so the Run History column-overflow regression cannot silently
 * return.
 */
import { describe, it, expect } from "vitest";
import { formatTimestamp } from "./formatTimestamp";

describe("formatTimestamp", () => {
  it("shortens the real 32-char microsecond+offset backend format", () => {
    expect(formatTimestamp("2026-07-18T15:53:53.702354+00:00")).toBe(
      "2026-07-18 15:53",
    );
  });

  it("shortens the Z-suffixed ISO format", () => {
    expect(formatTimestamp("2026-07-18T10:00:00Z")).toBe("2026-07-18 10:00");
  });

  it("shortens a fractional-second offset format", () => {
    expect(formatTimestamp("2026-07-18T09:00:05.5+00:00")).toBe(
      "2026-07-18 09:00",
    );
  });

  it("falls back to the raw input for an unrecognized shape", () => {
    expect(formatTimestamp("not-a-date")).toBe("not-a-date");
  });

  it("passes an empty string through unchanged", () => {
    expect(formatTimestamp("")).toBe("");
  });
});
