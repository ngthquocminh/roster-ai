import { cn } from "@/lib/utils";

type EvidenceLinkProps = Readonly<{
  group: string;
  record: string;
  fieldOrRange?: string;
  version: string;
  href?: string;
  onActivate?: () => void;
  className?: string;
}>;

export function EvidenceLink({
  className,
  fieldOrRange,
  group,
  href,
  onActivate,
  record,
  version,
}: EvidenceLinkProps) {
  const label = `Evidence: ${group} ${record}${fieldOrRange ? `, ${fieldOrRange}` : ""}, fixture ${version}`;
  const classes = cn(
    "inline-flex min-h-11 items-center rounded-evidence text-evidence-link underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
    className,
  );

  if (href) {
    return (
      <a className={classes} href={href} onClick={onActivate}>
        {label}
      </a>
    );
  }

  return (
    <button className={classes} onClick={onActivate} type="button">
      {label}
    </button>
  );
}
