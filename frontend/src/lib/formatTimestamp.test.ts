/**
 * Unit tests for formatTimestamp (gap G-03-1 / RUN-04) — pins the exact
 * real-world backend timestamp shapes (32-char microsecond+offset, and the
 * shorter Z-suffixed form) and the defensive fallback for unrecognized
 * input, so the Run History column-overflow regression cannot silently
 * return.
 */
import { describe, it, expect } from "vitest";
import { formatHorizon, formatTimestamp } from "./formatTimestamp";

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

describe("formatHorizon", () => {
  it("renders a whole-week horizon as a day count", () => {
    expect(formatHorizon("2026-05-31T14:00:00Z", 10_080)).toBe(
      "2026-05-31 14:00 → 2026-06-07 14:00 (7 days)",
    );
  });

  it("renders a non-day-aligned horizon with an hours/minutes remainder", () => {
    expect(formatHorizon("2026-01-01T00:00:00Z", 90)).toBe(
      "2026-01-01 00:00 → 2026-01-01 01:30 (1 hour 30 minutes)",
    );
  });

  it("falls back to the raw shape for an unparseable start", () => {
    expect(formatHorizon("not-a-date", 60)).toBe("starts not-a-date, 60 minutes");
  });

  it("treats a zone-naive start as UTC, never the host's local time", () => {
    // No `Z`/offset suffix -- `new Date(string)` would parse this as
    // host-local time in a browser; this must not shift with the runner's TZ.
    expect(formatHorizon("2026-01-01T00:00:00", 60)).toBe(
      "2026-01-01 00:00 → 2026-01-01 01:00 (1 hour)",
    );
  });

  it("falls back to the raw shape for a negative duration rather than rendering a malformed one", () => {
    expect(formatHorizon("2026-01-01T00:00:00Z", -30)).toBe(
      "starts 2026-01-01T00:00:00Z, -30 minutes",
    );
  });

  it("rounds a non-integer duration to a whole minute", () => {
    expect(formatHorizon("2026-01-01T00:00:00Z", 90.5)).toBe(
      "2026-01-01 00:00 → 2026-01-01 01:31 (1 hour 31 minutes)",
    );
  });
});
