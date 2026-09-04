"""TX2: consume, promote, audit, event, and resume in the caller transaction.

Unlike TX3's business-terminal outcomes, any failure after the first write must
escape the endpoint so the request dependency rolls the entire bundle back.
This module therefore never converts write faults into returned problem data.

WHY THE MECHANISM IS NOT SYMMETRIC WITH TX3'S
---------------------------------------------
`get_site_context` is a GENERATOR dependency: `with site_context(...) as
connection: yield connection`. FastAPI throws into it at the `yield` only when an
exception propagates out of the ENDPOINT FUNCTION. So:

* A route that catches an exception and ``return``s a problem response resumes
  the generator normally, and `engine.begin()`'s ``__exit__`` COMMITS everything
  written before the failure. At the database this is indistinguishable from
  success. TX3 depends on exactly that -- a `stale`/`expired` outcome has already
  written a terminal binding it must keep (Story 4.2 Decision 9).
* TX2 must never keep a partial bundle (FR19, NFR9, AR10, AR22), so its
  post-write failures are RAISED and left to escape. They are rendered by
  `api/main.py`'s registered handler, which runs after the dependency has
  unwound -- the rollback has already happened by the time the body is written.

"Raise it and catch it in the router" does NOT achieve this, and
``connection.rollback()`` inside an except arm does not either: `engine.begin()`
would commit a fresh empty transaction on exit, so it "works" only by accident.

Per-failure-mode table:

===============================================  ==========================
Situation                                        Result
===============================================  ==========================
`consume` returns None (concurrent decision)     raise, escape -> 409, rollback
`promote` returns None / IntegrityError          raise, escape -> 409, rollback
any DBAPIError inside the bundle                 propagate -> rollback
resume finds the run outside approval_required   escape -> 409, rollback
pending payload absent or not exactly one call   escape -> 500, rollback
every write succeeded                            RETURN -> the bundle commits
===============================================  ==========================

Pre-write refusals (`approval_not_pending` from the admission check,
`stale_resource_version`, `approval_not_found`, `idempotency_key_conflict`) are
detected before any write, so the transaction is healthy and the router keeps
catching and returning them -- which is also what lets the denial audit row
commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from application.app_version import APP_VERSION

from pydantic import TypeAdapter, ValidationError

from application.contracts.agent_runtime import AgentApprovalPendingV1, AgentTurnV1
from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.ports.conversation import ExecutedAgentRunV1
from application.ports.site_baseline import SiteBaselineV1
from application.use_cases.decide_approval import DecideApprovalError, PostWriteApprovalNotPendingError

SCOPE_CONTROLS = {
    "audit": "NOT COVERED: audit:write_fault_outcomes_owned_by_story_4_5",
    "baseline_supply": "NOT COVERED: baseline_supply:guarded_by_ead_8_not_wired",
    "resume": "NOT COVERED: resume:denied_decisions_have_no_producer",
}


class BaselineConcurrentlyMovedError(DecideApprovalError):
    code = "stale_baseline_version"


class ApprovalPayloadUnreadableError(DecideApprovalError):
    """An agent-backed binding's `pending_payload` cannot drive a resumed turn.

    `agent_run_id IS NOT NULL` does NOT imply `pending_payload IS NOT NULL`:
    `RequestApprovalCommandV1` declares them as two independent optionals, the
    column is nullable, and no CHECK ties them together. A missing payload, or
    one that does not carry exactly one pending call, is a server-side data
    integrity fault -- not a concurrency conflict and not planner error -- so it
    gets an honest 500 with a stable code instead of a bare `RuntimeError`
    surfacing as an undeclared generic `internal_error`. Like every other
    post-write failure it must escape, so TX2 rolls back whole.
    """

    code = "approval_payload_unreadable"


@dataclass(frozen=True)
class ResumeRequestV1:
    agent_run_id: UUID
    tool_call_id: str
    history: AgentTurnV1


@dataclass(frozen=True)
class PromotionResultV1:
    binding: ApprovalBindingV1
    baseline: SiteBaselineV1
    activity: ExecutedAgentRunV1 | None
    resume: ResumeRequestV1 | None


def promote_baseline(
    connection: Any,
    *,
    binding: ApprovalBindingV1,
    candidate: Any,
    actor_id: UUID,
    request_id: UUID,
    approvals: Any,
    baseline_writer: Any,
    audit_writer: Any,
    conversations: Any,
    occurred_at: datetime,
    app_version: str = APP_VERSION,
) -> PromotionResultV1:
    """Execute TX2 after the caller's shared revalidation returned valid."""
    if binding.state != "pending":
        raise AssertionError("promote_baseline requires a pending validated binding")
    if candidate is None:
        raise AssertionError("promote_baseline requires the candidate revalidation resolved")
    consumed = approvals.consume(
        connection,
        approval_id=binding.approval_id,
        site_id=binding.site_id,
        decided_by_actor_id=actor_id,
        decided_at=occurred_at,
        expected_resource_version=binding.resource_version,
    )
    if consumed is None:
        # Post-write-path concurrency closer: this exception must escape the
        # endpoint even though the admission check uses the same error type.
        raise PostWriteApprovalNotPendingError(
            "approval is no longer pending",
            expected={"state": "pending", "resource_version": binding.resource_version},
            current={"state": "terminal_or_changed"},
        )
    baseline = baseline_writer.promote(
        connection,
        site_id=binding.site_id,
        schedule_version_id=binding.candidate_schedule_version_id,
        actor_id=actor_id,
        occurred_at=occurred_at,
        expected_resource_version=binding.baseline_resource_version,
    )
    if baseline is None:
        raise BaselineConcurrentlyMovedError(
            "the site baseline moved concurrently",
            expected={"baseline_resource_version": binding.baseline_resource_version},
            current={"baseline_resource_version": "changed"},
        )
    audit_writer.append(connection, AuditEnvelopeV1(
        audit_id=uuid4(), attempt_id=uuid4(), request_id=request_id,
        site_id=binding.site_id, initiated_by_actor_id=binding.initiated_by_actor_id,
        decided_by_actor_id=actor_id, conversation_id=binding.conversation_id,
        agent_run_id=binding.agent_run_id, approval_id=binding.approval_id,
        schedule_run_id=binding.schedule_run_id, action=binding.action,
        outcome="approval_consumed", success=True, effect_key=binding.request_effect_key,
        before_version=binding.baseline_schedule_version,
        after_version=str(binding.candidate_schedule_version_id),
        safe_summary=binding.consequence_summary, parameter_hash=binding.parameter_hash,
        consequence_hash=binding.consequence_hash, policy_version=binding.policy_version,
        app_version=app_version, worker_facts=WorkerFactsV1(), evidence_refs=candidate.evidence_refs,
        occurred_at=occurred_at,
    ))
    resume = None
    if binding.agent_run_id is None:
        activity = conversations.append_approval_request_activity(
            connection, binding=consumed, actor_id=actor_id, request_id=request_id,
            agent_run_id=None, occurred_at=occurred_at, agent_run_status=None,
        )
    else:
        payload = approvals.get_pending_payload(
            connection, approval_id=binding.approval_id, site_id=binding.site_id
        )
        if payload is None:
            raise ApprovalPayloadUnreadableError(
                "agent-backed approval has no pending payload to resume from",
                expected={"pending_payload": "present"},
                current={"pending_payload": "absent"},
            )
        try:
            pending = TypeAdapter(AgentApprovalPendingV1).validate_python(payload)
        except ValidationError as exc:
            raise ApprovalPayloadUnreadableError(
                "agent-backed approval payload does not match the owned contract",
                expected={"pending_payload": "AgentApprovalPendingV1"},
                current={"pending_payload": "unreadable"},
            ) from exc
        if len(pending.pending_calls) != 1:
            raise ApprovalPayloadUnreadableError(
                "approval pending payload must contain exactly one call",
                expected={"pending_calls": 1},
                current={"pending_calls": len(pending.pending_calls)},
            )
        activity = conversations.resume_agent_run_for_approval(
            connection, agent_run_id=binding.agent_run_id, binding=consumed,
            request_id=request_id, occurred_at=occurred_at,
        )
        resume = ResumeRequestV1(
            agent_run_id=binding.agent_run_id,
            tool_call_id=pending.pending_calls[0].tool_call_id,
            history=pending.turn,
        )
    return PromotionResultV1(consumed, baseline, activity, resume)


__all__ = [
    "ApprovalPayloadUnreadableError",
    "BaselineConcurrentlyMovedError",
    "PromotionResultV1",
    "ResumeRequestV1",
    "promote_baseline",
]
