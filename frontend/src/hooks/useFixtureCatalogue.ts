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
    // Fixture versions are immutable by contract (AD-4), so refetching on every
    // mount and window focus buys nothing and can only flip a good view into an
    // error one.
    staleTime: Infinity,
  });
}
