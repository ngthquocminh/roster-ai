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
    <section
      aria-labelledby="scenario-context-heading"
      className="rounded-lg border bg-card p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Scenario
          </p>
          <h1
            className="mt-1 break-words text-2xl font-semibold outline-none"
            id="scenario-context-heading"
            ref={headingRef}
            tabIndex={-1}
          >
            {context.scenario_name}
          </h1>
        </div>
        <Link
          className="inline-flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
          to="/"
        >
          Change scenario
        </Link>
      </div>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Scenario ID</dt>
          <dd
            className="mt-1 break-all font-mono text-xs"
            title={context.scenario_id}
          >
            {context.scenario_id}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Fixture version</dt>
          <dd
            className="mt-1 break-all font-mono text-xs"
            title={context.fixture_version}
          >
            {context.fixture_version}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted-foreground">Baseline version</dt>
          <dd
            className="mt-1 break-all font-mono text-xs"
            title={baselineVersion}
          >
            {baselineVersion}
          </dd>
        </div>
      </dl>
    </section>
  );
}
