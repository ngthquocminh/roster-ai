import type { components } from "@/api/schema";
import type { ScenarioDataListGroup } from "@/features/scenario-data/columns";

type EvidenceReference = components["schemas"]["EvidenceRefV1"];

export type EvidenceGroup = EvidenceReference["group"];
export type EvidenceTarget = Readonly<{
  group: EvidenceGroup;
  record: EvidenceReference["record_id"];
  version: EvidenceReference["scenario_version_id"];
  field?: NonNullable<EvidenceReference["field"]>;
  start?: NonNullable<EvidenceReference["start_minute"]>;
  end?: NonNullable<EvidenceReference["end_minute"]>;
}>;

export const EVIDENCE_GROUP_TO_TAB = {
  "work-areas-and-tasks": "work-areas-and-tasks",
  workers: "workers",
  demand: "demand",
  "baseline-assignments": "baseline-assignments",
  locks: "locks",
  "constraints-and-objectives": "constraints-and-objectives",
} as const satisfies Record<EvidenceGroup, ScenarioDataListGroup>;

const groups = new Set<EvidenceGroup>(
  Object.keys(EVIDENCE_GROUP_TO_TAB) as EvidenceGroup[],
);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Scope as data: these reductions remain searchable and testable instead of
// quietly disappearing behind the currently reachable six-group vocabulary.
export const EVIDENCE_NAVIGATION_SCOPE = {
  destination: "Scenario Data is supported for every current EvidenceGroupV1. NOT COVERED: Results evidence navigation until Epic 3 creates run-scoped locators and a Results surface.",
  versionMismatchRecovery: "The selected and cited versions are named without retargeting. NOT COVERED: Open cited version, because each current fixture scenario has exactly one governed version.",
} as const;

export function toSearchParams(ref: EvidenceReference): URLSearchParams {
  const params = new URLSearchParams({
    group: ref.group,
    record: ref.record_id,
    version: ref.scenario_version_id,
  });
  if (ref.field) params.set("field", ref.field);
  if (ref.start_minute != null) params.set("start", String(ref.start_minute));
  if (ref.end_minute != null) params.set("end", String(ref.end_minute));
  return params;
}

function readOptionalMinute(params: URLSearchParams, key: "start" | "end") {
  const raw = params.get(key);
  if (raw === null) return undefined;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

export function readTarget(searchParams: URLSearchParams): EvidenceTarget | null {
  const requestedGroup = searchParams.get("group");
  const record = searchParams.get("record");
  const version = searchParams.get("version");
  if (!requestedGroup || !groups.has(requestedGroup as EvidenceGroup) || !record || !version || !uuidPattern.test(version)) {
    return null;
  }
  const start = readOptionalMinute(searchParams, "start");
  const end = readOptionalMinute(searchParams, "end");
  if (start === null || end === null) return null;
  const field = searchParams.get("field") || undefined;
  return {
    group: requestedGroup as EvidenceGroup,
    record,
    version,
    ...(field ? { field } : {}),
    ...(start === undefined ? {} : { start }),
    ...(end === undefined ? {} : { end }),
  };
}
