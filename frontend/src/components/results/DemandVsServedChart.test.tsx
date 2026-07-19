/**
 * RES-02 coverage: `toChartData`'s pure data mapping (function-key
 * preservation, null passthrough — D-07/Pitfall 5) plus a render smoke test.
 * No SVG pixel-dimension assertions here — jsdom cannot measure Recharts'
 * `ResponsiveContainer` (RESEARCH.md Pitfall 4); that's a visual concern for
 * manual/E2E verification, not this unit suite.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { DemandVsServedChart, toChartData } from "./DemandVsServedChart";
import type { CoverageStat } from "@/api/results";

describe("toChartData", () => {
  it("maps each function to one entry, preserving keys and required/served values", () => {
    const coverage: Record<string, CoverageStat> = {
      Pick: { required_h: 40, served_h: 32, pct: 80 },
      Receiving: { required_h: 12, served_h: 12, pct: 100 },
    };

    const result = toChartData(coverage);

    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({
      function: "Pick",
      required_h: 40,
      served_h: 32,
    });
    expect(result[1]).toEqual({
      function: "Receiving",
      required_h: 12,
      served_h: 12,
    });
  });

  it("passes a null required_h/served_h through verbatim, never coerced to 0", () => {
    const coverage: Record<string, CoverageStat> = {
      Pack: { required_h: null, served_h: null, pct: null },
    };

    const result = toChartData(coverage);

    expect(result).toEqual([
      { function: "Pack", required_h: null, served_h: null },
    ]);
  });

  it("returns an empty array for empty coverage_by_function", () => {
    expect(toChartData({})).toEqual([]);
  });
});

describe("DemandVsServedChart: render smoke test", () => {
  it("mounts without throwing given populated coverage_by_function", () => {
    const coverage: Record<string, CoverageStat> = {
      Pick: { required_h: 40, served_h: 32, pct: 80 },
      Receiving: { required_h: 12, served_h: 12, pct: 100 },
    };

    expect(() =>
      render(<DemandVsServedChart coverage_by_function={coverage} />),
    ).not.toThrow();
  });

  it("mounts without throwing when a function's values are null", () => {
    const coverage: Record<string, CoverageStat> = {
      Pack: { required_h: null, served_h: null, pct: null },
    };

    expect(() =>
      render(<DemandVsServedChart coverage_by_function={coverage} />),
    ).not.toThrow();
  });
});
