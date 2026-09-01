"""Compose one persisted decision timeline without SQL, providers, or calculators."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from application.contracts.activity import AgentResponseActivityV1, DraftActivityV1
from application.contracts.agent_runtime import AgentApprovalPendingV1
from application.contracts.approval_binding import presented_approval_state
from application.contracts.decision_provenance import (
    ApprovalDecisionProvenanceV1, ApprovalRequestProvenanceV1,
    AuditRecordProvenanceV1, BaselinePromotionProvenanceV1,
    DecisionProvenanceV1, DraftProvenanceV1, EvidenceClaimProvenanceV1,
    RunProgressProvenanceV1, SolverRunProvenanceV1, ToolProposalProvenanceV1,
)

#: Decision 5's cross-stream order. Every rank is DISTINCT: `occurred_at` ties are
#: the normal case -- TX1/TX2/TX3 each write binding, audit, and event against one
#: application clock -- so two item types sharing a rank fall through to `_sort_id`,
#: which reads a different field per type and therefore compares unrelated UUIDs as
#: strings. A decision precedes the audit that records it.
_SOURCE_RANK = {
    "solver_run": 0, "run_progress": 1, "draft": 2, "evidence_claim": 3,
    "tool_proposal": 4, "approval_request": 5, "approval_decision": 6,
    "audit_record": 7, "baseline_promotion": 8,
}
_COMPARISON_UNAVAILABLE = (
    "Comparison unavailable: the frozen baseline schedule has no authoritative "
    "assignment supply; it is linked by reference and never recomputed."
)
#: Deliberately distinct from the EAD-8 reason. A run that produced no candidate has
#: nothing to compare at all, which is a different fact from a frozen baseline whose
#: assignment supply cannot be read; reusing the EAD-8 text would misexplain it.
_COMPARISON_NO_CANDIDATE = (
    "Comparison unavailable: this run produced no candidate schedule version, so "
    "there is no comparison to link."
)


def _common(*, occurred_at, item_type, site_id, schedule_run_id,
            actor_id=None, initiated_by_actor_id=None, decided_by_actor_id=None,
            request_id=None, attempt_id=None, conversation_id=None,
            agent_run_id=None, tool_call_id=None, approval_id=None,
            job_attempt_id=None, audit_id=None, schedule_version_id=None,
            scenario_version_id=None, evidence_refs=()):
    return dict(
        occurred_at=occurred_at, item_type=item_type, site_id=site_id,
        actor_id=actor_id, initiated_by_actor_id=initiated_by_actor_id,
        decided_by_actor_id=decided_by_actor_id, request_id=request_id,
        attempt_id=attempt_id, conversation_id=conversation_id,
        agent_run_id=agent_run_id, tool_call_id=tool_call_id,
        approval_id=approval_id, job_attempt_id=job_attempt_id,
        schedule_run_id=schedule_run_id, audit_id=audit_id,
        schedule_version_id=schedule_version_id,
        scenario_version_id=scenario_version_id, evidence_refs=tuple(evidence_refs),
        schema_version="1",
    )


def _sort_id(item) -> str:
    """Last-resort tie-break WITHIN one item type; distinct ranks separate the types."""
    for name in (
        "audit_id", "approval_id", "schedule_version_id", "request_id",
        "attempt_id", "schedule_run_id",
    ):
        value = getattr(item, name, None)
        if value is not None:
            return str(value)
    return ""


def _audit_ids(audit) -> tuple[UUID | None, UUID | None]:
    return (audit.request_id, audit.attempt_id) if audit is not None else (None, None)


def query_decision_provenance(
    connection: Any, *, schedule_run_id: UUID, site_id: UUID,
    schedule_runs, approvals, audit_reader, conversations, clock,
) -> DecisionProvenanceV1 | None:
    """Return a port-composed snapshot; absence and foreign-site denial are identical."""
    run = schedule_runs.get_run(connection, run_id=schedule_run_id, site_id=site_id)
    if run is None:
        return None
    snapshot = schedule_runs.load_snapshot(connection, run_id=schedule_run_id, site_id=site_id)
    candidate = schedule_runs.get_candidate(
        connection, schedule_run_id=schedule_run_id, site_id=site_id,
    )
    bindings = approvals.list_for_schedule_run(
        connection, schedule_run_id=schedule_run_id, site_id=site_id,
    )
    audits = audit_reader.list_for_schedule_run(
        connection, schedule_run_id=schedule_run_id, site_id=site_id,
    )
    run_events = schedule_runs.events_after(
        connection, stream_id=schedule_run_id, after=Decimal(0), limit=10_000,
    ) or ()
    now = clock()
    items: list[Any] = []
    # Read one by one off the typed contracts. A defaulted `getattr` would turn a
    # future rename into a null on the one surface whose value is that a null means
    # "the row never carried one" (Decision 10).
    scenario_version_id = snapshot.scenario_version_id if snapshot is not None else None
    baseline_version = snapshot.baseline_schedule_version if snapshot is not None else None
    accepted_at = snapshot.accepted_at if snapshot is not None else None
    candidate_id = candidate.schedule_version_id if candidate is not None else None
    candidate_refs = candidate.evidence_refs if candidate is not None else ()
    candidate_metrics = candidate.metrics if candidate is not None else None
    first_actor = run_events[0].actor_id if run_events else None

    # Two independent reasons a comparison cannot be shown, and they are not the same
    # fact. EAD-8 refuses recomputation against a frozen baseline; a run with no
    # candidate has nothing to compare in the first place. Reporting the second case
    # as `available` claims a comparison that does not exist.
    comparison_reason = (
        _COMPARISON_UNAVAILABLE if baseline_version is not None
        else _COMPARISON_NO_CANDIDATE if candidate_id is None
        else None
    )
    items.append(SolverRunProvenanceV1(**_common(
        occurred_at=accepted_at or run.created_at,
        item_type="solver_run", site_id=site_id, schedule_run_id=schedule_run_id,
        actor_id=first_actor, initiated_by_actor_id=first_actor,
        schedule_version_id=candidate_id, scenario_version_id=scenario_version_id,
        evidence_refs=candidate_refs,
    ), status=run.status, reason=run.reason,
        baseline_schedule_version=baseline_version,
        candidate_schedule_version_id=candidate_id,
        comparison_status="unavailable" if comparison_reason else "available",
        comparison_reason=comparison_reason,
        metrics=candidate_metrics))

    for event in run_events:
        payload = event.payload
        items.append(RunProgressProvenanceV1(**_common(
            occurred_at=event.occurred_at, item_type="run_progress", site_id=site_id,
            schedule_run_id=schedule_run_id, actor_id=event.actor_id,
            initiated_by_actor_id=event.actor_id, request_id=event.request_id,
            conversation_id=event.conversation_id, agent_run_id=event.agent_run_id,
            scenario_version_id=scenario_version_id,
        ), status=payload.status, reason=payload.reason,
            resource_version=payload.resource_version))

    bound_agent_runs = {binding.agent_run_id for binding in bindings if binding.agent_run_id}
    conversation_ids = {binding.conversation_id for binding in bindings}
    for conversation_id in sorted(conversation_ids, key=str):
        timeline = conversations.timeline(connection, conversation_id=conversation_id, limit=10_000)
        if timeline is None:
            continue
        for event in timeline.events:
            if event.agent_run_id not in bound_agent_runs:
                continue
            payload = event.payload
            if not isinstance(payload, (DraftActivityV1, AgentResponseActivityV1)):
                continue
            common = _common(
                occurred_at=event.occurred_at, item_type="draft", site_id=site_id,
                schedule_run_id=schedule_run_id, actor_id=event.actor_id,
                initiated_by_actor_id=event.actor_id, request_id=event.request_id,
                conversation_id=event.conversation_id, agent_run_id=event.agent_run_id,
                scenario_version_id=payload.scenario_version_id,
            )
            if isinstance(payload, DraftActivityV1):
                items.append(DraftProvenanceV1(**common, proposal_id=payload.proposal_id,
                    proposal_version_id=payload.proposal_version_id,
                    consequence_summary=payload.consequence_summary))
            else:
                for claim in payload.response.claims:
                    claim_common = {**common, "item_type": "evidence_claim",
                                    "evidence_refs": claim.evidence_refs}
                    items.append(EvidenceClaimProvenanceV1(
                        **claim_common, claim=claim.metric, value=claim.value, unit=claim.unit,
                    ))

    # Keyed by OUTCOME, not by approval alone. One approval accumulates several audit
    # rows -- requested, then consumed/rejected, plus any denials -- so a last-wins map
    # per approval stamps the request item with the identifiers of whichever operation
    # came last: a well-formed identifier belonging to a different request, which is
    # exactly the question a reviewer opens provenance to answer. `setdefault` keeps
    # the earliest row of a repeated outcome; the adapter returns audits ordered.
    audits_by_outcome: dict[tuple[UUID, str], Any] = {}
    for audit in audits:
        if audit.approval_id is not None:
            audits_by_outcome.setdefault((audit.approval_id, audit.outcome), audit)
    state_outcome = {
        "consumed": "approval_consumed", "rejected": "approval_rejected",
        "expired": "approval_expired", "stale": "approval_stale",
    }
    for binding in bindings:
        state = presented_approval_state(binding, now)
        request_id, attempt_id = _audit_ids(
            audits_by_outcome.get((binding.approval_id, "approval_requested"))
        )
        items.append(ApprovalRequestProvenanceV1(**_common(
            occurred_at=binding.created_at, item_type="approval_request", site_id=site_id,
            schedule_run_id=schedule_run_id, actor_id=binding.initiated_by_actor_id,
            initiated_by_actor_id=binding.initiated_by_actor_id, request_id=request_id,
            attempt_id=attempt_id, conversation_id=binding.conversation_id,
            agent_run_id=binding.agent_run_id, approval_id=binding.approval_id,
            schedule_version_id=binding.candidate_schedule_version_id,
            scenario_version_id=binding.scenario_version_id,
        ), state=state, consequence_summary=binding.consequence_summary,
            parameter_hash=binding.parameter_hash, consequence_hash=binding.consequence_hash,
            policy_version=binding.policy_version, expires_at=binding.expires_at))
        if binding.agent_run_id is not None:
            try:
                pending_payload = approvals.get_pending_payload(
                    connection, approval_id=binding.approval_id, site_id=site_id,
                )
                pending = TypeAdapter(AgentApprovalPendingV1).validate_python(pending_payload)
            except (ValidationError, TypeError):
                pending = None
            if pending is not None and len(pending.pending_calls) == 1:
                call = pending.pending_calls[0]
                items.append(ToolProposalProvenanceV1(**_common(
                    occurred_at=binding.created_at, item_type="tool_proposal", site_id=site_id,
                    schedule_run_id=schedule_run_id, actor_id=binding.initiated_by_actor_id,
                    initiated_by_actor_id=binding.initiated_by_actor_id,
                    conversation_id=binding.conversation_id, agent_run_id=binding.agent_run_id,
                    tool_call_id=call.tool_call_id, approval_id=binding.approval_id,
                    scenario_version_id=binding.scenario_version_id,
                ), tool_name=call.tool_name))
        if state in state_outcome and binding.decided_at is not None:
            decision_request_id, decision_attempt_id = _audit_ids(
                audits_by_outcome.get((binding.approval_id, state_outcome[state]))
            )
            items.append(ApprovalDecisionProvenanceV1(**_common(
                occurred_at=binding.decided_at, item_type="approval_decision", site_id=site_id,
                schedule_run_id=schedule_run_id, actor_id=binding.initiated_by_actor_id,
                initiated_by_actor_id=binding.initiated_by_actor_id,
                decided_by_actor_id=binding.decided_by_actor_id,
                request_id=decision_request_id, attempt_id=decision_attempt_id,
                conversation_id=binding.conversation_id,
                agent_run_id=binding.agent_run_id, approval_id=binding.approval_id,
                schedule_version_id=binding.candidate_schedule_version_id,
                scenario_version_id=binding.scenario_version_id,
            ), outcome=state_outcome[state], state=state))

    for audit in audits:
        items.append(AuditRecordProvenanceV1(**_common(
            occurred_at=audit.occurred_at, item_type="audit_record", site_id=site_id,
            schedule_run_id=schedule_run_id, actor_id=audit.initiated_by_actor_id,
            initiated_by_actor_id=audit.initiated_by_actor_id,
            decided_by_actor_id=audit.decided_by_actor_id, request_id=audit.request_id,
            attempt_id=audit.attempt_id, conversation_id=audit.conversation_id,
            agent_run_id=audit.agent_run_id, approval_id=audit.approval_id,
            job_attempt_id=audit.worker_facts.attempt_id, audit_id=audit.audit_id,
            schedule_version_id=candidate_id, scenario_version_id=scenario_version_id,
            evidence_refs=audit.evidence_refs,
        ), action=audit.action, outcome=audit.outcome, success=audit.success,
            safe_summary=audit.safe_summary, parameter_hash=audit.parameter_hash,
            consequence_hash=audit.consequence_hash, policy_version=audit.policy_version,
            app_version=audit.app_version, worker_facts=audit.worker_facts))
        if audit.outcome == "approval_consumed" and audit.after_version is not None:
            items.append(BaselinePromotionProvenanceV1(**_common(
                occurred_at=audit.occurred_at, item_type="baseline_promotion", site_id=site_id,
                schedule_run_id=schedule_run_id, actor_id=audit.initiated_by_actor_id,
                initiated_by_actor_id=audit.initiated_by_actor_id,
                decided_by_actor_id=audit.decided_by_actor_id, request_id=audit.request_id,
                attempt_id=audit.attempt_id, conversation_id=audit.conversation_id,
                agent_run_id=audit.agent_run_id, approval_id=audit.approval_id,
                job_attempt_id=audit.worker_facts.attempt_id, audit_id=audit.audit_id,
                schedule_version_id=candidate_id, scenario_version_id=scenario_version_id,
                evidence_refs=audit.evidence_refs,
            ), before_version=audit.before_version, after_version=audit.after_version))

    # Ranks are distinct, so `_sort_id` only ever separates two items of the SAME
    # type, where its field preference is consistent.
    items.sort(key=lambda item: (
        item.occurred_at, _SOURCE_RANK[item.item_type], _sort_id(item),
    ))
    return DecisionProvenanceV1(schedule_run_id, site_id, tuple(items))


__all__ = ["query_decision_provenance"]
