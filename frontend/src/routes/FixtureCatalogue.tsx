import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";

import { FixtureCatalogueView } from "@/features/fixture-catalogue/FixtureCatalogueView";
import { useFixtureCatalogue } from "@/hooks/useFixtureCatalogue";
import { getErrorStatus } from "@/lib/errors";


export function FixtureCatalogue() {
  const query = useFixtureCatalogue();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const errorStatus = getErrorStatus(query.error);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (errorStatus === 401) {
      void navigate("/signin", {
        replace: true,
        state: { from: location.pathname + location.search },
      });
    }
  }, [errorStatus, location.pathname, location.search, navigate]);

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
        error={query.error}
        isError={query.isError}
        isPending={query.isPending}
        onRetry={() => {
          void query.refetch();
        }}
      />
    </main>
  );
}
