import { Button } from "@/components/ui/button";

export const PAGE_SIZE = 50;

type Props = Readonly<{
  cursor: number;
  itemCount: number;
  nextCursor: number | null;
  matchingCount: number;
  totalCount: number;
  hasFilters: boolean;
  onPageChange: (cursor: number) => void;
}>;

function countCopy({ cursor, hasFilters, itemCount, matchingCount, totalCount }: Omit<Props, "nextCursor" | "onPageChange">) {
  if (itemCount === 0) {
    // A stale/out-of-range cursor (e.g. a bookmarked URL after the filtered set shrank) can leave
    // matchingCount > 0 with nothing on this particular page — report 0 rather than an inverted range.
    return hasFilters
      ? `Showing 0 of ${matchingCount.toLocaleString()} matching (${totalCount.toLocaleString()} total)`
      : `Showing 0 of ${totalCount.toLocaleString()}`;
  }
  const start = cursor + 1;
  const end = cursor + itemCount;
  return hasFilters
    ? `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${matchingCount.toLocaleString()} matching (${totalCount.toLocaleString()} total)`
    : `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${totalCount.toLocaleString()}`;
}

export function PaginationControls(props: Props) {
  const { cursor, matchingCount, nextCursor, onPageChange } = props;
  const previous = Math.max(0, cursor - PAGE_SIZE);
  const last = Math.max(0, Math.floor((matchingCount - 1) / PAGE_SIZE) * PAGE_SIZE);
  const copy = countCopy(props);
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">{copy}</p>
      <div aria-label="Table pages" className="flex flex-wrap gap-2" role="group">
        <Button className="min-h-11" disabled={cursor === 0} onClick={() => onPageChange(0)} type="button" variant="outline">First</Button>
        <Button className="min-h-11" disabled={cursor === 0} onClick={() => onPageChange(previous)} type="button" variant="outline">Previous</Button>
        <Button className="min-h-11" disabled={nextCursor === null} onClick={() => { if (nextCursor !== null) onPageChange(nextCursor); }} type="button" variant="outline">Next</Button>
        <Button className="min-h-11" disabled={cursor === last} onClick={() => onPageChange(last)} type="button" variant="outline">Last</Button>
      </div>
      <span aria-live="polite" className="sr-only" role="status">{copy}</span>
    </div>
  );
}
