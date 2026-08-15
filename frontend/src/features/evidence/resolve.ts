import {
  resolveAssignment,
  resolveConstraint,
  resolveDemandInterval,
  resolveLock,
  resolveTask,
  resolveWorker,
  type AssignmentRecord,
  type ConstraintRecord,
  type DemandIntervalRecord,
  type LockRecord,
  type TaskRecord,
  type WorkerRecord,
} from "@/api/scenarioProjection";
import type { EvidenceGroup, EvidenceTarget } from "./locator";

export type EvidenceRecord =
  | TaskRecord
  | WorkerRecord
  | DemandIntervalRecord
  | AssignmentRecord
  | LockRecord
  | ConstraintRecord;

type Resolver = (scenarioId: string, recordId: string, versionId: string) => Promise<EvidenceRecord>;

export const RESOLVERS = {
  "work-areas-and-tasks": resolveTask,
  workers: resolveWorker,
  demand: resolveDemandInterval,
  "baseline-assignments": resolveAssignment,
  locks: resolveLock,
  "constraints-and-objectives": resolveConstraint,
} satisfies Record<EvidenceGroup, Resolver>;

export function resolveEvidenceRecord(
  scenarioId: string,
  target: EvidenceTarget,
): Promise<EvidenceRecord> {
  return RESOLVERS[target.group](scenarioId, target.record, target.version);
}
