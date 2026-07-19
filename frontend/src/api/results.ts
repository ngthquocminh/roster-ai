/**
 * Typed wrapper for GET /runs/{run_id}/result (RES-01..RES-03, RES-06).
 *
 * DEVIATION from the codebase's "types generated, never hand-written"
 * convention (see api/client.ts header comment): this endpoint has no
 * FastAPI response_model, so openapi-typescript cannot type it — schema.d.ts
 * resolves its response to `{ [key: string]: unknown }`. The `RunResult`
 * interface below is hand-authored field-for-field against
 * backend/services/serialize.py's serialize_result() (the actual wire
 * contract) — not against docs/API.md (documentation, can drift) and not
 * against schema.d.ts (doesn't model this response at all). Keep this type
 * in sync manually if serialize_result()'s shape ever changes. `data` is
 * cast to `RunResult` exactly once, here — every other call site in this
 * codebase must consume the resulting typed value, never re-cast an
 * untyped/unknown response of its own.
 */
import { client } from "./client";

export interface CoverageStat {
  required_h: number | null;
  served_h: number | null;
  pct: number | null;
}

export interface ScheduleRow {
  contact_id: string;
  member_name: string;
  task_id: string;
  function: string;
  shift_id: string;
  start_h: number;
  end_h: number;
}

export interface RunResult {
  status: string;
  metrics: {
    total_cost: number | null;
    total_unmet_hours: number | null;
    scheduled_shifts: number;
    scheduled_members: number;
    coverage_by_function: Record<string, CoverageStat>;
    coverage_by_day: Record<string, number | null>;
  };
  stats: {
    status: string;
    wall_time_s: number | null;
    unmet_objective_hours: number | null;
    cost_objective: number | null;
  };
  schedule: ScheduleRow[];
  // RES-06 — warnings is always a real array at runtime (serialize.py
  // always includes the key; domain/result.py defaults it to []), even
  // though schema.d.ts is silent on this response entirely.
  warnings: string[];
}

export async function getRunResult(runId: string): Promise<RunResult> {
  const { data, error, response } = await client.GET("/runs/{run_id}/result", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    // T-1-02: attach the HTTP status so callers can branch on it (e.g. 409
    // before COMPLETED, though callers should gate on RunOut.status first).
    throw { status: response.status, ...error };
  }
  return data as RunResult;
}
