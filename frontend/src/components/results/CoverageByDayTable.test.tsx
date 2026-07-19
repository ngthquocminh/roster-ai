/**
 * D-05/RES-01 coverage for the by-day breakdown table: 1-indexed "Day N"
 * labels (must match ScheduleTable's formatShiftWindow convention), percent
 * formatting, and the per-day null-safe "Not computed" guard.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { CoverageByDayTable } from "./CoverageByDayTable";

describe("CoverageByDayTable: populated [UI-SPEC E4/populated]", () => {
  it("renders 1-indexed 'Day N' rows with percent-formatted values", () => {
    render(
      <CoverageByDayTable coverage_by_day={{ "0": 61.2, "1": 88.0 }} />,
    );

    expect(screen.getByText("Day 1")).toBeInTheDocument();
    expect(screen.getByText("61.2%")).toBeInTheDocument();
    expect(screen.getByText("Day 2")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
  });
});

describe("CoverageByDayTable: partial null [UI-SPEC E4/partial]", () => {
  it("renders 'Not computed' (plain text, no tooltip) for a null day value", () => {
    render(
      <CoverageByDayTable coverage_by_day={{ "0": 61.2, "1": null }} />,
    );

    expect(screen.getByText("Day 2")).toBeInTheDocument();
    expect(screen.getByText("Not computed")).toBeInTheDocument();
  });
});
