/**
 * The honest not-built-yet surface (UI-SPEC Copywriting Contract). Shared by
 * all three scenario-scoped placeholders (Editor/Runs/Results) in this
 * phase. Renders fixed literal copy naming the view and stating it ships in
 * a later phase — contains no mock scenario/run/schedule data. A placeholder
 * that looks populated would be indistinguishable from a real view that is
 * broken, so this component is deliberately, visibly empty beneath the copy.
 */
export function PlaceholderView({ viewName }: { viewName: string }) {
  return (
    <div className="px-6 py-8">
      <h2 className="text-[20px] leading-[1.2] font-semibold">
        {viewName} — not built yet
      </h2>
      <p className="mt-2 text-sm leading-[1.5] text-muted-foreground">
        This view ships in a later phase of the v0.4 milestone.
      </p>
    </div>
  );
}
