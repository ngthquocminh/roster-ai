/**
 * D-06/RES-06 — the coverage-honesty caveat, rendered directly above the
 * stat row so a warning is read before the numbers it qualifies.
 *
 * Structural analog: `ErrorBanner.tsx` (same Alert/AlertTitle/AlertDescription
 * shape). Deliberate deviation from that analog: `ErrorBanner` renders FIXED
 * copy regardless of the error's contents, because backend internals must
 * never reach JSX (ASVS V7). `SolveResult.warnings` strings are the opposite
 * case — they are the solver's own already-display-ready, non-user-controlled
 * text, so rendering them verbatim as plain JSX text children is correct and
 * safe here (React's default text-node escaping is the mitigation; no raw-HTML
 * injection sink is used anywhere in this file).
 *
 * Renders nothing (not even empty chrome) when `warnings` is empty — callers
 * must guard the one call site with `warnings ?? []` for pre-warnings-era
 * cached rows.
 */
import { TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <Alert variant="default" className="mx-0 my-2 max-w-3xl">
      <TriangleAlert aria-hidden="true" />
      <AlertTitle>Heads up</AlertTitle>
      <AlertDescription className="whitespace-normal break-words">
        {warnings.map((warning) => (
          <p key={warning}>{warning}</p>
        ))}
      </AlertDescription>
    </Alert>
  );
}
