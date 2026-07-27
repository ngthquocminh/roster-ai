import { Link } from "react-router";

import type { FixtureCatalogueEntry } from "@/api/scenarioCatalogue";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { USER_ERROR_COPY } from "@/lib/errors";


type FixtureCatalogueViewProps = Readonly<{
  data: FixtureCatalogueEntry[] | undefined;
  error: unknown;
  isError: boolean;
  isPending: boolean;
  onRetry: () => void;
}>;

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
        <thead className="border-b bg-muted/40">
          <tr>
            <th className="w-[28%] px-3 py-3 font-medium" scope="col">
              Scenario name
            </th>
            <th className="w-[34%] px-3 py-3 font-medium" scope="col">
              Scenario ID
            </th>
            <th className="w-[16%] px-3 py-3 font-medium" scope="col">
              Fixture version
            </th>
            <th className="w-[22%] px-3 py-3 font-medium" scope="col">
              Imported at
            </th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr
              className="border-b last:border-b-0 hover:bg-muted/40"
              key={entry.scenario_version_id}
            >
              <td className="px-3 py-2">
                <Link
                  className="inline-flex min-h-11 items-center break-words text-primary underline underline-offset-4 outline-none focus-visible:rounded-sm focus-visible:ring-3 focus-visible:ring-ring/50"
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
    <div aria-busy="true" aria-live="polite">
      <p className="mb-3 text-sm text-muted-foreground">
        Loading predefined scenarios…
      </p>
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full table-fixed text-left text-sm">
          <caption className="sr-only">
            Predefined scenario fixture versions
          </caption>
          <thead className="border-b bg-muted/40">
            <tr>
              {["Scenario name", "Scenario ID", "Fixture version", "Imported at"].map(
                (heading) => (
                  <th className="px-3 py-3 font-medium" key={heading} scope="col">
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {[0, 1, 2].map((row) => (
              <tr className="border-b last:border-b-0" key={row}>
                {[0, 1, 2, 3].map((cell) => (
                  <td className="h-[60px] px-3 py-2" key={cell}>
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
    <Alert className="border-destructive/40">
      <AlertTitle>{USER_ERROR_COPY.connection.title}</AlertTitle>
      <AlertDescription>
        <p>{USER_ERROR_COPY.connection.description}</p>
        <Button
          className="mt-3 min-h-11"
          onClick={onRetry}
          type="button"
          variant="outline"
        >
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function FixtureCatalogueView({
  data,
  error,
  isError,
  isPending,
  onRetry,
}: FixtureCatalogueViewProps) {
  void error;
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
        <div
          className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 px-3 py-2"
          role="status"
        >
          <span className="text-sm">
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
          <p className="text-sm text-muted-foreground">
            No predefined scenarios are available.
          </p>
        )}
      </div>
    );
  }
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No predefined scenarios are available.
      </p>
    );
  }
  return <CatalogueTable entries={entries} />;
}
