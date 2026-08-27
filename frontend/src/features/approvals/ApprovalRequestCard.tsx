import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";

export type ApprovalRequestCardItem = {
  approval_id: string;
  state: "pending" | "consumed" | "rejected" | "expired" | "stale";
  schedule_run_id: string;
  candidate_schedule_version_id: string;
  baseline_schedule_version: string | null;
  consequence_summary: string;
  policy_version: string;
  expires_at: string;
};

export function ApprovalRequestCard({ approval, now = new Date() }: Readonly<{
  approval: ApprovalRequestCardItem;
  now?: Date;
}>) {
  const presentedState = approval.state === "pending" && new Date(approval.expires_at) <= now
    ? "expired"
    : approval.state;
  const stateLabel = presentedState.replaceAll("_", " ");

  return (
    <section aria-label="Approval request" className="rounded-xl border p-4 space-y-3">
      <div>
        <h3 className="font-semibold">Approval request</h3>
        <p className="text-sm text-muted-foreground">State: {stateLabel}</p>
      </div>
      <dl className="grid gap-3 text-sm md:grid-cols-2">
        <div><dt className="text-muted-foreground">Approval ID</dt><dd><IdentifierCopyButton identifierType="Approval ID" value={approval.approval_id} /></dd></div>
        <div><dt className="text-muted-foreground">Schedule run ID</dt><dd><IdentifierCopyButton identifierType="Schedule run ID" value={approval.schedule_run_id} /></dd></div>
        <div><dt className="text-muted-foreground">Candidate version</dt><dd><IdentifierCopyButton identifierType="Candidate version" value={approval.candidate_schedule_version_id} /></dd></div>
        <div><dt className="text-muted-foreground">Baseline version</dt><dd>{approval.baseline_schedule_version ? <IdentifierCopyButton identifierType="Baseline version" value={approval.baseline_schedule_version} /> : "No current baseline"}</dd></div>
        <div><dt className="text-muted-foreground">Policy version</dt><dd>{approval.policy_version}</dd></div>
        <div><dt className="text-muted-foreground">Expires at</dt><dd>{new Date(approval.expires_at).toLocaleString()}</dd></div>
      </dl>
      <p className="text-sm">{approval.consequence_summary}</p>
    </section>
  );
}
