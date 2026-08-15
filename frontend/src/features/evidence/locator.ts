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

// The slug is a URL segment, not planner-facing copy. The tabs for the same six
// groups render human labels, so the evidence region must too — otherwise the
// heading and the screen-reader name say "constraints-and-objectives" beside a
// tab that says "Constraints and objectives".
export const EVIDENCE_GROUP_LABEL = {
  "work-areas-and-tasks": "Work areas and tasks",
  workers: "Workers",
  demand: "Demand",
  "baseline-assignments": "Baseline assignments",
  locks: "Locks",
  "constraints-and-objectives": "Constraints and objectives",
} as const satisfies Record<EvidenceGroup, string>;

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

// `null` means "present but unreadable" and `undefined` means "absent". An empty
// string is NOT absent: `Number("")` is 0, which would pass an integer check and
// fabricate a `0–0 minutes` window that the citation never claimed.
function readOptionalMinute(params: URLSearchParams, key: "start" | "end") {
  const raw = params.get(key);
  if (raw === null) return undefined;
  if (raw.trim() === "") return null;
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
  const field = searchParams.get("field") || undefined;
  // An unreadable, half-specified, or inverted window is dropped rather than
  // announced: `targetDetail` would otherwise state a range the citation does
  // not support. The record itself still resolves — the group, record and
  // version are what address it, so a bad range must not void the whole jump.
  const windowIsUsable =
    start !== null
    && end !== null
    && (start === undefined) === (end === undefined)
    && (start === undefined || end === undefined || start <= end);
  return {
    group: requestedGroup as EvidenceGroup,
    record,
    version,
    ...(field ? { field } : {}),
    ...(windowIsUsable && start !== undefined && start !== null ? { start } : {}),
    ...(windowIsUsable && end !== undefined && end !== null ? { end } : {}),
  };
}
