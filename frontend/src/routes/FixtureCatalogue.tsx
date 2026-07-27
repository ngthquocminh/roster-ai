import { useEffect, useRef } from "react";

import { FixtureCatalogueView } from "@/features/fixture-catalogue/FixtureCatalogueView";
import { useFixtureCatalogue } from "@/hooks/useFixtureCatalogue";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";


export function FixtureCatalogue() {
  const query = useFixtureCatalogue();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const errorStatus = getErrorStatus(query.error);

  useRedirectOnUnauthorized(errorStatus);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  if (errorStatus === 401) {
    return null;
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <h1
        className="mb-6 text-[28px] leading-[1.2] font-semibold outline-none"
        ref={headingRef}
        tabIndex={-1}
      >
        Fixture catalogue
      </h1>
      <FixtureCatalogueView
        data={query.data}
        isError={query.isError}
        isPending={query.isPending}
        onRetry={() => {
          void query.refetch();
        }}
      />
    </main>
  );
}
