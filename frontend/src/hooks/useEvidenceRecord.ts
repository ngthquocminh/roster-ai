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
    queryFn: () => {
      // `enabled` already gates this, but a non-null assertion made the query
      // function's correctness depend on a neighbouring option rather than on
      // anything the type system checks.
      if (!target) throw new Error("useEvidenceRecord: no evidence target");
      return resolveEvidenceRecord(scenarioId, target);
    },
    enabled: Boolean(scenarioId && target),
    retry: false,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}
