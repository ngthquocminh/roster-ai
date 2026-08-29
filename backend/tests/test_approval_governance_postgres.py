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
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from pydantic import TypeAdapter

from api.deps import site_context
from adapters.postgres.approval import PostgresApprovalRepository
from adapters.postgres.audit import PostgresAuditWriter
from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.site_baseline import PostgresSiteBaselineReader
from adapters.postgres.schema import (
    agent_run,
    app_user,
    approval_request,
    audit_event,
    conversation,
    message,
    organization,
    proposal,
    proposal_version,
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
from application.contracts.scenario_projection import AssignmentV1
from application.use_cases.request_approval import (
    CandidateNotPromotableError,
    RequestApprovalCommandV1,
    StaleBaselineVersionError,
    StaleResourceVersionError,
    request_approval,
)

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def site_ids(governed_postgres_engine):
    ids = {name: uuid4() for name in ("org", "site", "other_site", "actor")}
    with governed_postgres_engine.begin() as c:
        c.execute(insert(organization).values(id=ids["org"], name="Approval Governance Org"))
        c.execute(insert(site), [
            {"id": ids["site"], "organization_id": ids["org"], "name": "A"},
            {"id": ids["other_site"], "organization_id": ids["org"], "name": "B"},
        ])
        c.execute(insert(app_user).values(id=ids["actor"], idp_subject="approval-actor", email="approval-actor@example.test"))
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
        c.execute(insert(run_snapshot).values(
            id=ids["run_snapshot"], site_id=site_id, scenario_id=ids["scenario"],
            scenario_version_id=ids["scenario_version"], proposal_id=ids["proposal"],
            proposal_version_id=ids["proposal_version"], payload={}, canonical_hash="c" * 64,
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
                "has_table_privilege('shiftmind_runtime', 'audit_event', 'INSERT') AS can_insert"
            )
        ).one()
    assert row.can_update is False
    assert row.can_delete is False
    assert row.can_insert is True


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

    # A DIFFERENT outcome for the same effect key is a distinct row -- proving
    # the two rules are independent, not one rule keyed on effect_key alone.
    with engine.begin() as c:
        c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect_key, outcome="approval_consumed", success=True)))


def test_failure_audit_rows_are_unique_on_site_and_attempt_id_regardless_of_effect_key(governed_postgres_engine, site_ids) -> None:
    engine = governed_postgres_engine
    attempt_id = uuid4()
    with engine.begin() as c:
        c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_rejected", success=False, attempt_id=attempt_id)))

    # Same attempt_id, a DIFFERENT effect_key -- still collides, because the
    # failure rule is keyed on (site_id, attempt_id) alone, not effect_key.
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_expired", success=False, attempt_id=attempt_id)))


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
