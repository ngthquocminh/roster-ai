"""Read-side decision provenance tests, split from router and PostgreSQL proofs."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from adapters.postgres.audit import PostgresAuditReader
from application.contracts.decision_provenance import (
    DecisionProvenanceItemV1,
    ProvenanceCommonV1,
    SCOPE_CONTROLS,
)
from api.schemas import DecisionProvenanceItemOut
from application.queries.decision_provenance import query_decision_provenance
from application.contracts.activity import AgentResponseActivityV1
from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import GroundedClaimV1, GroundedResponseV1
from application.contracts.persisted_event import PersistedEventV1


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _Rows(self.rows)


def test_audit_reader_filters_site_orders_rows_and_rehydrates_json() -> None:
    site_id = uuid4()
    run_id = uuid4()
    attempt_id = uuid4()
    scenario_version_id = uuid4()
    row = SimpleNamespace(
        id=uuid4(), site_id=site_id, attempt_id=attempt_id, request_id=uuid4(),
        initiated_by_actor_id=uuid4(), decided_by_actor_id=None,
        conversation_id=None, agent_run_id=None, approval_id=None,
        schedule_run_id=run_id, action="promote_baseline",
        outcome="approval_consumed", success=True, effect_key="effect",
        before_version=None, after_version="after", safe_summary="safe",
        parameter_hash="a" * 64, consequence_hash="b" * 64,
        policy_version="policy", app_version="app",
        worker_facts={"lease_owner": "worker", "attempt_id": str(attempt_id),
                      "fencing_epoch": 2, "schema_version": "1"},
        evidence_refs=[{
            "scenario_version_id": str(scenario_version_id),
            "checksum_algorithm": "sha256", "checksum_schema_version": "v1",
            "checksum_digest": "c" * 64, "producing_run_version": "run-v1",
            "baseline_schedule_version": None, "group": "demand",
            "record_id": "demand-1", "field": None, "start_minute": None,
            "end_minute": None, "schema_version": "1",
        }],
        occurred_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    connection = _Connection([row])

    result = PostgresAuditReader().list_for_schedule_run(
        connection, schedule_run_id=run_id, site_id=site_id,
    )

    assert result[0].worker_facts.attempt_id == attempt_id
    assert result[0].evidence_refs[0].scenario_version_id == scenario_version_id
    sql = str(connection.statement)
    assert "audit_event.site_id" in sql
    assert "audit_event.schedule_run_id" in sql
    assert "ORDER BY audit_event.occurred_at, audit_event.id" in sql


def test_provenance_contract_is_closed_and_carries_every_identifier_slot() -> None:
    union_members = DecisionProvenanceItemV1.__args__
    assert {member.__dataclass_fields__["item_type"].type.__args__[0] for member in union_members} == {
        "solver_run", "run_progress", "draft", "evidence_claim", "tool_proposal",
        "approval_request", "approval_decision", "audit_record", "baseline_promotion",
    }
    assert [field.name for field in fields(ProvenanceCommonV1)] == [
        "occurred_at", "item_type", "site_id", "actor_id",
        "initiated_by_actor_id", "decided_by_actor_id", "request_id", "attempt_id",
        "conversation_id", "agent_run_id", "tool_call_id", "approval_id",
        "job_attempt_id", "schedule_run_id", "audit_id", "schedule_version_id",
        "scenario_version_id", "evidence_refs", "schema_version",
    ]
    assert set(SCOPE_CONTROLS) == {
        "membership:agent_run_bound_conversation_events",
        "tool_proposals:approval_triggering_call_only",
        "comparison:linked_by_reference_never_recomputed",
        "payload:identity_only_never_turn",
    }
    assert DecisionProvenanceItemOut.__metadata__[0].discriminator == "item_type"


def test_projection_keeps_zero_approval_run_and_uses_timestamp_rank_id_order() -> None:
    site_id = uuid4()
    run_id = uuid4()
    scenario_version_id = uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    progress_id = uuid4()
    run = SimpleNamespace(
        schedule_run_id=run_id, status="solver_completed", reason=None,
        resource_version=2, cancellation_requested=False, created_at=now,
        finished_at=now,
    )
    progress = SimpleNamespace(
        occurred_at=now, site_id=site_id, actor_id=uuid4(), request_id=uuid4(),
        conversation_id=None, agent_run_id=None, schedule_run_id=run_id,
        payload=SimpleNamespace(
            activity_id=progress_id, status="solver_completed", reason=None,
            resource_version=2,
        ),
    )
    snapshot = SimpleNamespace(
        snapshot_id=uuid4(), schedule_run_id=run_id, scenario_version_id=scenario_version_id,
        baseline_schedule_version=None, accepted_at=now,
    )

    class Runs:
        def get_run(self, *_args, **_kwargs): return run
        def load_snapshot(self, *_args, **_kwargs): return snapshot
        def get_candidate(self, *_args, **_kwargs): return None
        def events_after(self, *_args, **_kwargs): return (progress,)

    class Empty:
        def list_for_schedule_run(self, *_args, **_kwargs): return ()

    result = query_decision_provenance(
        None, schedule_run_id=run_id, site_id=site_id, schedule_runs=Runs(),
        approvals=Empty(), audit_reader=Empty(), conversations=SimpleNamespace(),
        clock=lambda: now,
    )

    assert result is not None
    assert [item.item_type for item in result.items] == ["solver_run", "run_progress"]
    # No frozen baseline AND no candidate: there is nothing to compare, which is a
    # different fact from EAD-8 refusing recomputation. Claiming `available` here
    # advertises a comparison that does not exist.
    assert result.items[0].comparison_status == "unavailable"
    assert "produced no candidate schedule version" in result.items[0].comparison_reason


def test_projection_replays_candidate_and_grounded_claim_evidence_refs() -> None:
    site_id, run_id, conversation_id, agent_run_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id = uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    candidate_ref = EvidenceRefV1(
        scenario_version_id, "sha256", "v1", "a" * 64, "run-v1", None,
        "demand", "candidate-row",
    )
    claim_ref = EvidenceRefV1(
        scenario_version_id, "sha256", "v1", "b" * 64, None, None,
        "workers", "claim-row",
    )
    response = GroundedResponseV1(
        scenario_version_id=scenario_version_id,
        segments=(GroundedClaimV1(metric="qualified_worker_count", result_id="r1",
                                  value=2, unit="workers", evidence_refs=(claim_ref,),
                                  verdict="supported"),),
    )
    activity = AgentResponseActivityV1(
        uuid4(), "agent_response", conversation_id, 2, uuid4(),
        scenario_version_id, now, response,
    )
    event = PersistedEventV1(
        conversation_id, 1, "agent.response.v1", now, 2, uuid4(), conversation_id,
        agent_run_id, site_id, uuid4(), activity,
    )
    binding = ApprovalBindingV1(
        uuid4(), "pending", site_id, "promote_baseline", event.actor_id, None,
        conversation_id, agent_run_id, run_id, candidate_id, scenario_version_id,
        None, None, "c" * 64, "Promote exact candidate", "d" * 64,
        policy_version="policy", created_at=now, expires_at=now,
    )

    class Runs:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed", reason=None,
                                   created_at=now)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=scenario_version_id,
                                   baseline_schedule_version=None, accepted_at=now)
        def get_candidate(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_version_id=candidate_id, evidence_refs=(candidate_ref,),
                                   metrics=None)
        def events_after(self, *_args, **_kwargs): return ()

    class Approvals:
        def list_for_schedule_run(self, *_args, **_kwargs): return (binding,)
        def get_pending_payload(self, *_args, **_kwargs):
            return {
                "pending_calls": [{
                    "tool_call_id": "call-1", "tool_name": "scheduling_baseline",
                    "tool_args_json": "{\"private\":true}",
                }],
                "turn": {"messages": []},
            }

    conversations = SimpleNamespace(timeline=lambda *_args, **_kwargs:
                                    SimpleNamespace(events=(event,)))
    result = query_decision_provenance(
        None, schedule_run_id=run_id, site_id=site_id, schedule_runs=Runs(),
        approvals=Approvals(), audit_reader=SimpleNamespace(
            list_for_schedule_run=lambda *_args, **_kwargs: ()),
        conversations=conversations,
        clock=lambda: now,
    )

    assert next(item for item in result.items if item.item_type == "solver_run").evidence_refs == (candidate_ref,)
    assert next(item for item in result.items if item.item_type == "evidence_claim").evidence_refs == (claim_ref,)
    assert len([item for item in result.items if item.item_type == "tool_proposal"]) == 1
    assert next(item for item in result.items if item.item_type == "approval_request").state == "expired"


def test_rejected_then_rerequested_bindings_share_one_run_timeline() -> None:
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id = uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)

    def binding(state, *, decided=False):
        return ApprovalBindingV1(
            uuid4(), state, site_id, "promote_baseline", actor_id,
            actor_id if decided else None, conversation_id, None, run_id, candidate_id,
            scenario_version_id, None, None, "a" * 64, "Promote exact candidate",
            "b" * 64, policy_version="policy", created_at=now,
            expires_at=now.replace(year=2027), decided_at=now if decided else None,
        )

    rejected = binding("rejected", decided=True)
    pending = binding("pending")

    class Runs:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed",
                                   reason=None, created_at=now)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=scenario_version_id,
                                   baseline_schedule_version=None, accepted_at=now)
        def get_candidate(self, *_args, **_kwargs): return None
        def events_after(self, *_args, **_kwargs): return ()

    approvals = SimpleNamespace(
        list_for_schedule_run=lambda *_args, **_kwargs: (rejected, pending),
    )
    result = query_decision_provenance(
        None, schedule_run_id=run_id, site_id=site_id, schedule_runs=Runs(),
        approvals=approvals,
        audit_reader=SimpleNamespace(list_for_schedule_run=lambda *_args, **_kwargs: ()),
        conversations=SimpleNamespace(timeline=lambda *_args, **_kwargs:
                                      SimpleNamespace(events=())),
        clock=lambda: now,
    )

    assert len([item for item in result.items if item.item_type == "approval_request"]) == 2
    assert [item.state for item in result.items if item.item_type == "approval_decision"] == ["rejected"]


def _binding(*, site_id, run_id, conversation_id, actor_id, candidate_id, scenario_version_id,
             state="pending", approval_id=None, agent_run_id=None, created_at, expires_at,
             decided_at=None):
    return ApprovalBindingV1(
        approval_id or uuid4(), state, site_id, "promote_baseline", actor_id,
        actor_id if decided_at else None, conversation_id, agent_run_id, run_id, candidate_id,
        scenario_version_id, None, None, "a" * 64, "Promote exact candidate", "b" * 64,
        policy_version="policy", created_at=created_at, expires_at=expires_at,
        decided_at=decided_at,
    )


def _audit(*, site_id, run_id, conversation_id, actor_id, approval_id, outcome, occurred_at,
           request_id=None, attempt_id=None, after_version=None, audit_id=None,
           evidence_refs=()):
    return AuditEnvelopeV1(
        audit_id=audit_id or uuid4(), attempt_id=attempt_id or uuid4(),
        request_id=request_id or uuid4(),
        site_id=site_id, initiated_by_actor_id=actor_id, decided_by_actor_id=actor_id,
        conversation_id=conversation_id, agent_run_id=None, approval_id=approval_id,
        schedule_run_id=run_id, action="promote_baseline", outcome=outcome, success=True,
        effect_key="effect", before_version=None, after_version=after_version,
        safe_summary="safe", parameter_hash="a" * 64, consequence_hash="b" * 64,
        policy_version="policy", app_version="app", worker_facts=WorkerFactsV1(),
        evidence_refs=evidence_refs, occurred_at=occurred_at,
    )


def test_audit_record_and_baseline_promotion_replay_audit_evidence_refs() -> None:
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id, approval_id = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    evidence_ref = EvidenceRefV1(
        scenario_version_id, "sha256", "rfc8785-v1", "e" * 64,
        "run-v1", None, "demand", "demand-1",
    )
    binding = _binding(
        site_id=site_id, run_id=run_id, conversation_id=conversation_id,
        actor_id=actor_id, candidate_id=candidate_id,
        scenario_version_id=scenario_version_id, state="consumed",
        approval_id=approval_id, created_at=now,
        expires_at=now.replace(year=2027), decided_at=now,
    )
    audit = _audit(
        site_id=site_id, run_id=run_id, conversation_id=conversation_id,
        actor_id=actor_id, approval_id=approval_id, outcome="approval_consumed",
        occurred_at=now, after_version=str(candidate_id),
        evidence_refs=(evidence_ref,),
    )

    result = _run_query(
        run_id=run_id, site_id=site_id,
        runs=_runs(run_id=run_id, scenario_version_id=scenario_version_id, now=now),
        bindings=(binding,), audits=(audit,), now=now,
    )

    assert next(item for item in result.items if item.item_type == "audit_record").evidence_refs == (evidence_ref,)
    assert next(item for item in result.items if item.item_type == "baseline_promotion").evidence_refs == (evidence_ref,)


def _runs(*, run_id, scenario_version_id, now, candidate=None):
    class Runs:
        def get_run(self, *_args, **_kwargs):
            return SimpleNamespace(schedule_run_id=run_id, status="solver_completed",
                                   reason=None, created_at=now)
        def load_snapshot(self, *_args, **_kwargs):
            return SimpleNamespace(snapshot_id=uuid4(), scenario_version_id=scenario_version_id,
                                   baseline_schedule_version=None, accepted_at=now)
        def get_candidate(self, *_args, **_kwargs):
            return candidate
        def events_after(self, *_args, **_kwargs):
            return ()
    return Runs()


def _run_query(*, run_id, site_id, runs, bindings=(), audits=(), now, pending_payload=None):
    return query_decision_provenance(
        None, schedule_run_id=run_id, site_id=site_id, schedule_runs=runs,
        approvals=SimpleNamespace(
            list_for_schedule_run=lambda *_a, **_k: bindings,
            get_pending_payload=lambda *_a, **_k: pending_payload,
        ),
        audit_reader=SimpleNamespace(list_for_schedule_run=lambda *_a, **_k: audits),
        conversations=SimpleNamespace(timeline=lambda *_a, **_k: SimpleNamespace(events=())),
        clock=lambda: now,
    )


def test_same_timestamp_decision_and_audit_order_independently_of_their_uuids() -> None:
    """Decision 5's tie-break must not degrade into a UUID string comparison.

    TX2 writes the binding's `decided_at` and the audit's `occurred_at` from ONE
    application clock, so these items always share a timestamp. When both types held
    the same `source_rank`, the next key read a different field per type -- `audit_id`
    on audits, `approval_id` on decisions -- and the rendered order flipped purely on
    which random UUID sorted lower as a string.
    """
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id = uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    orders = []
    # Audit ids are FIXED so the approval UUID is the only varying input. The two
    # values sort on opposite sides of those audit ids as strings, which is what made
    # the collided rank observable.
    for approval_id in (UUID(int=7), UUID(int=255)):
        binding = _binding(
            site_id=site_id, run_id=run_id, conversation_id=conversation_id, actor_id=actor_id,
            candidate_id=candidate_id, scenario_version_id=scenario_version_id, state="consumed",
            approval_id=approval_id, created_at=now, expires_at=now.replace(year=2027),
            decided_at=now,
        )
        audits = (
            _audit(site_id=site_id, run_id=run_id, conversation_id=conversation_id,
                   actor_id=actor_id, approval_id=approval_id, outcome="approval_requested",
                   occurred_at=now, audit_id=UUID(int=10)),
            _audit(site_id=site_id, run_id=run_id, conversation_id=conversation_id,
                   actor_id=actor_id, approval_id=approval_id, outcome="approval_consumed",
                   occurred_at=now, after_version="version-2", audit_id=UUID(int=11)),
        )
        result = _run_query(
            run_id=run_id, site_id=site_id,
            runs=_runs(run_id=run_id, scenario_version_id=scenario_version_id, now=now),
            bindings=(binding,), audits=audits, now=now,
        )
        orders.append([item.item_type for item in result.items])

    assert orders[0] == orders[1], "timeline order changed with nothing but the approval UUID"
    assert orders[0] == [
        "solver_run", "approval_request", "approval_decision",
        "audit_record", "audit_record", "baseline_promotion",
    ]


def test_request_and_decision_items_take_identifiers_from_their_own_audit_row() -> None:
    """One approval owns several audit rows; each item must read the one recording it."""
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id, approval_id = uuid4(), uuid4(), uuid4()
    requested_request, consumed_request = uuid4(), uuid4()
    requested_attempt, consumed_attempt = uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    binding = _binding(
        site_id=site_id, run_id=run_id, conversation_id=conversation_id, actor_id=actor_id,
        candidate_id=candidate_id, scenario_version_id=scenario_version_id, state="consumed",
        approval_id=approval_id, created_at=now, expires_at=now.replace(year=2027),
        decided_at=now,
    )
    audits = (
        _audit(site_id=site_id, run_id=run_id, conversation_id=conversation_id, actor_id=actor_id,
               approval_id=approval_id, outcome="approval_requested", occurred_at=now,
               request_id=requested_request, attempt_id=requested_attempt),
        _audit(site_id=site_id, run_id=run_id, conversation_id=conversation_id, actor_id=actor_id,
               approval_id=approval_id, outcome="approval_consumed", occurred_at=now,
               request_id=consumed_request, attempt_id=consumed_attempt,
               after_version="version-2"),
    )

    result = _run_query(
        run_id=run_id, site_id=site_id,
        runs=_runs(run_id=run_id, scenario_version_id=scenario_version_id, now=now),
        bindings=(binding,), audits=audits, now=now,
    )

    request_item = next(i for i in result.items if i.item_type == "approval_request")
    decision_item = next(i for i in result.items if i.item_type == "approval_decision")
    assert (request_item.request_id, request_item.attempt_id) == (requested_request, requested_attempt)
    assert (decision_item.request_id, decision_item.attempt_id) == (consumed_request, consumed_attempt)


def test_an_overdue_pending_binding_is_presented_expired_without_a_decision_item() -> None:
    """EAD-7: a read that observes `now >= expires_at` presents expiry and writes nothing."""
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id = uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    binding = _binding(
        site_id=site_id, run_id=run_id, conversation_id=conversation_id, actor_id=actor_id,
        candidate_id=candidate_id, scenario_version_id=scenario_version_id, state="pending",
        created_at=now.replace(year=2026, month=8, day=30),
        expires_at=now.replace(year=2026, month=8, day=30), decided_at=None,
    )

    result = _run_query(
        run_id=run_id, site_id=site_id,
        runs=_runs(run_id=run_id, scenario_version_id=scenario_version_id, now=now),
        bindings=(binding,), now=now,
    )

    request_item = next(i for i in result.items if i.item_type == "approval_request")
    assert request_item.state == "expired"
    assert binding.state == "pending", "the projection must not mutate the binding"
    # An overdue PENDING row was never decided, so presenting expiry must not invent one.
    assert not [i for i in result.items if i.item_type == "approval_decision"]


def test_only_an_agent_initiated_binding_emits_exactly_one_tool_proposal() -> None:
    """Decision 8a: the approval-triggering call is the only persisted tool proposal."""
    site_id, run_id, conversation_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    scenario_version_id, candidate_id, agent_run_id = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    runs = _runs(run_id=run_id, scenario_version_id=scenario_version_id, now=now)
    payload = {
        "schema_version": "1",
        "pending_calls": [{"schema_version": "1", "tool_call_id": "call-1",
                           "tool_name": "promote_baseline", "arguments_json": "{}"}],
        "turn": {"schema_version": "1", "messages": []},
    }

    planner = _run_query(
        run_id=run_id, site_id=site_id, runs=runs, now=now, pending_payload=payload,
        bindings=(_binding(site_id=site_id, run_id=run_id, conversation_id=conversation_id,
                           actor_id=actor_id, candidate_id=candidate_id,
                           scenario_version_id=scenario_version_id, agent_run_id=None,
                           created_at=now, expires_at=now.replace(year=2027)),),
    )
    agentic = _run_query(
        run_id=run_id, site_id=site_id, runs=runs, now=now, pending_payload=payload,
        bindings=(_binding(site_id=site_id, run_id=run_id, conversation_id=conversation_id,
                           actor_id=actor_id, candidate_id=candidate_id,
                           scenario_version_id=scenario_version_id, agent_run_id=agent_run_id,
                           created_at=now, expires_at=now.replace(year=2027)),),
    )

    assert [i for i in planner.items if i.item_type == "tool_proposal"] == []
    proposals = [i for i in agentic.items if i.item_type == "tool_proposal"]
    assert len(proposals) == 1
    assert (proposals[0].tool_name, proposals[0].tool_call_id) == ("promote_baseline", "call-1")
    # Decision 9: identity only -- no argument or transcript field exists to leak.
    assert not {f.name for f in fields(proposals[0])} & {"tool_args_json", "turn", "payload"}
