import { cn } from "@/lib/utils";

type EvidenceLinkBaseProps = Readonly<{
  group: string;
  id: string;
  record: string;
  fieldOrRange?: string;
  version: string;
  className?: string;
}>;

type EvidenceLinkProps = EvidenceLinkBaseProps & (
  | Readonly<{ href: string; onActivate?: () => void }>
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
  version,
}: EvidenceLinkProps) {
  const label = `Evidence: ${group} ${record}${fieldOrRange ? `, ${fieldOrRange}` : ""}, fixture ${version}`;
  const classes = cn(
    "inline-flex min-h-11 items-center rounded-evidence text-evidence-link underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
    className,
  );

  if (href) {
    return (
      <a className={classes} href={href} id={id} onClick={onActivate}>
        {label}
      </a>
    );
  }

  return (
    <button className={classes} id={id} onClick={onActivate} type="button">
      {label}
    </button>
  );
}
