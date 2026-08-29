import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApprovalRequestCard } from "./ApprovalRequestCard";
import { ApprovalDecisionDialog } from "./ApprovalDecisionDialog";
import { useApproval } from "@/hooks/useApproval";
import { useDecideApproval } from "@/hooks/useDecideApproval";
export function ApprovalDecisionPanel({ approvalId }: Readonly<{ approvalId: string }>) {
 const query = useApproval(approvalId); const mutation = useDecideApproval(approvalId); const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
 const triggerRef = useRef<HTMLButtonElement | null>(null);
 if (query.isPending) return <p className="text-sm text-muted-foreground">Loading approval; decisions are unavailable.</p>;
 if (query.isError || !query.data) return <p className="text-sm text-muted-foreground">Approval could not be loaded; reload before deciding.</p>;
 const approval = query.data; const presentedExpired = approval.state === "pending" && new Date(approval.expires_at) <= new Date();
 const decide = (value: "approve" | "reject") => mutation.mutate({ decision: value, expected_resource_version: approval.resource_version }, { onSettled: () => setDecision(null) });
 const error = mutation.error as { expected?: Record<string, unknown>; current?: Record<string, unknown> } | null;
 const openDialog = (value: "approve" | "reject", trigger: HTMLButtonElement) => { triggerRef.current = trigger; setDecision(value); };
 const closeDialog = (open: boolean) => {
  if (!open) {
   setDecision(null);
   setTimeout(() => triggerRef.current?.focus());
  }
 };
 return <section className="space-y-3"><ApprovalRequestCard approval={approval} />{mutation.isError ? <div role="status" className="text-sm text-muted-foreground"><p>The approval changed. Refresh, rerun, or inspect the current result before deciding again.</p>{error?.expected ? <p>Expected: {JSON.stringify(error.expected)}</p> : null}{error?.current ? <p>Current: {JSON.stringify(error.current)}</p> : null}</div> : null}{presentedExpired ? <Button aria-label={`Dismiss expired approval request ${approval.approval_id}; the operational baseline does not change.`} className="min-h-11" onClick={() => decide("reject")} type="button" variant="outline">Dismiss expired request</Button> : approval.state === "pending" ? <div className="flex gap-2"><Button className="min-h-11" onClick={(event) => openDialog("approve", event.currentTarget)} type="button" variant="destructive">Approve as baseline</Button><Button className="min-h-11" onClick={(event) => openDialog("reject", event.currentTarget)} type="button" variant="outline">Reject</Button></div> : <p className="text-sm">Terminal approval state: {approval.state}{approval.agent_run_id ? "; associated agent run was cancelled." : ""}</p>}<ApprovalDecisionDialog approval={approval} decision={decision ?? "approve"} open={decision !== null} onOpenChange={closeDialog} onConfirm={() => decision && decide(decision)} onRestoreFocus={() => setTimeout(() => triggerRef.current?.focus())} pending={mutation.isPending} /></section>;
}
