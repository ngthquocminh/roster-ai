import { useQuery } from "@tanstack/react-query";

import { getRunProvenance } from "@/api/provenance";

export const runProvenanceKey = (runId?: string) =>
  runId ? ["run-provenance", runId] as const : ["run-provenance"] as const;

export function useRunProvenance(runId: string) {
  return useQuery({
    queryKey: runProvenanceKey(runId),
    queryFn: () => getRunProvenance(runId),
    enabled: Boolean(runId),
  });
}
