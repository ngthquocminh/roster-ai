"""Live PostgreSQL proofs for Story 4.1's storage substrate.

Covers what only a real database can prove: RLS forced on the three new
tables, `audit_event`'s append-only privilege grant, the two partial unique
indexes (one pending binding per agent run; the two independent audit
uniqueness rules), and `request_approval`'s TX1 bundle persisted end-to-end
through the real adapters -- including the agent-path pending-payload
round-trip and the `agent_run` status transition. Router wiring and
problem-code mapping are proven against fakes in `test_approvals_api.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from pydantic import TypeAdapter

from dataclasses import replace

from fastapi.testclient import TestClient

from api.auth_security import SESSION_COOKIE_NAME, hash_secret
from api.deps import get_approval_repository, get_clock, get_identity_store, get_settings, get_site_baseline_writer, site_context
from api.main import app
from application.ports.session import ResolvedSession
from settings import default_settings
from adapters.postgres.approval import PostgresApprovalRepository
from adapters.postgres.audit import PostgresAuditReader, PostgresAuditWriter
from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.site_baseline import PostgresSiteBaselineReader, PostgresSiteBaselineWriter
from adapters.postgres.membership import PostgresMembershipReader
from application.queries.decision_provenance import query_decision_provenance
from adapters.postgres.schema import (
    agent_run,
    app_user,
    approval_request,
    audit_event,
    conversation,
    message,
    membership,
    organization,
    proposal,
    proposal_version,
    persisted_event,
    run_snapshot,
    schedule_assignment,
    schedule_run,
    schedule_version,
    scenario,
    scenario_version,
    site,
    site_baseline,
)
from application.contracts.schedule_version import ScheduleVersionV1
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
from application.contracts.scenario_projection import AssignmentV1
from application.use_cases.request_approval import (
    CandidateNotPromotableError,
    RequestApprovalCommandV1,
    StaleBaselineVersionError,
    StaleResourceVersionError,
    request_approval,
)
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def site_ids(governed_postgres_engine):
    ids = {name: uuid4() for name in ("org", "site", "other_site", "tx2_site", "actor")}
    with governed_postgres_engine.begin() as c:
        c.execute(insert(organization).values(id=ids["org"], name="Approval Governance Org"))
        c.execute(insert(site), [
            {"id": ids["site"], "organization_id": ids["org"], "name": "A"},
            {"id": ids["other_site"], "organization_id": ids["org"], "name": "B"},
            {"id": ids["tx2_site"], "organization_id": ids["org"], "name": "TX2"},
        ])
        c.execute(insert(app_user).values(id=ids["actor"], idp_subject="approval-actor", email="approval-actor@example.test"))
        c.execute(insert(membership).values(id=uuid4(), app_user_id=ids["actor"], site_id=ids["site"]))
    return ids


def _seed_candidate_run(engine, *, site_id, actor_id, status="solver_completed", resource_version=2, assignment_count=1, suffix=None, scenario_payload=None):
    """Build one scenario -> conversation -> proposal -> run_snapshot ->
    schedule_run(+candidate schedule_version, +assignments) chain via direct
    inserts, mirroring `finalize_run`'s own insert order without invoking the
    solver. Returns the ids `request_approval` and its adapters need."""
    suffix = suffix or uuid4().hex
    ids = {name: uuid4() for name in (
        "scenario", "scenario_version", "conversation", "message", "proposal",
        "proposal_version", "run_snapshot", "schedule_run", "candidate",
    )}
    with engine.begin() as c:
        c.execute(insert(scenario).values(id=ids["scenario"], site_id=site_id, fixture_id=f"fixture-{suffix}", name="Fixture"))
        c.execute(insert(scenario_version).values(
            id=ids["scenario_version"], site_id=site_id, scenario_id=ids["scenario"],
            fixture_id=f"fixture-{suffix}", version="v1", payload=scenario_payload or {}, checksum_digest="a" * 64,
        ))
        c.execute(insert(conversation).values(
            id=ids["conversation"], site_id=site_id, scenario_id=ids["scenario"],
            scenario_version_id=ids["scenario_version"], created_by_actor_id=actor_id,
        ))
        c.execute(insert(message).values(
            id=ids["message"], site_id=site_id, conversation_id=ids["conversation"],
            actor_id=actor_id, text="Solve this scenario.",
        ))
        c.execute(insert(proposal).values(
            id=ids["proposal"], site_id=site_id, scenario_id=ids["scenario"],
            scenario_version_id=ids["scenario_version"], conversation_id=ids["conversation"],
            created_by_actor_id=actor_id,
        ))
        c.execute(insert(proposal_version).values(
            id=ids["proposal_version"], site_id=site_id, proposal_id=ids["proposal"],
            version_ordinal=1, payload={}, canonical_hash="b" * 64,
        ))
        snapshot = RunSnapshotV1(
            snapshot_id=ids["run_snapshot"], schedule_run_id=ids["schedule_run"],
            scenario_id=ids["scenario"], scenario_version_id=ids["scenario_version"],
            checksum_algorithm="sha256", checksum_schema_version="v1",
            checksum_digest="a" * 64, baseline_schedule_version=None,
            proposal_id=ids["proposal"], proposal_version_id=ids["proposal_version"],
            proposal_resource_version=1, solver_config=GovernedSolverConfigV1(),
            component_versions=(("test", "1"),), accepted_at=NOW,
        )
        c.execute(insert(run_snapshot).values(
            id=ids["run_snapshot"], site_id=site_id, scenario_id=ids["scenario"],
            scenario_version_id=ids["scenario_version"], proposal_id=ids["proposal"],
            proposal_version_id=ids["proposal_version"],
            payload=TypeAdapter(RunSnapshotV1).dump_python(snapshot, mode="json"),
            canonical_hash=snapshot.canonical_hash,
            accepted_at=NOW,
        ))
        # `candidate_schedule_version_id` and the FK it carries can only be set
        # once the referenced `schedule_version` row exists -- insert the run
        # first with it NULL (legal: the CHECK only requires NULL OR
        # status='solver_completed', and NULL always satisfies it).
        c.execute(insert(schedule_run).values(
            id=ids["schedule_run"], site_id=site_id, run_snapshot_id=ids["run_snapshot"],
            status=status, resource_version=resource_version,
        ))
        candidate = None
        if status == "solver_completed":
            assignments = tuple(
                AssignmentV1(record_id=f"assign-{i}", worker_id=f"worker-{i}", task_id="task-1", shift_id="shift-1", start_minute=0, end_minute=480)
                for i in range(assignment_count)
            )
            candidate = ScheduleVersionV1(
                schedule_version_id=ids["candidate"], schedule_run_id=ids["schedule_run"],
                scenario_id=ids["scenario"], scenario_version_id=ids["scenario_version"],
                proposal_id=ids["proposal"], proposal_version_id=ids["proposal_version"],
                feasible_solver_status="OPTIMAL", assignments=assignments, created_at=NOW,
            )
            payload = TypeAdapter(ScheduleVersionV1).dump_python(candidate, mode="json")
            c.execute(insert(schedule_version).values(
                id=ids["candidate"], site_id=site_id, schedule_run_id=ids["schedule_run"],
                scenario_id=ids["scenario"], scenario_version_id=ids["scenario_version"],
                proposal_id=ids["proposal"], proposal_version_id=ids["proposal_version"],
                solver_status="OPTIMAL", payload=payload, canonical_hash="d" * 64,
            ))
            for assignment in assignments:
                c.execute(insert(schedule_assignment).values(
                    site_id=site_id, schedule_version_id=ids["candidate"],
                    assignment_record_id=assignment.record_id, worker_id=assignment.worker_id,
                    task_id=assignment.task_id, shift_id=assignment.shift_id,
                    start_minute=assignment.start_minute, end_minute=assignment.end_minute,
                    qualification_refs=[], source=assignment.source,
                ))
            c.execute(update(schedule_run).where(schedule_run.c.id == ids["schedule_run"]).values(candidate_schedule_version_id=ids["candidate"]))
    return ids


def _seed_agent_run(engine, *, site_id, conversation_id, actor_id, status="agent_running"):
    ids = {"message": uuid4(), "agent_run": uuid4()}
    with engine.begin() as c:
        c.execute(insert(message).values(id=ids["message"], site_id=site_id, conversation_id=conversation_id, actor_id=actor_id, text="Please approve."))
        c.execute(insert(agent_run).values(id=ids["agent_run"], site_id=site_id, conversation_id=conversation_id, message_id=ids["message"], status=status))
    return ids["agent_run"]


# --- RLS is forced, not merely enabled -------------------------------------


@pytest.mark.parametrize("table_name", ["approval_request", "site_baseline", "audit_event"])
def test_rls_is_enabled_and_forced_on_every_new_table(governed_postgres_engine, table_name) -> None:
    with governed_postgres_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = :name AND relkind = 'r'"
            ),
            {"name": table_name},
        ).one()
    assert row.relrowsecurity is True
    assert row.relforcerowsecurity is True


def test_rls_hides_a_cross_site_approval_request_row(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids_a = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    ids_b = _seed_candidate_run(engine, site_id=site_ids["other_site"], actor_id=site_ids["actor"])
    approvals = PostgresApprovalRepository()
    approval_id_b = uuid4()
    with engine.begin() as c:
        c.execute(insert(approval_request).values(
            id=approval_id_b, site_id=site_ids["other_site"], state="pending", action="promote_baseline",
            initiated_by_actor_id=site_ids["actor"], conversation_id=ids_b["conversation"],
            schedule_run_id=ids_b["schedule_run"], candidate_schedule_version_id=ids_b["candidate"], scenario_version_id=ids_b["scenario_version"],
            parameter_hash="e" * 64, consequence_summary="x", consequence_hash="f" * 64,
            policy_version="v1", expires_at=NOW + timedelta(hours=1), request_effect_key=f"command:{uuid4()}",
        ))

    with site_context(engine, site_ids["site"]) as c:
        # Pass the OTHER site's id deliberately. The repository now also carries
        # an explicit `site_id` predicate, and passing this site's id would let
        # that predicate hide the row -- proving the predicate, not RLS. Asking
        # for the foreign row BY its own site id makes the explicit filter match,
        # so RLS is the only thing left that can return `None`. It is still the
        # real boundary; the predicate is defence in depth on top of it.
        assert approvals.get(c, approval_id=approval_id_b, site_id=site_ids["other_site"]) is None


# --- audit_event is append-only by grant, not just by convention -----------


def test_audit_event_denies_update_and_delete_to_the_runtime_role(governed_postgres_engine) -> None:
    with governed_postgres_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT has_table_privilege('shiftmind_runtime', 'audit_event', 'UPDATE') AS can_update, "
                "has_table_privilege('shiftmind_runtime', 'audit_event', 'DELETE') AS can_delete, "
                "has_table_privilege('shiftmind_runtime', 'audit_event', 'SELECT') AS can_select, "
                "has_table_privilege('shiftmind_runtime', 'audit_event', 'INSERT') AS can_insert, "
                "has_column_privilege('shiftmind_runtime', 'approval_request', 'state', 'UPDATE') AS can_update_approval_state"
            )
        ).one()
    assert row.can_update is False
    assert row.can_delete is False
    assert row.can_select is True
    assert row.can_insert is True
    assert row.can_update_approval_state is True


def test_runtime_role_is_refused_when_it_attempts_to_mutate_audit(governed_postgres_engine, site_ids) -> None:
    for statement in (
        "UPDATE audit_event SET safe_summary = safe_summary WHERE false",
        "DELETE FROM audit_event WHERE false",
    ):
        with pytest.raises(DBAPIError):
            with site_context(governed_postgres_engine, site_ids["site"]) as connection:
                connection.execute(text(statement))


# --- partial unique indexes -------------------------------------------------


def test_partial_index_refuses_a_second_pending_approval_for_one_agent_run(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    agent_run_id = _seed_agent_run(engine, site_id=site_ids["site"], conversation_id=ids["conversation"], actor_id=site_ids["actor"])

    def _row(effect_key):
        return dict(
            id=uuid4(), site_id=site_ids["site"], state="pending", action="promote_baseline",
            initiated_by_actor_id=site_ids["actor"], conversation_id=ids["conversation"], agent_run_id=agent_run_id,
            schedule_run_id=ids["schedule_run"], candidate_schedule_version_id=ids["candidate"], scenario_version_id=ids["scenario_version"],
            parameter_hash="a" * 64, consequence_summary="x", consequence_hash="b" * 64,
            policy_version="v1", expires_at=NOW + timedelta(hours=1), request_effect_key=effect_key,
        )

    with engine.begin() as c:
        c.execute(insert(approval_request).values(**_row(f"tool:{agent_run_id}:call-1")))

    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(approval_request).values(**_row(f"tool:{agent_run_id}:call-2")))


def test_unique_effect_key_admits_no_second_row_for_the_same_tool_call(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    effect_key = f"tool:{uuid4()}:{uuid4()}"

    def _row():
        return dict(
            id=uuid4(), site_id=site_ids["site"], state="pending", action="promote_baseline",
            initiated_by_actor_id=site_ids["actor"], conversation_id=ids["conversation"],
            schedule_run_id=ids["schedule_run"], candidate_schedule_version_id=ids["candidate"], scenario_version_id=ids["scenario_version"],
            parameter_hash="a" * 64, consequence_summary="x", consequence_hash="b" * 64,
            policy_version="v1", expires_at=NOW + timedelta(hours=1), request_effect_key=effect_key,
        )

    with engine.begin() as c:
        c.execute(insert(approval_request).values(**_row()))

    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(approval_request).values(**_row()))


def test_terminalize_is_a_site_scoped_pending_compare_and_set(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    approval_id = uuid4()
    with engine.begin() as c:
        c.execute(insert(approval_request).values(
            id=approval_id, site_id=site_ids["site"], state="pending", action="promote_baseline",
            initiated_by_actor_id=site_ids["actor"], conversation_id=ids["conversation"], schedule_run_id=ids["schedule_run"],
            candidate_schedule_version_id=ids["candidate"], scenario_version_id=ids["scenario_version"], parameter_hash="a" * 64,
            consequence_summary="x", consequence_hash="b" * 64, policy_version="v1", expires_at=NOW + timedelta(hours=1), request_effect_key=f"command:{approval_id}", resource_version=1,
        ))
        repository = PostgresApprovalRepository()
        terminal = repository.terminalize(c, approval_id=approval_id, site_id=site_ids["site"], state="rejected", decided_by_actor_id=site_ids["actor"], decided_at=NOW, expected_resource_version=1)
        lost = repository.terminalize(c, approval_id=approval_id, site_id=site_ids["site"], state="expired", decided_by_actor_id=site_ids["actor"], decided_at=NOW, expected_resource_version=2)
    assert terminal is not None and terminal.state == "rejected" and terminal.resource_version == 2
    assert lost is None


# --- the two audit uniqueness rules hold independently (AD-12) -------------


def _audit_row(*, site_id, actor_id, effect_key, outcome, success, attempt_id=None):
    return dict(
        id=uuid4(), site_id=site_id, attempt_id=attempt_id or uuid4(), request_id=uuid4(),
        initiated_by_actor_id=actor_id, action="promote_baseline", outcome=outcome, success=success,
        effect_key=effect_key, safe_summary="x", parameter_hash="a" * 64, consequence_hash="b" * 64,
        policy_version="v1", app_version="0.1.0", worker_facts={}, evidence_refs=[],
    )


def test_success_audit_rows_are_unique_on_site_effect_key_and_outcome(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    effect_key = str(uuid4())
    with engine.begin() as c:
        c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect_key, outcome="approval_requested", success=True)))

    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect_key, outcome="approval_requested", success=True)))

    # The requested and consumed rows deliberately share the binding effect
    # key; outcome is the disambiguator, and a second pointer-effect row loses.
    with engine.begin() as c:
        c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect_key, outcome="approval_consumed", success=True)))
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect_key, outcome="approval_consumed", success=True)))


def test_failure_audit_rows_are_unique_on_site_and_attempt_id_regardless_of_effect_key(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    attempt_id = uuid4()
    with engine.begin() as c:
        c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_denied", success=False, attempt_id=attempt_id)))

    # Same attempt_id, a DIFFERENT effect_key -- still collides, because the
    # failure rule is keyed on (site_id, attempt_id) alone, not effect_key.
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_denied", success=False, attempt_id=attempt_id)))


# --- TX1 persisted end-to-end through the real adapters --------------------


def _use_case_dependencies():
    return dict(
        schedule_runs=PostgresScheduleRunRepository(),
        baselines=PostgresSiteBaselineReader(),
        approvals=PostgresApprovalRepository(),
        audit_writer=PostgresAuditWriter(),
        conversations=PostgresConversationRepository(),
        approval_expiry_seconds=3600,
        scheduling_baseline_enabled=True,
        clock=lambda: NOW,
    )


def _decision_dependencies(*, now=NOW):
    return dict(
        schedule_runs=PostgresScheduleRunRepository(),
        baselines=PostgresSiteBaselineReader(),
        baseline_writer=PostgresSiteBaselineWriter(),
        memberships=PostgresMembershipReader(),
        approvals=PostgresApprovalRepository(),
        audit_writer=PostgresAuditWriter(),
        conversations=PostgresConversationRepository(),
        scheduling_baseline_enabled=True,
        clock=lambda: now,
    )


def test_tx2_repository_surface_consumes_promotes_reads_payload_and_resumes(
    governed_postgres_engine, site_ids
) -> None:
    engine = governed_postgres_engine
    tx2_site = site_ids["tx2_site"]
    tx2_actor = site_ids["actor"]
    ids = _seed_candidate_run(
        engine, site_id=tx2_site, actor_id=tx2_actor, resource_version=2
    )
    agent_run_id = _seed_agent_run(
        engine,
        site_id=tx2_site,
        conversation_id=ids["conversation"],
        actor_id=tx2_actor,
    )
    payload = {"pending_calls": [{"tool_call_id": "call-promote"}], "turn": {"messages": []}}
    request = RequestApprovalCommandV1(
        site_id=tx2_site, actor_id=tx2_actor, schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"tool:{agent_run_id}:call-promote", request_id=uuid4(),
        conversation_id=ids["conversation"], agent_run_id=agent_run_id, pending_payload=payload,
    )
    with site_context(engine, tx2_site) as c:
        pending_binding = request_approval(c, command=request, **_use_case_dependencies()).binding
        approvals = PostgresApprovalRepository()
        assert approvals.get_pending_payload(
            c, approval_id=pending_binding.approval_id, site_id=tx2_site
        ) == payload
        consumed = approvals.consume(
            c,
            approval_id=pending_binding.approval_id,
            site_id=tx2_site,
            decided_by_actor_id=tx2_actor,
            decided_at=NOW,
            expected_resource_version=pending_binding.resource_version,
        )
        assert consumed is not None and consumed.state == "consumed" and consumed.consumed_at == NOW
        writer = PostgresSiteBaselineWriter()
        first = writer.promote(
            c, site_id=tx2_site, schedule_version_id=ids["candidate"],
            actor_id=tx2_actor, occurred_at=NOW, expected_resource_version=None,
        )
        assert first is not None and first.resource_version == 1
        second = writer.promote(
            c, site_id=tx2_site, schedule_version_id=ids["candidate"],
            actor_id=tx2_actor, occurred_at=NOW, expected_resource_version=1,
        )
        assert second is not None and second.resource_version == 2
        activity = PostgresConversationRepository().resume_agent_run_for_approval(
            c, agent_run_id=agent_run_id, binding=consumed,
            request_id=uuid4(), occurred_at=NOW,
        )
        assert activity.agent_run_status == "agent_running"
        status = c.execute(select(agent_run.c.status, agent_run.c.status_reason).where(agent_run.c.id == agent_run_id)).one()
        assert status.status == "agent_running" and status.status_reason is None


@pytest.mark.parametrize("agent_backed", [False, True])
def test_tx3_terminal_bundle_persists_through_runtime_role_on_both_initiator_paths(
    governed_postgres_engine, site_ids, agent_backed
) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    agent_run_id = _seed_agent_run(engine, site_id=site_ids["site"], conversation_id=ids["conversation"], actor_id=site_ids["actor"]) if agent_backed else None
    request = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
        agent_run_id=agent_run_id, pending_payload={"pending_calls": [], "turn": {}} if agent_backed else None,
    )
    with site_context(engine, site_ids["site"]) as c:
        pending_result = request_approval(c, command=request, **_use_case_dependencies())
    command = DecideApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], approval_id=pending_result.binding.approval_id,
        decision="reject", expected_resource_version=1, request_id=uuid4(),
    )
    with site_context(engine, site_ids["site"]) as c:
        result = decide_approval(c, command=command, **_decision_dependencies())
    with engine.connect() as c:
        stored = c.execute(select(approval_request).where(approval_request.c.id == result.binding.approval_id)).one()
        audits = c.execute(select(audit_event.c.outcome).where(audit_event.c.approval_id == result.binding.approval_id)).scalars().all()
        events = c.execute(select(persisted_event.c.event_type).where(
            persisted_event.c.stream_id == ids["conversation"],
            persisted_event.c.event_type == "approval_request",
        )).scalars().all()
        if agent_run_id:
            run = c.execute(select(agent_run.c.status, agent_run.c.status_reason).where(agent_run.c.id == agent_run_id)).one()
            assert (run.status, run.status_reason) == ("agent_cancelled", "approval_rejected")
    assert stored.state == "rejected" and stored.resource_version == 2
    assert sorted(audits) == ["approval_rejected", "approval_requested"]
    assert events.count("approval_request") == 2


def test_runtime_role_has_the_two_tx3_update_grants(governed_postgres_engine) -> None:
    with governed_postgres_engine.connect() as c:
        row = c.execute(text(
            "SELECT has_column_privilege('shiftmind_runtime','agent_run','status_reason','UPDATE') AS run_reason, "
            "has_column_privilege('shiftmind_runtime','approval_request','state','UPDATE') AS approval_state"
        )).one()
    assert row.run_reason is True and row.approval_state is True


def test_dismissing_expiry_releases_the_schedule_run_slot_for_a_real_second_request(
    governed_postgres_engine, site_ids
) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    agent_run_id = _seed_agent_run(engine, site_id=site_ids["site"], conversation_id=ids["conversation"], actor_id=site_ids["actor"])
    request = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"tool:{agent_run_id}:call-1", request_id=uuid4(), conversation_id=ids["conversation"],
        agent_run_id=agent_run_id, pending_payload={"pending_calls": [{"tool_call_id": "call-1"}], "turn": {}},
    )
    with site_context(engine, site_ids["site"]) as c:
        first = request_approval(c, command=request, **_use_case_dependencies())
    command = DecideApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], approval_id=first.binding.approval_id,
        decision="reject", expected_resource_version=1, request_id=uuid4(),
    )
    with site_context(engine, site_ids["site"]) as c:
        expired = decide_approval(c, command=command, **_decision_dependencies(now=NOW + timedelta(hours=2)))
    # The ORIGINAL agent run cannot host a second approval and never could:
    # EAD-5 terminalizes it here, and `pause_agent_run_for_approval` claims only
    # `agent_running`. Asserting that is what keeps the ledger honest -- the slot
    # `uq_approval_request_pending_agent_run` guards is released onto a run that
    # is, by design, finished.
    with engine.connect() as c:
        cancelled = c.execute(select(agent_run.c.status, agent_run.c.status_reason).where(agent_run.c.id == agent_run_id)).one()
    assert (cancelled.status, cancelled.status_reason) == ("agent_cancelled", "approval_expired")

    # The slot that matters in production is `uq_approval_request_pending_run`
    # on (site_id, schedule_run_id), and the way a planner actually refills it is
    # `request_approval` -- NOT a raw `create_pending`. Driving the real use case
    # is what exercises Trap 8's blocker: `ApprovalAlreadyPendingError` counts
    # overdue rows too (`request_approval.py`, `any(state == "pending")`). A
    # direct insert proves the partial index, and nothing else.
    second_request = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
        agent_run_id=None, pending_payload=None,
    )
    with site_context(engine, site_ids["site"]) as c:
        second = request_approval(c, command=second_request, **_use_case_dependencies())
    with engine.connect() as c:
        states = c.execute(select(approval_request.c.state).where(approval_request.c.schedule_run_id == ids["schedule_run"]).order_by(approval_request.c.created_at)).scalars().all()
    assert expired.outcome == "expired"
    assert second.binding.state == "pending"
    assert states == ["expired", "pending"]


def test_tx1_persists_the_planner_path_bundle_through_the_real_adapters(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    command = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"command:{site_ids['actor']}:request_approval:{uuid4()}",
        request_id=uuid4(), conversation_id=ids["conversation"],
    )
    with site_context(engine, site_ids["site"]) as c:
        result = request_approval(c, command=command, **_use_case_dependencies())

    with engine.connect() as c:
        stored = c.execute(select(approval_request).where(approval_request.c.id == result.binding.approval_id)).one()
        audit_rows = c.execute(select(audit_event).where(audit_event.c.approval_id == result.binding.approval_id)).all()
    assert stored.state == "pending"
    assert stored.candidate_schedule_version_id == ids["candidate"]
    assert len(audit_rows) == 1
    assert audit_rows[0].outcome == "approval_requested"
    assert audit_rows[0].success is True


def test_tx1_persists_the_agent_pending_payload_byte_identically_and_pauses_the_run(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    agent_run_id = _seed_agent_run(engine, site_id=site_ids["site"], conversation_id=ids["conversation"], actor_id=site_ids["actor"])
    pending_payload = {"pending_calls": [{"tool_call_id": "call-1"}], "turn": {"messages": ["hello"]}}
    command = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2, expected_baseline_schedule_version=None,
        request_effect_key=f"tool:{agent_run_id}:call-1", request_id=uuid4(),
        conversation_id=ids["conversation"], agent_run_id=agent_run_id, pending_payload=pending_payload,
    )
    with site_context(engine, site_ids["site"]) as c:
        result = request_approval(c, command=command, **_use_case_dependencies())

    with engine.connect() as c:
        stored_payload = c.execute(select(approval_request.c.pending_payload).where(approval_request.c.id == result.binding.approval_id)).scalar_one()
        run_status = c.execute(select(agent_run.c.status).where(agent_run.c.id == agent_run_id)).scalar_one()
    assert stored_payload == pending_payload
    assert run_status == "approval_required"


@pytest.mark.parametrize(
    "make_command",
    [
        lambda ids, site_id: dict(expected_resource_version=999),
        lambda ids, site_id: dict(expected_baseline_schedule_version="a-version-that-does-not-exist"),
    ],
)
def test_tx1_refuses_and_writes_nothing_against_the_real_database(governed_postgres_engine, site_ids, make_command) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    overrides = make_command(ids, site_ids["site"])
    command = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=overrides.get("expected_resource_version", 2),
        expected_baseline_schedule_version=overrides.get("expected_baseline_schedule_version"),
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
    )
    with pytest.raises((StaleResourceVersionError, StaleBaselineVersionError)):
        with site_context(engine, site_ids["site"]) as c:
            request_approval(c, command=command, **_use_case_dependencies())

    with engine.connect() as c:
        assert c.execute(select(approval_request).where(approval_request.c.schedule_run_id == ids["schedule_run"])).one_or_none() is None
        assert c.execute(select(audit_event).where(audit_event.c.schedule_run_id == ids["schedule_run"])).one_or_none() is None


def test_tx1_refuses_a_non_completed_run_and_writes_nothing(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], status="solver_infeasible")
    command = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=1, expected_baseline_schedule_version=None,
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
    )
    with pytest.raises(CandidateNotPromotableError):
        with site_context(engine, site_ids["site"]) as c:
            request_approval(c, command=command, **_use_case_dependencies())

    with engine.connect() as c:
        assert c.execute(select(approval_request).where(approval_request.c.schedule_run_id == ids["schedule_run"])).one_or_none() is None


# --- EAD-2: both baseline producers agree; a seeded row is non-null --------


def test_site_baseline_reader_returns_the_same_value_for_a_seeded_row(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    with engine.begin() as c:
        c.execute(insert(site_baseline).values(
            id=uuid4(), site_id=site_ids["site"], schedule_version_id=ids["candidate"], updated_by_actor_id=site_ids["actor"],
        ))
    reader = PostgresSiteBaselineReader()
    with engine.connect() as c:
        result = reader.get(c, site_ids["site"])
    assert result is not None
    assert result.schedule_version_id == ids["candidate"]


def test_both_baseline_producers_return_the_same_value_for_absence_and_for_a_seeded_row(
    governed_postgres_engine, site_ids
) -> None:
    """Decision 8's whole point: BOTH producers move to the one reader together.

    `calculate_comparison` compares the run snapshot's frozen value (sourced
    from the CATALOGUE) against the projection's current value. Moving only one
    of the two producers to `site_baseline` creates permanent false staleness the
    moment Story 4.3 writes a pointer -- the frozen side would be a real version
    and the current side `None` forever.

    Observed failing by reverting either producer to its old hardcoded `None`
    (`literal(None, type_=String)` in the catalogue, or the literal `None` on
    `ScenarioOverviewV1`): the absence case still passes, and this seeded case
    is the one that catches it.
    """
    from adapters.postgres.scenario_catalogue import PostgresScenarioCatalogueReader
    from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader

    engine = governed_postgres_engine
    # The projection parses the fixture payload, so `{}` (enough for every other
    # proof here) is not enough for `get_overview`. A one-row Scenario Range is
    # the minimum that reaches the baseline field this test is about, and it has
    # to be seeded at INSERT time -- `scenario_version` rows are immutable by
    # database trigger (Story 1.1's governed history).
    # `other_site` deliberately: `site_baseline` is UNIQUE per site
    # (`uq_site_baseline_site`) and the seeded-row test above already claims the
    # primary site's single row, so the absence half of this proof could never
    # hold there. This test owns its site's baseline outright.
    test_site = site_ids["other_site"]
    ids = _seed_candidate_run(
        engine, site_id=test_site, actor_id=site_ids["actor"],
        scenario_payload={"Scenario Range": [{"PeriodStartDate": "2026-01-01T00:00:00", "PeriodEndDate": "2026-01-02T00:00:00"}]},
    )
    catalogue = PostgresScenarioCatalogueReader()
    projection = PostgresScenarioProjectionReader()

    # 1) No row: absence is the real "no baseline" state (EAD-2), and both
    #    producers must report it identically.
    with site_context(engine, test_site) as c:
        context_absent = catalogue.get_scenario_context(c, ids["scenario"])
        overview_absent = projection.get_overview(c, ids["scenario"])
    assert context_absent is not None and overview_absent is not None
    assert context_absent.baseline_schedule_version is None
    assert overview_absent.baseline_schedule_version is None

    # 2) Seeded row: both must return the SAME non-null string.
    with engine.begin() as c:
        c.execute(insert(site_baseline).values(
            id=uuid4(), site_id=test_site, schedule_version_id=ids["candidate"],
            updated_by_actor_id=site_ids["actor"],
        ))

    with site_context(engine, test_site) as c:
        context_seeded = catalogue.get_scenario_context(c, ids["scenario"])
        overview_seeded = projection.get_overview(c, ids["scenario"])
    assert context_seeded is not None and overview_seeded is not None
    assert context_seeded.baseline_schedule_version == str(ids["candidate"])
    # The agreement itself -- the assertion the false-staleness trap needs.
    assert overview_seeded.baseline_schedule_version == context_seeded.baseline_schedule_version


def test_downgrade_removes_this_migration_without_revoking_an_ancestor_grant(
    fresh_postgres_database_url: str,
) -> None:
    """Task 2's "working `downgrade()`", proven one step rather than to base.

    A full downgrade to base is blocked at ancestor `c4d5e6f7a8b9`
    (deliberately irreversible), so nothing else exercises THIS migration's
    reversal. The bug it guards: `REVOKE UPDATE (status, status_reason) ON
    agent_run` also strips the `UPDATE (status)` grant created by ancestor
    `c7d6e5f4a3b2`, which stays applied -- after which every claim/finalize
    transition fails under RLS.

    Observed failing by restoring the paired revoke.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    # alembic.ini lives at the REPO root, one level above `backend/`.
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    engine = create_engine(fresh_postgres_database_url)
    try:
        with engine.begin() as c:
            config.attributes["connection"] = c
            command.upgrade(config, "head")
        assert "approval_request" in set(inspect(engine).get_table_names())

        with engine.begin() as c:
            config.attributes["connection"] = c
            command.downgrade(config, "c4d5e6f7a8b9")

        tables = set(inspect(engine).get_table_names())
        assert {"approval_request", "site_baseline", "audit_event"}.isdisjoint(tables)

        with engine.connect() as c:
            # The ancestor's grant must survive this migration's reversal.
            assert c.execute(text(
                "SELECT has_column_privilege('shiftmind_runtime', 'agent_run', 'status', 'UPDATE')"
            )).scalar_one() is True
            # ...and the column this migration added is gone with it.
            assert "status_reason" not in {
                col["name"] for col in inspect(engine).get_columns("agent_run")
            }

        # And it goes back up cleanly.
        with engine.begin() as c:
            config.attributes["connection"] = c
            command.upgrade(config, "head")
        assert "approval_request" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# --- Decision 9: returning commits, raising rolls back ---------------------
#
# Every other decision-route test overrides `get_site_context` with
# `lambda: object()` -- no transaction at all -- so none of them can observe
# whether a 409 response COMMITTED the terminal bundle or discarded it. The
# story calls this "the single most dangerous line"; this is the only place it
# is actually proven, because it needs a real transaction and a real route.

_SESSION_TOKEN = "governance-session"
_CSRF_TOKEN = "governance-csrf"


@pytest.fixture()
def decision_http_client(governed_postgres_engine, site_ids):
    restricted = governed_postgres_engine.url.set(
        username="shiftmind_login", password="shiftmind_login"
    ).render_as_string(hide_password=False)
    settings = replace(
        default_settings(), database_url=restricted, scheduling_baseline_enabled=True
    )
    session = ResolvedSession(
        app_user_id=site_ids["actor"],
        site_id=site_ids["site"],
        csrf_token_hash=hash_secret(_CSRF_TOKEN),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    class _Store:
        def resolve_session(self, token_hash):
            return session if token_hash == hash_secret(_SESSION_TOKEN) else None

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: _Store()
    try:
        with TestClient(app) as client:
            yield client, settings
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _governance_headers(settings, *, key):
    return {
        "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
        "Origin": settings.app_base_url,
        "X-CSRF-Token": _CSRF_TOKEN,
        "Idempotency-Key": key,
    }


def test_provenance_foreign_and_absent_runs_have_byte_identical_404s(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    foreign = _seed_candidate_run(
        governed_postgres_engine, site_id=site_ids["other_site"], actor_id=site_ids["actor"],
    )
    headers = _governance_headers(settings, key="unused-by-get")
    foreign_response = client.get(
        "/api/v1/approvals/provenance",
        params={"schedule_run_id": str(foreign["schedule_run"])}, headers=headers,
    )
    absent_response = client.get(
        "/api/v1/approvals/provenance",
        params={"schedule_run_id": str(uuid4())}, headers=headers,
    )

    assert foreign_response.status_code == absent_response.status_code == 404
    assert foreign_response.content == absent_response.content
    assert foreign_response.json()["code"] == "schedule_run_not_found"


def test_a_409_expiry_response_commits_the_terminal_row_through_the_real_route(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    """The route RETURNS a problem response, so `get_site_context` commits.

    Mutation that must turn this red: change the terminalizing branch's
    `return problem_response(...)` to `raise HTTPException(status_code=409)`.
    The status assertion still passes -- and the follow-up GET then reports
    `pending`, because the exception rolled TX3 back.
    """
    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(
        engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2
    )
    # `site_ids` is module-scoped, so an earlier test in this file may have left
    # a `site_baseline` row behind. Read the live pointer rather than assuming
    # absence -- TX1 refuses on a baseline mismatch before anything else runs.
    with site_context(engine, site_ids["site"]) as c:
        live_baseline = PostgresSiteBaselineReader().get(c, site_ids["site"])
    request = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
        expected_resource_version=2,
        expected_baseline_schedule_version=str(live_baseline.schedule_version_id) if live_baseline else None,
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
        conversation_id=ids["conversation"], agent_run_id=None, pending_payload=None,
    )
    with site_context(engine, site_ids["site"]) as c:
        pending_binding = request_approval(c, command=request, **_use_case_dependencies()).binding

    # Past `expires_at`, so revalidation terminalizes to `expired` (EAD-7 runs
    # TX3 with `approval_expired` instead of the requested reject).
    app.dependency_overrides[get_clock] = lambda: NOW + timedelta(hours=2)

    response = client.post(
        f"/api/v1/approvals/{pending_binding.approval_id}/decision",
        headers=_governance_headers(settings, key="commit-guard"),
        json={"decision": "reject", "expected_resource_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "approval_expired"

    # The row survived the refusing response -- read on a SEPARATE transaction,
    # which is the only way to tell a commit from an uncommitted write.
    follow_up = client.get(
        f"/api/v1/approvals/{pending_binding.approval_id}",
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={_SESSION_TOKEN}",
            "Origin": settings.app_base_url,
        },
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["state"] == "expired"
    with engine.connect() as c:
        stored = c.execute(
            select(approval_request.c.state, approval_request.c.decided_at).where(
                approval_request.c.id == pending_binding.approval_id
            )
        ).one()
    assert stored.state == "expired" and stored.decided_at is not None


@pytest.mark.parametrize("agent_backed", [False, True])
def test_tx2_promotes_consumes_audits_and_emits_on_both_initiator_paths(
    governed_postgres_engine, site_ids, agent_backed
) -> None:
    engine = governed_postgres_engine
    ids = _seed_candidate_run(
        engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2
    )
    with engine.connect() as c:
        versions_before = [dict(row._mapping) for row in c.execute(
            select(schedule_version).where(schedule_version.c.site_id == site_ids["site"]).order_by(schedule_version.c.id)
        )]
    agent_run_id = _seed_agent_run(
        engine, site_id=site_ids["site"], conversation_id=ids["conversation"],
        actor_id=site_ids["actor"],
    ) if agent_backed else None
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
    payload = {
        "pending_calls": [{
            "tool_call_id": "call-promote", "tool_name": "scheduling_baseline",
            "tool_args_json": "{}",
        }],
        "turn": {"messages": []},
    } if agent_backed else None
    request = RequestApprovalCommandV1(
        site_id=site_ids["site"], actor_id=site_ids["actor"],
        schedule_run_id=ids["schedule_run"], expected_resource_version=2,
        expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
        request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
        conversation_id=ids["conversation"], agent_run_id=agent_run_id,
        pending_payload=payload,
    )
    with site_context(engine, site_ids["site"]) as c:
        pending_binding = request_approval(c, command=request, **_use_case_dependencies()).binding
        result = decide_approval(
            c,
            command=DecideApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                approval_id=pending_binding.approval_id, decision="approve",
                expected_resource_version=pending_binding.resource_version,
                request_id=uuid4(),
            ),
            **_decision_dependencies(),
        )
        assert result.outcome == "consumed"
    with site_context(engine, site_ids["site"]) as c:
        provenance = query_decision_provenance(
            c, schedule_run_id=ids["schedule_run"], site_id=site_ids["site"],
            schedule_runs=PostgresScheduleRunRepository(),
            approvals=PostgresApprovalRepository(), audit_reader=PostgresAuditReader(),
            conversations=PostgresConversationRepository(),
            baselines=PostgresSiteBaselineReader(), clock=lambda: NOW,
        )
    assert provenance is not None
    promotion = next(item for item in provenance.items if item.item_type == "baseline_promotion")
    assert promotion.after_version == str(ids["candidate"])
    assert promotion.before_version == (str(live.schedule_version_id) if live else None)
    with engine.connect() as c:
        stored = c.execute(select(approval_request).where(approval_request.c.id == pending_binding.approval_id)).one()
        baseline = c.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).one()
        audits = c.execute(select(audit_event).where(
            audit_event.c.approval_id == pending_binding.approval_id,
            audit_event.c.outcome == "approval_consumed",
        )).all()
        events = c.execute(select(persisted_event).where(
            persisted_event.c.conversation_id == ids["conversation"],
            persisted_event.c.event_type == "approval_request",
        )).all()
        assert stored.state == "consumed" and stored.consumed_at is not None
        assert baseline.schedule_version_id == ids["candidate"]
        assert len(audits) == 1 and audits[0].effect_key == pending_binding.request_effect_key
        assert len(events) == 2
        if agent_run_id is not None:
            run = c.execute(select(agent_run.c.status, agent_run.c.status_reason).where(agent_run.c.id == agent_run_id)).one()
            assert run.status == "agent_running" and run.status_reason is None
        versions_after = [dict(row._mapping) for row in c.execute(
            select(schedule_version).where(schedule_version.c.site_id == site_ids["site"]).order_by(schedule_version.c.id)
        )]
        assert versions_after == versions_before


def test_approve_route_replays_once_rejects_conflicts_and_audits_denials(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(
        engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2
    )
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        pending_binding = request_approval(
            c,
            command=RequestApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                schedule_run_id=ids["schedule_run"], expected_resource_version=2,
                expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
                request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
                conversation_id=ids["conversation"],
            ),
            **_use_case_dependencies(),
        ).binding
    url = f"/api/v1/approvals/{pending_binding.approval_id}/decision"
    body = {"decision": "approve", "expected_resource_version": 1}
    app.dependency_overrides[get_clock] = lambda: NOW
    first = client.post(url, headers=_governance_headers(settings, key="approve-replay"), json=body)
    replay = client.post(url, headers=_governance_headers(settings, key="approve-replay"), json=body)
    conflict = client.post(
        url, headers=_governance_headers(settings, key="approve-replay"),
        json={"decision": "reject", "expected_resource_version": 1},
    )
    denied = client.post(url, headers=_governance_headers(settings, key="approve-new-key"), json=body)
    assert first.status_code == 200, first.json()
    assert replay.status_code == 200, replay.json()
    assert first.json() == replay.json() and first.json()["state"] == "consumed"
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_key_conflict"
    assert denied.status_code == 409 and denied.json()["code"] == "approval_not_pending"

    second_ids = _seed_candidate_run(
        engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2
    )
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        second_binding = request_approval(
            c,
            command=RequestApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                schedule_run_id=second_ids["schedule_run"], expected_resource_version=2,
                expected_baseline_schedule_version=str(live.schedule_version_id),
                request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
                conversation_id=second_ids["conversation"],
            ),
            **_use_case_dependencies(),
        ).binding
    second_url = f"/api/v1/approvals/{second_binding.approval_id}/decision"
    for key in ("stale-version-1", "stale-version-2"):
        stale = client.post(
            second_url, headers=_governance_headers(settings, key=key),
            json={"decision": "approve", "expected_resource_version": 99},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "stale_resource_version"
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.approval_id == pending_binding.approval_id,
            audit_event.c.outcome == "approval_consumed",
        )).scalar_one() == 1
        denial_rows = c.execute(select(audit_event).where(
            audit_event.c.approval_id == pending_binding.approval_id,
            audit_event.c.outcome == "approval_denied",
        )).all()
        assert len(denial_rows) == 1 and denial_rows[0].success is False
        stale_denials = c.execute(select(audit_event).where(
            audit_event.c.approval_id == second_binding.approval_id,
            audit_event.c.outcome == "approval_denied",
        )).all()
        assert len(stale_denials) == 2
        assert len({row.attempt_id for row in stale_denials}) == 2
        baseline = c.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).one()
        assert baseline.schedule_version_id == ids["candidate"]


def test_runtime_privileges_keep_versions_immutable_and_allow_baseline_cas(
    governed_postgres_engine,
) -> None:
    with governed_postgres_engine.connect() as c:
        privileges = c.execute(text(
            "SELECT "
            "has_table_privilege('shiftmind_runtime','schedule_version','UPDATE') AS version_update, "
            "has_table_privilege('shiftmind_runtime','schedule_version','DELETE') AS version_delete, "
            "has_table_privilege('shiftmind_runtime','site_baseline','INSERT') AS baseline_insert, "
            "has_column_privilege('shiftmind_runtime','site_baseline','schedule_version_id','UPDATE') AS baseline_update"
        )).one()
    assert privileges.version_update is False and privileges.version_delete is False
    assert privileges.baseline_insert is True and privileges.baseline_update is True


def test_baseline_insert_grant_guard_was_demonstrated_red_by_transactional_revoke(
    governed_postgres_engine, site_ids
) -> None:
    """Mutation proof: removing INSERT makes the runtime write fail; rollback restores it."""
    with pytest.raises(DBAPIError):
        with governed_postgres_engine.begin() as c:
            c.execute(text("REVOKE INSERT ON site_baseline FROM shiftmind_runtime"))
            c.execute(text("SET LOCAL ROLE shiftmind_runtime"))
            c.execute(text("SET LOCAL app.site_id = :site_id"), {"site_id": str(site_ids["site"])})
            c.execute(insert(site_baseline).values(
                id=uuid4(), site_id=site_ids["site"], schedule_version_id=uuid4(),
                updated_by_actor_id=site_ids["actor"], resource_version=1,
            ))


def test_not_found_and_policy_precheck_write_no_denial_audit_without_telemetry(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    with governed_postgres_engine.connect() as c:
        before = c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.site_id == site_ids["site"], audit_event.c.outcome == "approval_denied",
        )).scalar_one()
    body = {"decision": "approve", "expected_resource_version": 1}
    missing = client.post(
        f"/api/v1/approvals/{uuid4()}/decision",
        headers=_governance_headers(settings, key="missing-no-audit"), json=body,
    )
    disabled = replace(settings, scheduling_baseline_enabled=False)
    app.dependency_overrides[get_settings] = lambda: disabled
    policy = client.post(
        f"/api/v1/approvals/{uuid4()}/decision",
        headers=_governance_headers(settings, key="policy-no-audit"), json=body,
    )
    assert missing.status_code == 404 and missing.json()["code"] == "approval_not_found"
    assert policy.status_code == 403 and policy.json()["code"] == "approval_not_granted"
    with governed_postgres_engine.connect() as c:
        after = c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.site_id == site_ids["site"], audit_event.c.outcome == "approval_denied",
        )).scalar_one()
    # Decision 7's two deliberately UNAUDITED arms write nothing. This is the
    # negative direction only -- AC4's observability clause is proven separately,
    # against a live failing exporter, in the test below.
    assert after == before


def test_authoritative_audit_survives_a_failing_span_exporter(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    """AC4: observability being disabled or broken cannot remove the record.

    The previous coverage asserted this by COMMENT ("no telemetry exporter is
    involved"), which is the assumption the requirement exists to rule out. Audit
    is PostgreSQL and telemetry is OTel, so the independence is asserted here the
    way `test_manual_run_result_and_evidence_survive_a_failing_span_exporter`
    already does it: with an exporter that really raises in-process, and with
    `calls` asserted so the case cannot pass vacuously.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

    class _RaisingExporter(SpanExporter):
        def __init__(self) -> None:
            self.calls = 0

        def export(self, _spans):
            self.calls += 1
            raise RuntimeError("simulated exporter failure")

        def shutdown(self) -> None:
            return None

    exporter = _RaisingExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(
        engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2
    )
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        binding = request_approval(
            c,
            command=RequestApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                schedule_run_id=ids["schedule_run"], expected_resource_version=2,
                expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
                request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
                conversation_id=ids["conversation"],
            ),
            **_use_case_dependencies(),
        ).binding
    url = f"/api/v1/approvals/{binding.approval_id}/decision"
    app.dependency_overrides[get_clock] = lambda: NOW

    # A span ends -- and the exporter raises -- on both sides of each command.
    with tracer.start_as_current_span("before-denial"):
        pass
    denial = client.post(
        url, headers=_governance_headers(settings, key="otel-denial"),
        json={"decision": "approve", "expected_resource_version": 99},
    )
    with tracer.start_as_current_span("between"):
        pass
    success = client.post(
        url, headers=_governance_headers(settings, key="otel-success"),
        json={"decision": "approve", "expected_resource_version": 1},
    )
    with tracer.start_as_current_span("after-success"):
        pass

    assert denial.status_code == 409 and denial.json()["code"] == "stale_resource_version"
    assert success.status_code == 200 and success.json()["state"] == "consumed"
    # The exporter really ran and really failed; without this the case is vacuous.
    assert exporter.calls >= 3
    with governed_postgres_engine.connect() as c:
        rows = c.execute(
            select(audit_event.c.outcome, audit_event.c.success).where(
                audit_event.c.approval_id == binding.approval_id
            )
        ).all()
        baseline_row = c.execute(
            select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])
        ).one()
    outcomes = {(row.outcome, row.success) for row in rows}
    assert ("approval_denied", False) in outcomes
    assert ("approval_consumed", True) in outcomes
    assert baseline_row.schedule_version_id == ids["candidate"]
    provider.shutdown()


def test_lost_promotion_cas_escapes_route_and_rolls_back_the_real_transaction(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        binding = request_approval(c, command=RequestApprovalCommandV1(
            site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
            expected_resource_version=2,
            expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
            request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
        ), **_use_case_dependencies()).binding
    class _LostWriter:
        def promote(self, *_a, **_k): return None
    app.dependency_overrides[get_site_baseline_writer] = lambda: _LostWriter()
    app.dependency_overrides[get_clock] = lambda: NOW
    response = client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_governance_headers(settings, key="lost-cas"),
        json={"decision": "approve", "expected_resource_version": 1},
    )
    assert response.status_code == 409 and response.json()["code"] == "stale_baseline_version"
    with engine.connect() as c:
        stored = c.execute(select(approval_request.c.state, approval_request.c.consumed_at).where(approval_request.c.id == binding.approval_id)).one()
        count = c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome == "approval_consumed",
        )).scalar_one()
    assert stored.state == "pending" and stored.consumed_at is None and count == 0


def test_lost_consume_cas_escapes_route_without_partial_commit(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        binding = request_approval(c, command=RequestApprovalCommandV1(
            site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
            expected_resource_version=2,
            expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
            request_effect_key=f"command:{uuid4()}", request_id=uuid4(), conversation_id=ids["conversation"],
        ), **_use_case_dependencies()).binding

    real = PostgresApprovalRepository()

    class _LostConsumeRepository:
        def __getattr__(self, name):
            return getattr(real, name)

        def consume(self, *_a, **_k):
            return None

    app.dependency_overrides[get_approval_repository] = lambda: _LostConsumeRepository()
    app.dependency_overrides[get_clock] = lambda: NOW
    response = client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_governance_headers(settings, key="lost-consume"),
        json={"decision": "approve", "expected_resource_version": 1},
    )
    assert response.status_code == 409 and response.json()["code"] == "approval_not_pending"
    with engine.connect() as c:
        stored = c.execute(select(approval_request.c.state).where(approval_request.c.id == binding.approval_id)).scalar_one()
        consumed_audits = c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome == "approval_consumed",
        )).scalar_one()
    assert stored == "pending" and consumed_audits == 0


def test_uncancellable_agent_run_escapes_route_and_rolls_back_terminalization(
    governed_postgres_engine, site_ids, decision_http_client
) -> None:
    client, settings = decision_http_client
    engine = governed_postgres_engine
    ids = _seed_candidate_run(engine, site_id=site_ids["site"], actor_id=site_ids["actor"], resource_version=2)
    agent_run_id = _seed_agent_run(engine, site_id=site_ids["site"], conversation_id=ids["conversation"], actor_id=site_ids["actor"])
    with site_context(engine, site_ids["site"]) as c:
        live = PostgresSiteBaselineReader().get(c, site_ids["site"])
        binding = request_approval(c, command=RequestApprovalCommandV1(
            site_id=site_ids["site"], actor_id=site_ids["actor"], schedule_run_id=ids["schedule_run"],
            expected_resource_version=2,
            expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
            request_effect_key=f"tool:{agent_run_id}:call-rollback", request_id=uuid4(), conversation_id=ids["conversation"],
            agent_run_id=agent_run_id, pending_payload={"pending_calls": [{"tool_call_id": "call-rollback"}], "turn": {}},
        ), **_use_case_dependencies()).binding
    with engine.begin() as c:
        c.execute(update(agent_run).where(agent_run.c.id == agent_run_id).values(status="agent_running"))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_governance_headers(settings, key="uncancellable"),
        json={"decision": "reject", "expected_resource_version": 1},
    )
    assert response.status_code == 409 and response.json()["code"] == "agent_run_not_cancellable"
    with engine.connect() as c:
        stored = c.execute(select(approval_request.c.state).where(approval_request.c.id == binding.approval_id)).scalar_one()
        count = c.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome == "approval_rejected",
        )).scalar_one()
    assert stored == "pending" and count == 0
