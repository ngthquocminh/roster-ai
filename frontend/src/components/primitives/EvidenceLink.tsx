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
    "inline-flex min-h-11 items-center gap-1 rounded-evidence outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
    // Icon-only (`verified`) has no visible text to underline -- the
    // `underline` class here previously painted a stray decoration line
    // under the bare icon. It gets a circular hover highlight instead (the
    // standard icon-button affordance); the text-link shape keeps its
    // existing underline + hover-color treatment, unchanged.
    verified
      ? "rounded-full justify-center hover:bg-muted"
      : "text-evidence-link underline underline-offset-4 hover:text-evidence-link/80",
    className,
  );
  // `verified` renders as the check icon ALONE (the full label moves to
  // `sr-only` text on the same control) -- one small button carrying the
  // link, not an icon beside a separate visible text link. The non-verified
  // shape (every other EvidenceLink call site) is untouched: visible text.
  const icon = verified ? <CheckIcon aria-hidden className="size-4 text-emerald-600 dark:text-emerald-400" /> : null;
  const content = verified ? (
    <>
      {icon}
      <span className="sr-only">{label}</span>
    </>
  ) : (
    label
  );

  if (href) {
    return (
      <a className={classes} href={href} id={id} onClick={onActivate}>
        {content}
      </a>
    );
  }

  return (
    <button className={classes} id={id} onClick={onActivate} type="button">
      {content}
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
