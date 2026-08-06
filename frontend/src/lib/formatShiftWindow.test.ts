import { describe, it, expect } from "vitest";
import { formatMinuteWindow, formatShiftWindow } from "./formatShiftWindow";

describe("formatShiftWindow", () => {
  it("formats a same-day shift as 'Day N, HH:MM–HH:MM' (1-indexed)", () => {
    expect(formatShiftWindow(8.5, 16.0)).toBe("Day 1, 08:30–16:00");
  });

  it("formats a second-day shift correctly (day-2 06:00 = 30.0h per docs/API.md convention)", () => {
    expect(formatShiftWindow(30.0, 38.0)).toBe("Day 2, 06:00–14:00");
  });

  it("formats a cross-midnight shift with both days labeled explicitly", () => {
    expect(formatShiftWindow(22.0, 30.0)).toBe("Day 1, 22:00 – Day 2, 06:00");
  });

  it("rounds once in total minutes so a 23.999h boundary never renders '24:00'", () => {
    const result = formatShiftWindow(0.0, 23.999);
    expect(result).not.toContain("24:00");
    expect(result).toBe("Day 1, 00:00 – Day 2, 00:00");
  });

  it("renders hour 0 as 'Day 1' (1-indexed), never 'Day 0'", () => {
    expect(formatShiftWindow(0.0, 4.0)).toBe("Day 1, 00:00–04:00");
  });
});

describe("formatMinuteWindow", () => {
  it("uses the established day/time presentation for minute offsets", () => {
    expect(formatMinuteWindow(510, 960)).toBe("Day 1, 08:30–16:00");
  });

  it("labels both days for a cross-midnight minute window", () => {
    expect(formatMinuteWindow(1320, 1800)).toBe("Day 1, 22:00 – Day 2, 06:00");
  });
});
