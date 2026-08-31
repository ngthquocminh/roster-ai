import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApprovalRequestCard } from "./ApprovalRequestCard";
import { ApprovalDecisionDialog } from "./ApprovalDecisionDialog";
import { useApproval } from "@/hooks/useApproval";
import { useDecideApproval } from "@/hooks/useDecideApproval";
import { getErrorCode } from "@/lib/errors";

type Decision = "approve" | "reject";

type Feedback = Readonly<{
  /** `outcome`: the decision landed. `blocked`: nothing changed, and why. */
  tone: "outcome" | "blocked";
  message: string;
  expected?: Record<string, unknown>;
  current?: Record<string, unknown>;
}>;

/**
 * What the server actually did, in the planner's words.
 *
 * A single `isError` branch is wrong here because terminalizing stale and
 * expired outcomes arrive as HTTP failures even though the governance state
 * changed. Reporting either as "the approval changed elsewhere" tells the
 * planner the opposite of what happened.
 */
function decisionFeedback(
  isSuccess: boolean,
  state: string | undefined,
  candidateVersion: string | undefined,
  priorBaselineVersion: string | null | undefined,
  isError: boolean,
  error: unknown,
): Feedback | null {
  if (isSuccess) {
    if (state === "consumed") {
      const replacement = priorBaselineVersion
        ? `replacing ${priorBaselineVersion}`
        : "replacing no previous baseline";
      return { tone: "outcome", message: `Candidate ${candidateVersion ?? "schedule"} is now the operational baseline, ${replacement}.` };
    }
    return { tone: "outcome", message: `Approval ${state ?? "decided"}. The operational baseline did not change.` };
  }
  if (!isError) return null;
  const context = error as { expected?: Record<string, unknown>; current?: Record<string, unknown> } | null;
  const expected = context?.expected;
  const current = context?.current;
  switch (getErrorCode(error)) {
    case "approval_expired":
      return { tone: "outcome", message: "This approval had already expired, so it was closed. The operational baseline did not change." };
    case "approval_stale":
      return { tone: "outcome", message: "This approval no longer matched the current plan, so it was closed as stale. The operational baseline did not change.", expected, current };
    case "approval_not_granted":
      return { tone: "blocked", message: "Current policy does not grant baseline approval." };
    case "approval_not_pending":
    case "stale_resource_version":
      return { tone: "blocked", message: "This approval changed elsewhere. Refresh, rerun, or inspect the current result before deciding again.", expected, current };
    case "agent_run_not_cancellable":
      return { tone: "blocked", message: "The agent run awaiting this approval changed. Refresh before deciding again.", expected, current };
    // The baseline moved under the decision, so the whole promotion rolled back
    // and the binding is still pending. Retrying with the SAME pinned version is
    // guaranteed to fail revalidation, so the copy must send the planner to a
    // refresh, never to a retry — and it carries the literal versions the
    // backend attaches, which the default arm would have dropped.
    case "stale_baseline_version":
      return { tone: "blocked", message: "The operational baseline changed while this decision was being applied, so nothing was promoted. Refresh to see the current baseline before deciding again.", expected, current };
    case "approval_payload_unreadable":
      return { tone: "blocked", message: "This approval's saved agent context could not be read, so nothing was promoted. Start a new request for this candidate.", expected, current };
    case "idempotency_key_conflict":
      return { tone: "blocked", message: "That decision was already submitted with different details. Refresh before deciding again." };
    default:
      return { tone: "blocked", message: "The decision could not be submitted. Try again; if the problem continues, reload the page." };
  }
}

function hasEntries(value: Record<string, unknown> | undefined): value is Record<string, unknown> {
  // `{}` is truthy in JavaScript, so a plain `value ? … : null` rendered a
  // literal `Expected: {}` whenever the problem carried no context.
  return value !== undefined && Object.keys(value).length > 0;
}

export function ApprovalDecisionPanel({ approvalId }: Readonly<{ approvalId: string }>) {
  const query = useApproval(approvalId);
  const mutation = useDecideApproval(approvalId);
  const [decision, setDecision] = useState<Decision | null>(null);
  // Retained separately so a *closing* reject dialog does not re-render as the
  // approve dialog: `decision` and `open` flip in the same commit while Radix
  // keeps `DialogContent` mounted through the exit.
  const [lastDecision, setLastDecision] = useState<Decision>("approve");
  const [now, setNow] = useState(() => Date.now());
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);

  const expiresAt = query.data ? new Date(query.data.expires_at).getTime() : null;
  useEffect(() => {
    // Re-render once the binding crosses `expires_at` while mounted, so the
    // controls swap to "Dismiss expired request" instead of offering an
    // approve the server will terminalize as expired.
    if (expiresAt === null) return;
    const delay = expiresAt - Date.now() + 1_000;
    // `setTimeout` stores its delay in a 32-bit signed int: anything past ~24.8
    // days overflows and fires on the NEXT TICK instead of never, which is the
    // opposite of what this timer is for. Approval windows are minutes; a
    // horizon beyond the cap cannot be crossed while this panel is mounted.
    if (delay <= 0 || delay > 2_147_483_647) return;
    const timer = setTimeout(() => setNow(Date.now()), delay);
    return () => clearTimeout(timer);
  }, [expiresAt]);

  // Decision 10: `!query.isSuccess` gates the controls. The positive check also
  // narrows `query.data`, so nothing below leans on `!data` being falsy.
  if (!query.isSuccess) {
    return (
      <p className="text-sm text-muted-foreground">
        {query.isError
          ? "Approval could not be loaded; reload before deciding."
          : "Loading approval; decisions are unavailable."}
      </p>
    );
  }

  const approval = query.data;
  const presentedExpired = approval.state === "pending" && new Date(approval.expires_at).getTime() <= now;
  const feedback = decisionFeedback(
    mutation.isSuccess,
    mutation.data?.state,
    mutation.data?.candidate_schedule_version_id,
    mutation.data?.baseline_schedule_version,
    mutation.isError,
    mutation.error,
  );

  const restoreFocus = () => {
    setTimeout(() => {
      const trigger = triggerRef.current;
      // A committed decision unmounts the trigger, and focusing a detached node
      // silently drops focus to <body>. Fall back to the panel itself.
      if (trigger?.isConnected) trigger.focus();
      else sectionRef.current?.focus();
    });
  };

  const decide = (value: Decision) =>
    mutation.mutate(
      { decision: value, expected_resource_version: approval.resource_version },
      { onSettled: () => setDecision(null) },
    );

  const openDialog = (value: Decision, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger;
    setLastDecision(value);
    setDecision(value);
  };

  const closeDialog = (open: boolean) => {
    if (!open) {
      setDecision(null);
      restoreFocus();
    }
  };

  return (
    <section className="space-y-3" data-approval-panel={approvalId} ref={sectionRef} tabIndex={-1}>
      <ApprovalRequestCard approval={approval} />
      {/* UX-DR32 / EXPERIENCE.md:189 -- the durable transition announces once,
          politely, whether it landed or was refused. */}
      <div aria-label="Approval decision status" aria-live="polite" role="status">
        {feedback ? (
          <div className="text-sm text-muted-foreground">
            <p>{feedback.message}</p>
            {hasEntries(feedback.expected) ? <p>Expected: {JSON.stringify(feedback.expected)}</p> : null}
            {hasEntries(feedback.current) ? <p>Current: {JSON.stringify(feedback.current)}</p> : null}
          </div>
        ) : null}
      </div>
      {presentedExpired ? (
        <Button
          aria-label={`Dismiss expired approval request ${approval.approval_id}; the operational baseline does not change.`}
          className="min-h-11"
          disabled={mutation.isPending}
          onClick={() => decide("reject")}
          type="button"
          variant="outline"
        >
          Dismiss expired request
        </Button>
      ) : approval.state === "pending" ? (
        <div className="flex gap-2">
          <Button
            className="min-h-11"
            onClick={(event) => openDialog("approve", event.currentTarget)}
            type="button"
            variant="destructive"
          >
            Approve as baseline
          </Button>
          <Button
            className="min-h-11"
            onClick={(event) => openDialog("reject", event.currentTarget)}
            type="button"
            variant="outline"
          >
            Reject
          </Button>
        </div>
      ) : (
        <p className="text-sm">
          Terminal approval state: {approval.state}
          {approval.state === "consumed"
            ? `; promoted ${approval.candidate_schedule_version_id}${approval.baseline_schedule_version ? ` replacing ${approval.baseline_schedule_version}` : " replacing no previous baseline"}.`
            : ""}
          {/* A CONSUMED binding RESUMED its run (TX2 sets `agent_running`); only
              the non-promoting terminal outcomes cancel it. Guarding this clause
              on `agent_run_id` alone stated the opposite of what happened on the
              one transition this story exists to introduce. */}
          {approval.agent_run_id && approval.state !== "consumed" ? "; associated agent run was cancelled." : ""}
          {approval.agent_run_id && approval.state === "consumed" ? " The associated agent run was resumed." : ""}
        </p>
      )}
      <ApprovalDecisionDialog
        approval={approval}
        decision={decision ?? lastDecision}
        onConfirm={() => decision && decide(decision)}
        onOpenChange={closeDialog}
        onRestoreFocus={restoreFocus}
        open={decision !== null}
        pending={mutation.isPending}
      />
    </section>
  );
}
