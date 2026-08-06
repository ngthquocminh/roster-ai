/** Thin generated-contract wrappers for immutable scenario projection reads. */
import { client } from "./client";
import type { paths } from "./schema";

export type ScenarioOverview = paths["/api/v1/scenarios/{scenario_id}/projection"]["get"]["responses"][200]["content"]["application/json"];
export type TaskPage = paths["/api/v1/scenarios/{scenario_id}/projection/work-areas-and-tasks"]["get"]["responses"][200]["content"]["application/json"];
export type WorkerPage = paths["/api/v1/scenarios/{scenario_id}/projection/workers"]["get"]["responses"][200]["content"]["application/json"];
export type DemandIntervalPage = paths["/api/v1/scenarios/{scenario_id}/projection/demand"]["get"]["responses"][200]["content"]["application/json"];
export type AssignmentPage = paths["/api/v1/scenarios/{scenario_id}/projection/baseline-assignments"]["get"]["responses"][200]["content"]["application/json"];
export type LockPage = paths["/api/v1/scenarios/{scenario_id}/projection/locks"]["get"]["responses"][200]["content"]["application/json"];
export type ConstraintPage = paths["/api/v1/scenarios/{scenario_id}/projection/constraints-and-objectives"]["get"]["responses"][200]["content"]["application/json"];
export type TaskQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/work-areas-and-tasks"]["get"]["parameters"]["query"]>;
export type WorkerQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/workers"]["get"]["parameters"]["query"]>;
export type DemandQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/demand"]["get"]["parameters"]["query"]>;
export type AssignmentQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/baseline-assignments"]["get"]["parameters"]["query"]>;
export type LockQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/locks"]["get"]["parameters"]["query"]>;
export type ConstraintQuery = NonNullable<paths["/api/v1/scenarios/{scenario_id}/projection/constraints-and-objectives"]["get"]["parameters"]["query"]>;

function compactQuery<T extends object>(params: T): T {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined),
  ) as T;
}

export async function getScenarioOverview(scenarioId: string): Promise<ScenarioOverview> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection", { params: { path: { scenario_id: scenarioId } } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getWorkAreasAndTasks(scenarioId: string, params: TaskQuery = {}): Promise<TaskPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/work-areas-and-tasks", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getWorkers(scenarioId: string, params: WorkerQuery = {}): Promise<WorkerPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/workers", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getDemand(scenarioId: string, params: DemandQuery = {}): Promise<DemandIntervalPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/demand", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getBaselineAssignments(scenarioId: string, params: AssignmentQuery = {}): Promise<AssignmentPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/baseline-assignments", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getLocks(scenarioId: string, params: LockQuery = {}): Promise<LockPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/locks", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getConstraintsAndObjectives(scenarioId: string, params: ConstraintQuery = {}): Promise<ConstraintPage> {
  const { data, error, response } = await client.GET("/api/v1/scenarios/{scenario_id}/projection/constraints-and-objectives", { params: { path: { scenario_id: scenarioId }, query: compactQuery(params) } });
  if (error) throw { ...error, status: response.status };
  return data;
}
