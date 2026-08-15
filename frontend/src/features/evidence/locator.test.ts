import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { COLUMNS_BY_GROUP } from "@/features/scenario-data/columns";
import { EVIDENCE_NAVIGATION_SCOPE, readTarget, toSearchParams } from "./locator";

const reference = {
  scenario_version_id: "11111111-1111-4111-8111-111111111111",
  checksum_algorithm: "sha256",
  checksum_schema_version: "1",
  checksum_digest: "digest",
  producing_run_version: null,
  baseline_schedule_version: null,
  group: "demand" as const,
  record_id: "demand-1",
  field: "amount",
  start_minute: 60,
  end_minute: 120,
  schema_version: "1",
};

describe("evidence locator", () => {
  it("round-trips an app-owned reference through search parameters", () => {
    const params = toSearchParams(reference);

    expect(params.toString()).toBe(
      "group=demand&record=demand-1&version=11111111-1111-4111-8111-111111111111&field=amount&start=60&end=120",
    );
    expect(readTarget(params)).toEqual({
      group: "demand",
      record: "demand-1",
      version: "11111111-1111-4111-8111-111111111111",
      field: "amount",
      start: 60,
      end: 120,
    });
  });

  it("rejects an unknown group instead of guessing a destination", () => {
    expect(readTarget(new URLSearchParams("group=overview&record=x&version=11111111-1111-4111-8111-111111111111"))).toBeNull();
  });

  it("rejects malformed cited versions", () => {
    expect(readTarget(new URLSearchParams("group=demand&record=x&version=latest"))).toBeNull();
  });

  it("drops an unusable window without voiding the citation it can still resolve", () => {
    const version = "11111111-1111-4111-8111-111111111111";
    const base = { group: "demand", record: "x", version } as const;

    // Empty strings coerce to 0 and used to fabricate a "0–0 minutes" window
    // the citation never claimed.
    expect(readTarget(new URLSearchParams(`group=demand&record=x&version=${version}&start=&end=`))).toEqual(base);
    // Inverted, half-specified, and unreadable ranges are all dropped — but the
    // group/record/version still address the record, so the jump survives.
    expect(readTarget(new URLSearchParams(`group=demand&record=x&version=${version}&start=960&end=510`))).toEqual(base);
    expect(readTarget(new URLSearchParams(`group=demand&record=x&version=${version}&start=510`))).toEqual(base);
    expect(readTarget(new URLSearchParams(`group=demand&record=x&version=${version}&start=abc&end=120`))).toEqual(base);
    // A well-formed window is still carried through.
    expect(readTarget(new URLSearchParams(`group=demand&record=x&version=${version}&start=510&end=960`)))
      .toEqual({ ...base, start: 510, end: 960 });
  });

  it("keeps every golden evidence group and field aligned with Scenario Data columns", () => {
    const directory = resolve(process.cwd(), "../backend/evals/golden/scheduling_compute");
    let checkedGroups = 0;
    let checkedFields = 0;
    for (const filename of readdirSync(directory).filter((name) => name.endsWith(".json"))) {
      const golden = JSON.parse(readFileSync(resolve(directory, filename), "utf8")) as {
        expected_evidence_refs?: string[];
      };
      for (const encoded of golden.expected_evidence_refs ?? []) {
        const [, group, , fieldAndRange] = encoded.split("|");
        const field = fieldAndRange?.split(":", 1)[0];
        expect(COLUMNS_BY_GROUP).toHaveProperty(group!);
        checkedGroups += 1;
        // `EvidenceRefV1.field` is optional and `evals/evaluators.py:112`
        // encodes an absent one as "" — a valid case that must not turn this
        // guard red. Only a field that is actually present is column-checked.
        if (!field) continue;
        expect(COLUMNS_BY_GROUP[group as keyof typeof COLUMNS_BY_GROUP].map((column) => column.key)).toContain(field);
        checkedFields += 1;
      }
    }
    // Anti-vacuity: emptying the goldens must not turn this into a green no-op.
    expect(checkedGroups).toBeGreaterThan(0);
    expect(checkedFields).toBeGreaterThan(0);
  });

  it("records the two deliberate navigation reductions as scope data", () => {
    expect(EVIDENCE_NAVIGATION_SCOPE.destination).toContain("NOT COVERED: Results");
    expect(EVIDENCE_NAVIGATION_SCOPE.versionMismatchRecovery).toContain("NOT COVERED: Open cited version");
  });
});
