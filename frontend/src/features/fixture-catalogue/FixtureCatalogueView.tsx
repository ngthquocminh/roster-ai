import { Link } from "react-router";

import type { FixtureCatalogueEntry } from "@/api/scenarioCatalogue";
import { EmptyState } from "@/components/primitives/EmptyState";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { USER_ERROR_COPY } from "@/lib/errors";


type FixtureCatalogueViewProps = Readonly<{
  data: FixtureCatalogueEntry[] | undefined;
  isError: boolean;
  isPending: boolean;
  onRetry: () => void;
}>;

// Single source of truth for the column contract. The skeleton and the real
// table previously hand-duplicated these headers and had already drifted on
// width, so a table-fixed layout reflowed all four columns the moment data
// arrived — exactly the shift the skeleton exists to prevent.
const COLUMNS = [
  { label: "Scenario name", width: "w-[28%]" },
  { label: "Scenario ID", width: "w-[34%]" },
  { label: "Fixture version", width: "w-[16%]" },
  { label: "Imported at", width: "w-[22%]" },
] as const;

function CatalogueHead() {
  return (
    <thead className="border-b bg-muted/40">
      <tr>
        {COLUMNS.map((column) => (
          <th
            className={`${column.width} px-3 py-3 font-medium`}
            key={column.label}
            scope="col"
          >
            {column.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function CatalogueTable({
  entries,
}: {
  entries: FixtureCatalogueEntry[];
}) {
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full table-fixed text-left text-sm">
        <caption className="sr-only">
          Predefined scenario fixture versions
        </caption>
        <CatalogueHead />
        <tbody>
          {entries.map((entry) => (
            <tr
              className="border-b last:border-b-0 hover:bg-muted/40"
              key={entry.scenario_version_id}
            >
              <td className="px-3 py-2">
                <Link
                  className="inline-flex min-h-11 items-center break-words text-evidence-link underline underline-offset-4 outline-none focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50"
                  to={`/scenarios/${entry.scenario_id}`}
                >
                  {entry.scenario_name}
                </Link>
              </td>
              <td
                className="break-all px-3 py-2 font-mono text-xs"
                title={entry.scenario_id}
              >
                {entry.scenario_id}
              </td>
              <td
                className="break-all px-3 py-2 font-mono text-xs"
                title={entry.fixture_version}
              >
                {entry.fixture_version}
              </td>
              <td className="break-words px-3 py-2">
                {formatTimestamp(entry.imported_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoadingCatalogue() {
  return (
    <div>
      <p className="mb-3 text-sm text-muted-foreground">
        Loading predefined scenarios…
      </p>
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full table-fixed text-left text-sm">
          <caption className="sr-only">
            Predefined scenario fixture versions
          </caption>
          <CatalogueHead />
          <tbody>
            {[0, 1, 2].map((row) => (
              <tr className="border-b last:border-b-0" key={row}>
                {COLUMNS.map((column) => (
                  <td className="h-[60px] px-3 py-2" key={column.label}>
                    <Skeleton className="h-4 w-full max-w-36" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UnavailableCatalogue({ onRetry }: { onRetry: () => void }) {
  return (
    <InlineAlert
      action={
        <Button
          className="min-h-11"
          onClick={onRetry}
          type="button"
          variant="outline"
        >
          Retry
        </Button>
      }
      description={USER_ERROR_COPY.connection.description}
      title={USER_ERROR_COPY.connection.title}
      variant="destructive"
    />
  );
}

function EmptyCatalogue() {
  return <EmptyState explanation="No predefined scenarios are available." />;
}

function CatalogueBody({
  data,
  isError,
  isPending,
  onRetry,
}: FixtureCatalogueViewProps) {
  if (isPending) {
    return <LoadingCatalogue />;
  }
  if (isError && data === undefined) {
    return <UnavailableCatalogue onRetry={onRetry} />;
  }

  const entries = data ?? [];
  if (isError) {
    return (
      <div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 px-3 py-2">
          {/* Only the message is a live region — a control inside one gets
              re-announced on every update and can strand focus when the
              region's contents are swapped by the retry it triggered. */}
          <span className="text-sm" role="status">
            Saved catalogue — refresh unavailable
          </span>
          <Button
            className="min-h-11"
            onClick={onRetry}
            type="button"
            variant="outline"
          >
            Retry
          </Button>
        </div>
        {entries.length > 0 ? (
          <CatalogueTable entries={entries} />
        ) : (
          <EmptyCatalogue />
        )}
      </div>
    );
  }
  if (entries.length === 0) {
    return <EmptyCatalogue />;
  }
  return <CatalogueTable entries={entries} />;
}

export function FixtureCatalogueView(props: FixtureCatalogueViewProps) {
  // The live region wraps every state and is never unmounted. Previously
  // aria-live was mounted with its message already inside it, and live regions
  // announce mutations to an existing region rather than content present at
  // insertion — so nothing was announced on load *or* on completion.
  return (
    <div aria-busy={props.isPending} aria-live="polite">
      <CatalogueBody {...props} />
    </div>
  );
}
