/** Thin TanStack Query wrappers around the immutable catalogue API. */
import { useQuery } from "@tanstack/react-query";

import { listFixtureVersions } from "@/api/scenarioCatalogue";


export const fixtureCatalogueQueryKey = ["fixture-catalogue"] as const;

export function useFixtureCatalogue() {
  return useQuery({
    queryKey: fixtureCatalogueQueryKey,
    queryFn: listFixtureVersions,
    // Match useSession: a 401 or 404 is terminal, so retrying three times with
    // backoff only delays the sign-in redirect behind ~7s of spinner.
    retry: false,
    // Deliberately NO staleTime. Individual scenario_version rows are immutable
    // (AD-4), but this *collection* is not — importing a fixture adds rows. More
    // importantly, refetchOnMount/WindowFocus/Reconnect are all staleness-gated,
    // so staleTime: Infinity would suppress every automatic refetch and make the
    // cached-stale state (AC #2: isError with data still cached) unreachable in
    // normal use. The background refetch is what produces that state.
  });
}
