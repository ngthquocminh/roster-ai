import { useState } from "react";
import { NavLink, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { useSignOut } from "@/hooks/useSession";
import { USER_ERROR_COPY } from "@/lib/errors";

/**
 * Persistent global nav (UI-SPEC Application Structure, tier 1) — the only
 * *global* nav destination in Phase 1: Editor/Runs/Results are
 * scenario-scoped and meaningless without a `:scenarioId`, so they live in
 * ScenarioLayout's tab nav instead of here (see RESEARCH.md's flat-nav
 * anti-pattern warning).
 *
 * The bar is session-aware (Story 1.2's BFF auth) — the Sign out button is
 * the one piece of session UI it carries; everything else stays unchanged.
 */
export function AppBar() {
  const navigate = useNavigate();
  const signOut = useSignOut();
  const [signOutFailed, setSignOutFailed] = useState(false);

  async function handleSignOut() {
    setSignOutFailed(false);
    try {
      const { postLogoutRedirectUrl } = await signOut.mutateAsync();
      if (postLogoutRedirectUrl) {
        window.location.href = postLogoutRedirectUrl;
        return;
      }
      navigate("/signin", { replace: true });
    } catch {
      setSignOutFailed(true);
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-[#F5F5F5] px-6">
      <span className="text-sm font-semibold text-foreground">ShiftMind</span>
      <div className="flex items-center gap-3">
        {signOutFailed && (
          <span className="text-sm text-destructive">
            {USER_ERROR_COPY.connection.title}
          </span>
        )}
        <NavLink
          to="/"
          end
          className="text-sm font-medium text-[#4F46E5] hover:underline"
        >
          Home
        </NavLink>
        <Button
          type="button"
          variant="outline"
          disabled={signOut.isPending}
          onClick={handleSignOut}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
