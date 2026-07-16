import { NavLink } from "react-router";

/**
 * Persistent global nav (UI-SPEC Application Structure, tier 1) — the only
 * *global* nav destination in Phase 1: Editor/Runs/Results are
 * scenario-scoped and meaningless without a `:scenarioId`, so they live in
 * ScenarioLayout's tab nav instead of here (see RESEARCH.md's flat-nav
 * anti-pattern warning).
 *
 * D-02 (no auth) means there is no session to represent, so this bar
 * deliberately carries nothing implying otherwise. Wordmark plus one link
 * only, at desktop widths (D-06) — cannot overflow its container.
 */
export function AppBar() {
  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-[#F5F5F5] px-6">
      <span className="text-sm font-semibold text-foreground">ShiftMind</span>
      <NavLink
        to="/"
        end
        className="text-sm font-medium text-[#4F46E5] hover:underline"
      >
        Home
      </NavLink>
    </header>
  );
}
