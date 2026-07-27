/** Thin TanStack Query wrappers around the immutable catalogue API. */
import { useQuery } from "@tanstack/react-query";

import { listFixtureVersions } from "@/api/scenarioCatalogue";


export const fixtureCatalogueQueryKey = ["fixture-catalogue"] as const;

export function useFixtureCatalogue() {
  return useQuery({
    queryKey: fixtureCatalogueQueryKey,
    queryFn: listFixtureVersions,
  });
}
