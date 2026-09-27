import { CheckIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type EvidenceLinkBaseProps = Readonly<{
  group: string;
  id: string;
  record: string;
  fieldOrRange?: string;
  version: string;
  className?: string;
  // Prepends a small decorative check ahead of the link, folding what used to
  // be a separate "Verified: ..." text node into this one control instead of
  // duplicating it.
  verified?: boolean;
}>;

// Exactly one activation mechanism, enforced at compile time in BOTH directions.
// Neither prop leaves an inert focusable control; both props attach a handler to
// a real anchor, so activating it runs the handler AND performs the navigation.
type EvidenceLinkProps = EvidenceLinkBaseProps & (
  | Readonly<{ href: string; onActivate?: never }>
  | Readonly<{ href?: never; onActivate: () => void }>
);

export function EvidenceLink({
  className,
  fieldOrRange,
  group,
  href,
  id,
  onActivate,
  record,
  verified = false,
  version,
}: EvidenceLinkProps) {
  // `verified` prefixes the accessible name itself (not just an aria-hidden
  // icon) -- a screen reader user must still hear "verified", the same
  // meaning the old separate "Verified: ..." text node carried, not lose it
  // to a decorative-only glyph.
  const label = `${verified ? "Verified Evidence" : "Evidence"}: ${group} ${record}${fieldOrRange ? `, ${fieldOrRange}` : ""}, fixture ${version}`;
  const classes = cn(
    "inline-flex min-h-11 items-center gap-1 rounded-evidence text-evidence-link underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
    className,
  );
  const icon = verified ? <CheckIcon aria-hidden className="size-4 text-emerald-600 dark:text-emerald-400" /> : null;

  if (href) {
    return (
      <a className={classes} href={href} id={id} onClick={onActivate}>
        {icon}
        {label}
      </a>
    );
  }

  return (
    <button className={classes} id={id} onClick={onActivate} type="button">
      {icon}
      {label}
    </button>
  );
}

// The many-evidence-rows case (e.g. a `worker_count`-style claim): the
// mechanism that produced the value already verified every row server-side,
// so a per-row link list adds nothing a planner can act on. This renders only
// the success indicator, accessibly labelled rather than a purely decorative
// glyph, with no navigation target. No `min-h-11` here (unlike `EvidenceLink`):
// that sizing is a touch-target minimum for an interactive control, and this
// span is neither a link nor a button.
export function VerifiedMark({ className }: Readonly<{ className?: string }>) {
  return (
    <span className={cn("inline-flex items-center", className)} role="img" aria-label="Verified">
      <CheckIcon aria-hidden className="size-4 text-emerald-600 dark:text-emerald-400" />
    </span>
  );
}
