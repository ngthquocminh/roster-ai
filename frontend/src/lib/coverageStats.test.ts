import { describe, expect, it } from "vitest";

import { hoursByDay, summarizeCoverage } from "./coverageStats";

const base = {
  interval_coverage_required_minutes: [] as [string, number][],
  interval_coverage_served_minutes: [] as [string, number][],
  function_coverage_required_minutes: [] as [string, number][],
  function_coverage_served_minutes: [] as [string, number][],
  overtime_minutes: 0, total_cost: 0, objective_components: [] as [string, number][],
  assignment_count: 0, member_count: 0, schema_version: "1",
};

describe("summarizeCoverage", () => {
  it("returns null coverage (never NaN) when nothing is required", () => {
    const s = summarizeCoverage(base);
    expect(s.coveragePct).toBeNull();
    expect(s.unresolvedCount).toBe(0);
    expect(s.worst).toEqual([]);
  });

  it("counts under-served intervals, buckets them, and keeps only the top 5", () => {
    const required: [string, number][] = [];
    const served: [string, number][] = [];
    for (let i = 0; i < 300; i++) { required.push([`d-${i}`, 100]); served.push([`d-${i}`, i % 2 ? 100 : 100 - (i % 150) - 1]); }
    const s = summarizeCoverage({ ...base, interval_coverage_required_minutes: required, interval_coverage_served_minutes: served });
    expect(s.intervalCount).toBe(300);
    expect(s.unresolvedCount).toBe(150);
    expect(s.worst).toHaveLength(5);
    expect(s.worst[0].shortfallMinutes).toBeGreaterThanOrEqual(s.worst[4].shortfallMinutes);
    expect(s.buckets.reduce((n, b) => n + b.count, 0)).toBe(150);
  });

  it("treats a missing served row as zero and computes shortfall and percentage", () => {
    const s = summarizeCoverage({
      ...base,
      interval_coverage_required_minutes: [["a", 60], ["b", 60]],
      interval_coverage_served_minutes: [["a", 45]],
      function_coverage_required_minutes: [["Picking", 120]],
      function_coverage_served_minutes: [["Picking", 45]],
    });
    expect(s.shortfallMinutes).toBe(75);
    expect(s.coveragePct).toBeCloseTo(37.5);
    expect(s.buckets.map((b) => b.count)).toEqual([1, 0, 1, 0]);
    expect(s.byFunction[0]).toMatchObject({ name: "Picking", pct: 37.5 });
  });

  it("does not let over-serving one interval hide a gap in another", () => {
    const s = summarizeCoverage({
      ...base,
      interval_coverage_required_minutes: [["a", 60], ["b", 60]],
      interval_coverage_served_minutes: [["a", 90], ["b", 30]],
    });
    expect(s.servedMinutes).toBe(90);
    expect(s.unresolvedCount).toBe(1);
  });
});

describe("hoursByDay", () => {
  it("splits an assignment crossing midnight across days", () => {
    expect(hoursByDay([{ start_minute: 1380, end_minute: 1500 }])).toEqual([
      { day: 1, hours: 1 },
      { day: 2, hours: 1 },
    ]);
  });
});
