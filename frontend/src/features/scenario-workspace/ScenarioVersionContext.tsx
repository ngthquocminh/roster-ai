import { ChevronLeft } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";

import type { ScenarioContext } from "@/api/scenarioCatalogue";


export function ScenarioVersionContext({
  context,
}: {
  context: ScenarioContext;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const baselineVersion =
    context.baseline_schedule_version ?? "Not established";

  return (
    <section aria-labelledby="scenario-context-heading">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h1
          className="min-w-0 break-words text-2xl font-semibold outline-none"
          id="scenario-context-heading"
          ref={headingRef}
          tabIndex={-1}
        >
          {context.scenario_name}
        </h1>
        <Link
          className="-mr-2 inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          to="/"
        >
          <ChevronLeft aria-hidden="true" className="size-4" />
          Change scenario
        </Link>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <div className="flex min-w-0 items-baseline gap-2">
          <dt className="text-muted-foreground">Scenario ID</dt>
          <dd className="min-w-0 break-all font-mono" title={context.scenario_id}>
            {context.scenario_id}
          </dd>
        </div>
        <div className="flex min-w-0 items-baseline gap-2">
          <dt className="text-muted-foreground">Fixture version</dt>
          <dd className="min-w-0 break-all font-mono" title={context.fixture_version}>
            {context.fixture_version}
          </dd>
        </div>
        <div className="flex min-w-0 items-baseline gap-2">
          <dt className="text-muted-foreground">Baseline version</dt>
          <dd className="min-w-0 break-all font-mono" title={baselineVersion}>
            {baselineVersion}
          </dd>
        </div>
      </dl>
    </section>
  );
}
