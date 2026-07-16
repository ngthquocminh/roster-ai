/**
 * Page shell only for this plan (SHELL-03) — the Display-role page title per
 * UI-SPEC Typography (28px/600/1.2, used once per view). Plans 01-06/01-07
 * fill this with the scenario list table and the create-scenario dialog;
 * this plan only guarantees the route mounts.
 */
export function Home() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-[28px] leading-[1.2] font-semibold">Scenarios</h1>
    </div>
  );
}
