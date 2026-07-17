/**
 * CONS-01 constraint input box (UI-SPEC E4) — Textarea + "Apply Constraint",
 * status-branching for CONS-05 (503-vs-422, keyed strictly off
 * `response.status`, never error message text), and the Input-preservation
 * rule that generalizes CONS-04 across every non-full-success outcome.
 *
 * Closest analog: `CreateScenarioDialog.tsx` (controlled state,
 * `canSubmit` derivation, whole-form-disables-during-submit,
 * status-branch-on-`error.status`) — copied structurally, but its
 * unconditional `onSuccess: () => resetForm()` clear does NOT transfer
 * here. `POST /constraints` always returns 200 for rejected-only /
 * clarification / no-match outcomes (they are not HTTP errors), so
 * "request succeeded" and "should clear the textarea" are two different
 * conditions in this component, unlike `CreateScenarioDialog`. The clear
 * condition is evaluated against the RESPONSE BODY inside this component's
 * own `.mutate(text, { onSuccess: (data) => {...} })` callback — never
 * inside `useApplyConstraint`'s own `onSuccess` (which only invalidates).
 *
 * The 503 path throws before any 200 body exists, so it renders
 * `ProviderDownBanner` here directly rather than going through
 * `onOutcome`/the transcript — it is never a transcript entry (T-02-14).
 */
import * as React from "react";
import { LoaderCircle } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useApplyConstraint } from "@/hooks/useApplyConstraint";
import { getErrorStatus } from "@/lib/errors";
import { ProviderDownBanner } from "./ProviderDownBanner";
import type { TranscriptEntryData } from "./ConstraintTranscript";

const MAX_LENGTH = 2000;
const COUNTER_THRESHOLD = 1800;

function freshId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function ConstraintInput({
  scenarioId,
  onOutcome,
}: {
  scenarioId: string;
  onOutcome: (entry: TranscriptEntryData) => void;
}) {
  const [text, setText] = React.useState("");
  const applyConstraint = useApplyConstraint(scenarioId);

  const isSubmitting = applyConstraint.isPending;
  const canSubmit =
    text.trim().length > 0 && text.length <= MAX_LENGTH && !isSubmitting;

  const applyErrorStatus = getErrorStatus(applyConstraint.error);
  const isProviderDown = applyErrorStatus === 503;
  // Structural backstop only (UI-SPEC E4/422) — client-side length gating
  // above makes this unreachable in the ordinary flow, but the server
  // remains the source of truth (ASVS V5), so the branch stays. Keyed off
  // `status`, never error message text (T-02-14 discriminator).
  const isValidationError = applyErrorStatus === 422;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    applyConstraint.mutate(text, {
      onSuccess: (data) => {
        onOutcome({ id: freshId(), submittedText: text, response: data });
        // Input-preservation rule (generalizes CONS-04): clear ONLY on a
        // genuine full apply with nothing rejected and no pending
        // clarification. Rejected-only, mixed applied+rejected, clarification,
        // and no-match outcomes all preserve the typed text — a rejected
        // fragment means part of what the user typed still needs attention
        // (WR-01).
        if (
          data.applied.length > 0 &&
          data.rejected.length === 0 &&
          data.clarification_needed === null
        ) {
          setText("");
        }
      },
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <Textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        disabled={isSubmitting}
        placeholder="e.g. keep at least 2 workers on Pick at all times"
        aria-label="Constraint text"
      />
      <div className="flex items-center justify-between gap-2">
        <div>
          {text.length > COUNTER_THRESHOLD && (
            <span className="text-xs leading-[1.2] text-muted-foreground">
              {text.length}/{MAX_LENGTH}
            </span>
          )}
        </div>
        <Button type="submit" disabled={!canSubmit}>
          {isSubmitting && (
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          )}
          {isSubmitting ? "Applying…" : "Apply Constraint"}
        </Button>
      </div>

      {isProviderDown && <ProviderDownBanner />}
      {isValidationError && (
        <p className="text-xs text-destructive" data-testid="validation-error">
          That constraint text couldn't be validated. Edit it and try again.
        </p>
      )}
    </form>
  );
}
