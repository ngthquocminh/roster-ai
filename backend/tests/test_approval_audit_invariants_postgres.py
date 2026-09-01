"""Story 4.5 release-blocking proofs for approval and authoritative audit."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from adapters.postgres.approval import PostgresApprovalRepository
from adapters.postgres.audit import PostgresAuditWriter
from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.schema import approval_request, audit_event, membership, persisted_event, scenario_version, site_baseline
from adapters.postgres.site_baseline import PostgresSiteBaselineReader, PostgresSiteBaselineWriter
from api.deps import get_approval_repository, get_audit_writer, get_clock, get_conversation_repository, get_site_baseline_writer, site_context
from api.main import app
from application.use_cases.request_approval import RequestApprovalCommandV1, request_approval
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval

from tests.test_approval_governance_postgres import (
    NOW,
    _decision_dependencies,
    _governance_headers,
    _seed_candidate_run,
    _use_case_dependencies,
    decision_http_client,
    site_ids,
)

pytestmark = pytest.mark.postgres


def _request(engine, ids, site_ids, *, expires_now=False):
    with site_context(engine, site_ids["site"]) as connection:
        live = PostgresSiteBaselineReader().get(connection, site_ids["site"])
        result = request_approval(
            connection,
            command=RequestApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                schedule_run_id=ids["schedule_run"], expected_resource_version=2,
                expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
                request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
                conversation_id=ids["conversation"],
            ),
            **_use_case_dependencies(),
        )
        binding = result.binding
    if expires_now:
        with engine.begin() as connection:
            connection.execute(update(approval_request).where(approval_request.c.id == binding.approval_id).values(expires_at=NOW))
    return binding


def _post(client, settings, binding, *, decision="approve", key=None, version=1):
    return client.post(
        f"/api/v1/approvals/{binding.approval_id}/decision",
        headers=_governance_headers(settings, key=key or uuid4().hex),
        json={"decision": decision, "expected_resource_version": version},
    )


def _state(engine, binding):
    with engine.connect() as connection:
        state = connection.execute(select(approval_request.c.state).where(approval_request.c.id == binding.approval_id)).scalar_one()
        rows = connection.execute(select(audit_event.c.outcome, audit_event.c.success).where(audit_event.c.approval_id == binding.approval_id)).all()
    return state, {(row.outcome, row.success) for row in rows}


def test_initial_promotion_is_exactly_once(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 200 and response.json()["state"] == "consumed"
    state, outcomes = _state(governed_postgres_engine, binding)
    assert state == "consumed"
    assert outcomes == {("approval_requested", True), ("approval_consumed", True)}
    with governed_postgres_engine.connect() as connection:
        baseline = connection.execute(select(site_baseline.c.schedule_version_id).where(site_baseline.c.site_id == site_ids["site"])).scalar_one()
    assert baseline == ids["candidate"]


def test_replacement_is_exactly_once(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    with site_context(governed_postgres_engine, site_ids["site"]) as connection:
        live = PostgresSiteBaselineReader().get(connection, site_ids["site"])
    if live is None:
        prior = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
        with site_context(governed_postgres_engine, site_ids["site"]) as connection:
            assert PostgresSiteBaselineWriter().promote(
                connection, site_id=site_ids["site"], schedule_version_id=prior["candidate"],
                actor_id=site_ids["actor"], occurred_at=NOW, expected_resource_version=None,
            ) is not None
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    before = None
    with governed_postgres_engine.connect() as connection:
        before = connection.execute(select(func.count()).select_from(site_baseline)).scalar_one()
    assert _post(client, settings, binding).status_code == 200
    with governed_postgres_engine.connect() as connection:
        row = connection.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).one()
        after = connection.execute(select(func.count()).select_from(site_baseline)).scalar_one()
    assert row.schedule_version_id == ids["candidate"] and after == before


def test_business_mismatch_terminalizes_stale(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    with governed_postgres_engine.begin() as connection:
        connection.execute(update(membership).where(membership.c.app_user_id == site_ids["actor"], membership.c.site_id == site_ids["site"]).values(revoked_at=NOW))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 409 and response.json()["code"] == "approval_stale"
    assert _state(governed_postgres_engine, binding)[0] == "stale"
    with governed_postgres_engine.begin() as connection:
        connection.execute(update(membership).where(membership.c.app_user_id == site_ids["actor"], membership.c.site_id == site_ids["site"]).values(revoked_at=None))


def test_expiry_terminalizes_expired(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids, expires_now=True)
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 409 and response.json()["code"] == "approval_expired"
    assert _state(governed_postgres_engine, binding)[0] == "expired"


def test_rejection_terminalizes_rejected(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding, decision="reject")
    assert response.status_code == 200 and response.json()["state"] == "rejected"
    assert _state(governed_postgres_engine, binding)[0] == "rejected"


def test_command_replay_is_idempotent(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    key = uuid4().hex
    first = _post(client, settings, binding, key=key)
    replay = _post(client, settings, binding, key=key)
    conflict = _post(client, settings, binding, key=key, decision="reject")
    assert first.status_code == replay.status_code == 200 and first.json() == replay.json()
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_key_conflict"
    with governed_postgres_engine.connect() as connection:
        count = connection.execute(select(func.count()).select_from(audit_event).where(audit_event.c.approval_id == binding.approval_id, audit_event.c.outcome == "approval_consumed")).scalar_one()
    assert count == 1


def test_overdue_reads_are_pure(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids, expires_now=True)
    app.dependency_overrides[get_clock] = lambda: NOW + timedelta(seconds=1)
    with governed_postgres_engine.connect() as connection:
        before = connection.execute(select(func.count()).select_from(persisted_event).where(persisted_event.c.site_id == site_ids["site"])).scalar_one()
    headers = _governance_headers(settings, key="unused-read")
    assert client.get(f"/api/v1/approvals/{binding.approval_id}", headers=headers).status_code == 200
    assert client.get("/api/v1/approvals/provenance", params={"schedule_run_id": str(ids["schedule_run"])}, headers=headers).status_code == 200
    with governed_postgres_engine.connect() as connection:
        state = connection.execute(select(approval_request.c.state).where(approval_request.c.id == binding.approval_id)).scalar_one()
        after = connection.execute(select(func.count()).select_from(persisted_event).where(persisted_event.c.site_id == site_ids["site"])).scalar_one()
    assert state == "pending" and after == before


class _Faulting:
    def __init__(self, target, method):
        self.target, self.method, self.calls = target, method, 0
    def __getattr__(self, name):
        if name != self.method:
            return getattr(self.target, name)
        def fail(*_args, **_kwargs):
            self.calls += 1
            raise DBAPIError("story-4.5 injected write", {}, RuntimeError("injected"))
        return fail


@pytest.mark.parametrize("fault", ("consume", "baseline", "audit", "event"))
def test_faulted_tx2_rolls_back_and_retries_once(fault, governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    targets = {
        "consume": (get_approval_repository, PostgresApprovalRepository(), "consume"),
        "baseline": (get_site_baseline_writer, PostgresSiteBaselineWriter(), "promote"),
        "audit": (get_audit_writer, PostgresAuditWriter(), "append"),
        "event": (get_conversation_repository, PostgresConversationRepository(), "append_approval_request_activity"),
    }
    dependency, target, method = targets[fault]
    wrapper = _Faulting(target, method)
    app.dependency_overrides[dependency] = lambda: wrapper
    app.dependency_overrides[get_clock] = lambda: NOW
    with pytest.raises(DBAPIError):
        _post(client, settings, binding, key=f"fault-{fault}")
    assert wrapper.calls == 1
    assert _state(governed_postgres_engine, binding)[0] == "pending"
    app.dependency_overrides.pop(dependency)
    retry = _post(client, settings, binding, key=f"fault-{fault}")
    assert retry.status_code == 200 and retry.json()["state"] == "consumed"
    assert ("approval_consumed", True) in _state(governed_postgres_engine, binding)[1]


def test_audit_evidence_refs_resolve_by_group(governed_postgres_engine, site_ids):
    payload = {"Task": [{"TaskID": "task-1", "Task": "Pick"}]}
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"], scenario_payload=payload, evidence_ref_records=(("work-areas-and-tasks", "task-1", "Task", None, None), ("locks", "lock-1", None, None, None)))
    binding = _request(governed_postgres_engine, ids, site_ids)
    with site_context(governed_postgres_engine, site_ids["site"]) as connection:
        from adapters.postgres.schedule_run import PostgresScheduleRunRepository
        candidate = PostgresScheduleRunRepository().get_candidate(connection, schedule_run_id=ids["schedule_run"], site_id=site_ids["site"])
        assert candidate is not None and candidate.evidence_refs
        result = decide_approval(
            connection,
            command=DecideApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                approval_id=binding.approval_id, decision="approve",
                expected_resource_version=1, request_id=uuid4(),
            ),
            **_decision_dependencies(),
        )
        assert result.outcome == "consumed"
        from adapters.postgres.audit import PostgresAuditReader
        audits = PostgresAuditReader().list_for_schedule_run(
            connection, schedule_run_id=ids["schedule_run"], site_id=site_ids["site"]
        )
        consumed = next(row for row in audits if row.outcome == "approval_consumed")
        assert consumed.evidence_refs
        assert consumed.evidence_refs == candidate.evidence_refs
        from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
        reader = PostgresScenarioProjectionReader()
        outcomes = {
            ref.group: getattr(reader, "resolve_task" if ref.group == "work-areas-and-tasks" else "resolve_lock")(
                connection, ids["scenario"], ref.scenario_version_id, ref.record_id
            ).outcome
            for ref in consumed.evidence_refs
        }
    # Locks are structurally not_found because resolve_lock searches lambda: ().
    assert outcomes == {"work-areas-and-tasks": "resolved", "locks": "not_found"}
    assert binding.approval_id


def test_superseding_scenario_version_reports_version_mismatch(governed_postgres_engine, site_ids):
    payload = {"Task": [{"TaskID": "task-1", "Task": "Pick"}]}
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"], scenario_payload=payload, evidence_ref_records=(("work-areas-and-tasks", "task-1", "Task", None, None),))
    with governed_postgres_engine.begin() as connection:
        connection.execute(insert(scenario_version).values(id=uuid4(), site_id=site_ids["site"], scenario_id=ids["scenario"], fixture_id=f"superseding-{uuid4().hex}", version="v2", payload=payload, checksum_digest="b" * 64))
    with site_context(governed_postgres_engine, site_ids["site"]) as connection:
        from adapters.postgres.schedule_run import PostgresScheduleRunRepository
        from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
        ref = PostgresScheduleRunRepository().get_candidate(connection, schedule_run_id=ids["schedule_run"], site_id=site_ids["site"]).evidence_refs[0]
        result = PostgresScenarioProjectionReader().resolve_task(connection, ids["scenario"], ref.scenario_version_id, ref.record_id)
    assert result.outcome == "version_mismatch"


def test_audit_uniqueness_covers_the_closed_outcome_vocabulary(governed_postgres_engine, site_ids):
    from tests.test_approval_governance_postgres import _audit_row
    success = ("approval_requested", "approval_consumed", "approval_rejected", "approval_expired", "approval_stale")
    for outcome in success:
        effect = f"integrity:{outcome}:{uuid4()}"
        with governed_postgres_engine.begin() as connection:
            connection.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect, outcome=outcome, success=True)))
        with pytest.raises(IntegrityError):
            with governed_postgres_engine.begin() as connection:
                connection.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=effect, outcome=outcome, success=True)))
    attempt = uuid4()
    with governed_postgres_engine.begin() as connection:
        connection.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_denied", success=False, attempt_id=attempt)))
    with pytest.raises(IntegrityError):
        with governed_postgres_engine.begin() as connection:
            connection.execute(insert(audit_event).values(_audit_row(site_id=site_ids["site"], actor_id=site_ids["actor"], effect_key=str(uuid4()), outcome="approval_denied", success=False, attempt_id=attempt)))


def test_approval_audit_path_has_no_telemetry_import_dependency():
    """Disabled telemetry is the structural default; CloudWatch is Epic 6's."""
    from pathlib import Path
    modules = (
        "application/use_cases/request_approval.py",
        "application/use_cases/decide_approval.py",
        "application/use_cases/promote_baseline.py",
        "adapters/postgres/audit.py",
    )
    for module in modules:
        source = (Path(__file__).parents[1] / module).read_text(encoding="utf-8")
        assert "opentelemetry" not in source
        assert "cloudwatch" not in source.casefold()


def test_repeated_denials_keep_distinct_attempts_full_refs_and_identity_roles(
    governed_postgres_engine, site_ids, decision_http_client
):
    client, settings = decision_http_client
    payload = {"Task": [{"TaskID": "task-1", "Task": "Pick"}]}
    ids = _seed_candidate_run(
        governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"],
        scenario_payload=payload,
        evidence_ref_records=(("work-areas-and-tasks", "task-1", "Task", None, None),),
    )
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    for key in ("denial-one", "denial-two"):
        response = _post(client, settings, binding, key=f"{key}-{uuid4().hex[:20]}", version=99)
        assert response.status_code == 409 and response.json()["code"] == "stale_resource_version", response.json()
    with governed_postgres_engine.connect() as connection:
        rows = connection.execute(select(
            audit_event.c.attempt_id, audit_event.c.initiated_by_actor_id,
            audit_event.c.decided_by_actor_id, audit_event.c.worker_facts,
            audit_event.c.evidence_refs,
        ).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome == "approval_denied",
        )).all()
    assert len(rows) == 2 and len({row.attempt_id for row in rows}) == 2
    assert all(row.initiated_by_actor_id == site_ids["actor"] for row in rows)
    assert all(row.decided_by_actor_id == site_ids["actor"] for row in rows)
    assert all(set(row.worker_facts) == {"lease_owner", "attempt_id", "fencing_epoch", "schema_version"} for row in rows)
    assert all(row.evidence_refs for row in rows)
    assert rows[0].evidence_refs == rows[1].evidence_refs
