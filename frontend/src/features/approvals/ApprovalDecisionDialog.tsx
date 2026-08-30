import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { Approval } from "@/api/approvals";
export function ApprovalDecisionDialog({ approval, decision, open, onOpenChange, onConfirm, onRestoreFocus, pending }: Readonly<{ approval: Approval; decision: "approve" | "reject"; open: boolean; onOpenChange: (value: boolean) => void; onConfirm: () => void; onRestoreFocus: () => void; pending: boolean }>) {
 const approve = decision === "approve"; const baseline = approval.baseline_schedule_version ?? "no current baseline";
 const confirm = approve ? `Approve candidate ${approval.candidate_schedule_version_id} as baseline replacing ${baseline}` : `Reject approval request ${approval.approval_id}; the operational baseline does not change.`;
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent onCloseAutoFocus={(event) => { event.preventDefault(); onRestoreFocus(); }}><DialogHeader><DialogTitle>{approve ? "Approve candidate as baseline" : "Reject approval request"}</DialogTitle><DialogDescription>{approval.consequence_summary}</DialogDescription></DialogHeader><DialogFooter><DialogClose asChild><Button className="min-h-11" variant="outline">Cancel</Button></DialogClose><Button aria-label={confirm} className="min-h-11" disabled={pending} onClick={onConfirm} variant={approve ? "destructive" : "outline"}>{approve ? "Approve as baseline" : "Reject"}</Button></DialogFooter></DialogContent></Dialog>;
}
