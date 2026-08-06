import { useId } from "react";

export function WorkspaceTabPlaceholder({ description, title }: Readonly<{ title: string; description: string }>) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-6 rounded-lg border border-dashed p-6">
      <h2 className="text-lg font-medium" id={headingId}>{title}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
    </section>
  );
}
