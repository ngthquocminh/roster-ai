import { useQuery } from "@tanstack/react-query";

import type { EvidenceTarget } from "@/features/evidence/locator";
import { resolveEvidenceRecord } from "@/features/evidence/resolve";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";

export function useEvidenceRecord(scenarioId: string, target: EvidenceTarget | null) {
  const query = useQuery({
    queryKey: [
      "evidence-record",
      scenarioId,
      target?.group,
      target?.record,
      target?.version,
    ],
    queryFn: () => resolveEvidenceRecord(scenarioId, target!),
    enabled: Boolean(scenarioId && target),
    retry: false,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}
