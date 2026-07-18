/**
 * Coverage for the run-status vocabulary + terminal/active predicates
 * (UI-SPEC Color section status icon/color mapping table). Pure module, no
 * mocking needed.
 */
import { describe, it, expect } from "vitest";
import { Clock, LoaderCircle, Check, X } from "lucide-react";
import {
  RUN_STATUS_META,
  runStatusMeta,
  isTerminalStatus,
  hasActiveRun,
  newestActiveRun,
} from "./runStatus";

function run(overrides: Partial<{ id: string; status: string; created_at: string }> = {}) {
  return {
    id: "r1",
    scenario_id: "s1",
    status: "PENDING",
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    solver_status: null,
    error: null,
    ...overrides,
  };
}

describe("runStatusMeta", () => {
  it("maps PENDING to Clock + 'Queued' + muted-foreground, no spin", () => {
    const meta = runStatusMeta("PENDING");
    expect(meta.label).toBe("Queued");
    expect(meta.Icon).toBe(Clock);
    expect(meta.className).toBe("text-muted-foreground");
    expect(meta.spin).toBeFalsy();
  });

  it("maps RUNNING to LoaderCircle + 'Running' + muted-foreground + spin", () => {
    const meta = runStatusMeta("RUNNING");
    expect(meta.label).toBe("Running");
    expect(meta.Icon).toBe(LoaderCircle);
    expect(meta.className).toBe("text-muted-foreground");
    expect(meta.spin).toBe(true);
  });

  it("maps COMPLETED to Check + 'Completed' + foreground (neutral), no spin", () => {
    const meta = runStatusMeta("COMPLETED");
    expect(meta.label).toBe("Completed");
    expect(meta.Icon).toBe(Check);
    expect(meta.className).toBe("text-foreground");
    expect(meta.spin).toBeFalsy();
  });

  it("maps FAILED to X + 'Failed' + destructive, no spin", () => {
    const meta = runStatusMeta("FAILED");
    expect(meta.label).toBe("Failed");
    expect(meta.Icon).toBe(X);
    expect(meta.className).toBe("text-destructive");
    expect(meta.spin).toBeFalsy();
  });

  it("falls back to a neutral Clock + muted treatment for an unrecognized status, using the raw string as label (never fabricated)", () => {
    const meta = runStatusMeta("WEIRD_UNSEEN");
    expect(meta.label).toBe("WEIRD_UNSEEN");
    expect(meta.Icon).toBe(Clock);
    expect(meta.className).toBe("text-muted-foreground");
  });
});

describe("RUN_STATUS_META", () => {
  it("is keyed by the four known status strings", () => {
    expect(Object.keys(RUN_STATUS_META).sort()).toEqual(
      ["COMPLETED", "FAILED", "PENDING", "RUNNING"].sort(),
    );
  });
});

describe("isTerminalStatus", () => {
  it("is true for COMPLETED and FAILED", () => {
    expect(isTerminalStatus("COMPLETED")).toBe(true);
    expect(isTerminalStatus("FAILED")).toBe(true);
  });

  it("is false for PENDING and RUNNING", () => {
    expect(isTerminalStatus("PENDING")).toBe(false);
    expect(isTerminalStatus("RUNNING")).toBe(false);
  });
});

describe("hasActiveRun", () => {
  it("is false for an empty list", () => {
    expect(hasActiveRun([])).toBe(false);
  });

  it("is false for an all-terminal list", () => {
    expect(hasActiveRun([run({ status: "COMPLETED" }), run({ status: "FAILED" })])).toBe(false);
  });

  it("is true when any run is PENDING or RUNNING", () => {
    expect(hasActiveRun([run({ status: "COMPLETED" }), run({ status: "PENDING" })])).toBe(true);
    expect(hasActiveRun([run({ status: "RUNNING" })])).toBe(true);
  });
});

describe("newestActiveRun", () => {
  it("returns null when no non-terminal run exists", () => {
    expect(newestActiveRun([run({ status: "COMPLETED" }), run({ status: "FAILED" })])).toBeNull();
  });

  it("returns null for an empty list", () => {
    expect(newestActiveRun([])).toBeNull();
  });

  it("returns the FIRST non-terminal run in input order (server newest-first), without re-sorting", () => {
    const sharedCreatedAt = "2026-01-01T00:00:00Z";
    const runs = [
      run({ id: "r3", status: "COMPLETED", created_at: sharedCreatedAt }),
      run({ id: "r2", status: "RUNNING", created_at: sharedCreatedAt }),
      run({ id: "r1", status: "PENDING", created_at: sharedCreatedAt }),
    ];

    const result = newestActiveRun(runs);

    expect(result?.id).toBe("r2");
  });
});
