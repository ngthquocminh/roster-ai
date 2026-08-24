import { client } from "./client";
import type { paths } from "./schema";

type AvailabilityRoute = paths["/api/v1/agent-availability"];
export type AgentAvailability =
  AvailabilityRoute["get"]["responses"][200]["content"]["application/json"];

export async function getAgentAvailability(
  scenarioId: string,
): Promise<AgentAvailability> {
  const { data, error, response } = await client.GET(
    "/api/v1/agent-availability",
    { params: { query: { scenario_id: scenarioId } } },
  );
  if (error) throw { ...error, status: response.status };
  return data;
}
