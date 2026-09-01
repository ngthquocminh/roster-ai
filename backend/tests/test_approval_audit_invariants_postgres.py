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
from adapters.postgres.schema import agent_run, approval_request, audit_event, membership, persisted_event, scenario_version, schedule_run, schedule_version, site_baseline
from adapters.postgres.site_baseline import PostgresSiteBaselineReader, PostgresSiteBaselineWriter
from api.deps import get_approval_repository, get_audit_writer, get_clock, get_conversation_repository, get_site_baseline_writer, site_context
from api.main import app
from application.use_cases.request_approval import RequestApprovalCommandV1, request_approval
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval

from tests.test_approval_governance_postgres import (
    NOW,
    _decision_dependencies,
    _governance_headers,
    _seed_agent_run,
    _seed_candidate_run,
    _use_case_dependencies,
    decision_http_client,
    site_ids,
)

pytestmark = pytest.mark.postgres


def _request(engine, ids, site_ids, *, expires_now=False, agent_run_id=None):
    with site_context(engine, site_ids["site"]) as connection:
        live = PostgresSiteBaselineReader().get(connection, site_ids["site"])
        result = request_approval(
            connection,
            command=RequestApprovalCommandV1(
                site_id=site_ids["site"], actor_id=site_ids["actor"],
                schedule_run_id=ids["schedule_run"], expected_resource_version=2,
                expected_baseline_schedule_version=str(live.schedule_version_id) if live else None,
                request_effect_key=f"command:{uuid4()}", request_id=uuid4(),
                conversation_id=ids["conversation"], agent_run_id=agent_run_id,
                # A resumable pause needs a real pending call; an empty
                # `pending_calls` list makes TX2's resume refuse with a 422
                # before any injected fault can fire.
                pending_payload={"pending_calls": [{"tool_call_id": "call-fault"}], "turn": {}} if agent_run_id else None,
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


def _counts(engine, binding):
    """Multiplicity, not membership. `_state`'s set collapses a duplicated row,
    which is precisely what an "exactly once" assertion must be able to see."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(audit_event.c.outcome, audit_event.c.success, func.count().label("n"))
            .where(audit_event.c.approval_id == binding.approval_id)
            .group_by(audit_event.c.outcome, audit_event.c.success)
        ).all()
    return {(row.outcome, row.success): row.n for row in rows}


def test_initial_promotion_is_exactly_once(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 200 and response.json()["state"] == "consumed"
    assert _state(governed_postgres_engine, binding)[0] == "consumed"
    assert _counts(governed_postgres_engine, binding) == {("approval_requested", True): 1, ("approval_consumed", True): 1}
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
    with governed_postgres_engine.connect() as connection:
        before = connection.execute(select(func.count()).select_from(site_baseline)).scalar_one()
        # Prior candidates must survive a replacement untouched -- CAS moves the
        # pointer, it never rewrites or removes the versions it points away from.
        prior_versions = connection.execute(
            select(schedule_version.c.id, schedule_version.c.canonical_hash)
            .where(schedule_version.c.site_id == site_ids["site"]).order_by(schedule_version.c.id)
        ).all()
    assert _post(client, settings, binding).status_code == 200
    with governed_postgres_engine.connect() as connection:
        row = connection.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).one()
        after = connection.execute(select(func.count()).select_from(site_baseline)).scalar_one()
        still = connection.execute(
            select(schedule_version.c.id, schedule_version.c.canonical_hash)
            .where(schedule_version.c.site_id == site_ids["site"]).order_by(schedule_version.c.id)
        ).all()
    assert row.schedule_version_id == ids["candidate"] and after == before
    assert still == prior_versions
    assert _counts(governed_postgres_engine, binding)[("approval_consumed", True)] == 1


def _set_membership_revoked(engine, site_ids, value):
    with engine.begin() as connection:
        connection.execute(update(membership).where(
            membership.c.app_user_id == site_ids["actor"], membership.c.site_id == site_ids["site"]
        ).values(revoked_at=value))


def test_business_mismatch_terminalizes_stale(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    # `site_ids` and `governed_postgres_engine` are MODULE-scoped, so the
    # revocation below is shared state. Restoring it outside a `finally` lets
    # one real failure here cascade into every later test in the module, and
    # seven of those are named proof nodes -- the artifact would then report
    # eight failed gates for one defect and destroy per-fixture attribution.
    _set_membership_revoked(governed_postgres_engine, site_ids, NOW)
    try:
        app.dependency_overrides[get_clock] = lambda: NOW
        response = _post(client, settings, binding)
        assert response.status_code == 409 and response.json()["code"] == "approval_stale"
        assert _state(governed_postgres_engine, binding)[0] == "stale"
    finally:
        _set_membership_revoked(governed_postgres_engine, site_ids, None)


def test_altered_parameter_terminalizes_stale(governed_postgres_engine, site_ids, decision_http_client):
    """The run's resource version is inside the signed `parameter` digest
    (`decide_approval.py` -- `revalidate_binding`), so moving it moves the hash."""
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    with governed_postgres_engine.begin() as connection:
        connection.execute(update(schedule_run).where(schedule_run.c.id == ids["schedule_run"]).values(resource_version=3))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 409 and response.json()["code"] == "approval_stale"
    assert _state(governed_postgres_engine, binding)[0] == "stale"
    assert _counts(governed_postgres_engine, binding)[("approval_stale", True)] == 1


def test_changed_baseline_terminalizes_stale(governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    moved = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    with site_context(governed_postgres_engine, site_ids["site"]) as connection:
        live = PostgresSiteBaselineReader().get(connection, site_ids["site"])
        assert PostgresSiteBaselineWriter().promote(
            connection, site_id=site_ids["site"], schedule_version_id=moved["candidate"],
            actor_id=site_ids["actor"], occurred_at=NOW,
            expected_resource_version=live.resource_version if live else None,
        ) is not None
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 409 and response.json()["code"] == "approval_stale"
    assert _state(governed_postgres_engine, binding)[0] == "stale"


def test_replaced_candidate_terminalizes_stale(governed_postgres_engine, site_ids, decision_http_client):
    """Decision 3's mismatch row names "candidate missing / no longer feasible".

    The *infeasible* half is unrepresentable rather than untested:
    `ScheduleVersionV1.feasible_solver_status` is a Literal of `OPTIMAL |
    FEASIBLE`, so `get_candidate` cannot return an infeasible candidate -- it
    raises `ValidationError` instead. The reachable half is a candidate that no
    longer matches the id the binding was signed against, which is the same
    `valid_candidate` arm of `revalidate_binding`."""
    client, settings = decision_http_client
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    binding = _request(governed_postgres_engine, ids, site_ids)
    with governed_postgres_engine.begin() as connection:
        payload = connection.execute(select(schedule_version.c.payload).where(schedule_version.c.id == ids["candidate"])).scalar_one()
        connection.execute(update(schedule_version).where(schedule_version.c.id == ids["candidate"]).values(
            payload={**payload, "schedule_version_id": str(uuid4())}
        ))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding)
    assert response.status_code == 409 and response.json()["code"] == "approval_stale"
    assert _state(governed_postgres_engine, binding)[0] == "stale"


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


# TX2 writes the event through a DIFFERENT conversation method per initiator
# path (`promote_baseline` -- `append_approval_request_activity` for the planner,
# `resume_agent_run_for_approval` for the agent). Faulting only one leaves the
# other path's event write with no rollback proof at all, so both are nodes.
_TX2_FAULTS = {
    "consume": (get_approval_repository, PostgresApprovalRepository, "consume", True),
    "baseline": (get_site_baseline_writer, PostgresSiteBaselineWriter, "promote", True),
    "audit": (get_audit_writer, PostgresAuditWriter, "append", True),
    "event_resume": (get_conversation_repository, PostgresConversationRepository, "resume_agent_run_for_approval", True),
    "event_activity": (get_conversation_repository, PostgresConversationRepository, "append_approval_request_activity", False),
}


@pytest.mark.parametrize("fault", tuple(_TX2_FAULTS))
def test_faulted_tx2_rolls_back_and_retries_once(fault, governed_postgres_engine, site_ids, decision_http_client):
    client, settings = decision_http_client
    dependency, factory, method, agent_backed = _TX2_FAULTS[fault]
    ids = _seed_candidate_run(governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"])
    agent_run_id = _seed_agent_run(
        governed_postgres_engine, site_id=site_ids["site"],
        conversation_id=ids["conversation"], actor_id=site_ids["actor"],
    ) if agent_backed else None
    binding = _request(governed_postgres_engine, ids, site_ids, agent_run_id=agent_run_id)
    with governed_postgres_engine.connect() as connection:
        baseline_before = connection.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).all()
    wrapper = _Faulting(factory(), method)
    app.dependency_overrides[dependency] = lambda: wrapper
    app.dependency_overrides[get_clock] = lambda: NOW
    with pytest.raises(DBAPIError):
        _post(client, settings, binding, key=f"fault-{fault}")
    assert wrapper.calls == 1
    # Decision 4's four post-fault facts, all of them: the binding never
    # terminalizes, the pointer never moves, the faulted attempt leaves no audit
    # row behind, and the paused agent run is still waiting on the decision.
    assert _state(governed_postgres_engine, binding)[0] == "pending"
    with governed_postgres_engine.connect() as connection:
        assert connection.execute(select(site_baseline).where(site_baseline.c.site_id == site_ids["site"])).all() == baseline_before
        assert connection.execute(select(func.count()).select_from(audit_event).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome != "approval_requested",
        )).scalar_one() == 0
        if agent_run_id is not None:
            assert connection.execute(select(agent_run.c.status).where(agent_run.c.id == agent_run_id)).scalar_one() == "approval_required"
    app.dependency_overrides.pop(dependency)
    retry = _post(client, settings, binding, key=f"fault-{fault}")
    assert retry.status_code == 200 and retry.json()["state"] == "consumed"
    assert _counts(governed_postgres_engine, binding)[("approval_consumed", True)] == 1


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


_AC3_PAYLOAD = {"Task": [{"TaskID": "task-1", "Task": "Pick"}]}
_AC3_REFS = (("work-areas-and-tasks", "task-1", "Task", None, None), ("locks", "lock-1", None, None, None))
# Per group, never a blanket "all resolved" (Decision 7): `resolve_lock` searches
# `lambda: ()`, so a locks ref is STRUCTURALLY not_found once the version matches.
_AC3_EXPECTED = {"work-areas-and-tasks": "resolved", "locks": "not_found"}


def _resolve_by_group(connection, scenario_id, refs):
    from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
    reader = PostgresScenarioProjectionReader()
    return {
        ref.group: getattr(reader, "resolve_task" if ref.group == "work-areas-and-tasks" else "resolve_lock")(
            connection, scenario_id, ref.scenario_version_id, ref.record_id
        ).outcome
        for ref in refs
    }


@pytest.mark.parametrize("outcome", ("rejected", "expired", "stale", "denied"))
def test_every_audit_outcome_carries_resolvable_evidence_refs(outcome, governed_postgres_engine, site_ids, decision_http_client):
    """AC3 names five decisions. `test_audit_evidence_refs_resolve_by_group`
    covers `promoted`; this covers the remaining four, resolving each row's
    references through the Decision 6 port methods rather than through gate.py."""
    client, settings = decision_http_client
    ids = _seed_candidate_run(
        governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"],
        scenario_payload=_AC3_PAYLOAD, evidence_ref_records=_AC3_REFS,
    )
    binding = _request(governed_postgres_engine, ids, site_ids, expires_now=outcome == "expired")
    if outcome == "stale":
        with governed_postgres_engine.begin() as connection:
            connection.execute(update(schedule_run).where(schedule_run.c.id == ids["schedule_run"]).values(resource_version=3))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(
        client, settings, binding,
        decision="reject" if outcome == "rejected" else "approve",
        version=99 if outcome == "denied" else 1,
    )
    assert response.status_code == (200 if outcome == "rejected" else 409)
    expected_row = "approval_denied" if outcome == "denied" else f"approval_{outcome}"
    with site_context(governed_postgres_engine, site_ids["site"]) as connection:
        from adapters.postgres.audit import PostgresAuditReader
        audits = PostgresAuditReader().list_for_schedule_run(
            connection, schedule_run_id=ids["schedule_run"], site_id=site_ids["site"]
        )
        row = next(item for item in audits if item.outcome == expected_row)
        assert row.evidence_refs, "a resolved candidate must never yield an empty reference set"
        resolved = _resolve_by_group(connection, ids["scenario"], row.evidence_refs)
    assert resolved == _AC3_EXPECTED


def test_denial_whose_candidate_is_absent_carries_an_empty_set(governed_postgres_engine, site_ids, decision_http_client):
    """AC3's absence clause, OBSERVED rather than assumed. Corrupting the stored
    `schedule_version.payload` makes `get_candidate` raise `ValidationError` in
    the denial arm (`api/routers/approvals.py`), which is the only production
    path that produces `evidence_refs=()`. The admission check raises before
    `revalidate_binding` runs, so the corrupt payload cannot short-circuit it."""
    client, settings = decision_http_client
    ids = _seed_candidate_run(
        governed_postgres_engine, site_id=site_ids["site"], actor_id=site_ids["actor"],
        scenario_payload=_AC3_PAYLOAD, evidence_ref_records=_AC3_REFS,
    )
    binding = _request(governed_postgres_engine, ids, site_ids)
    with governed_postgres_engine.begin() as connection:
        connection.execute(update(schedule_version).where(schedule_version.c.id == ids["candidate"]).values(
            payload={"no_longer": "a ScheduleVersionV1"}
        ))
    app.dependency_overrides[get_clock] = lambda: NOW
    response = _post(client, settings, binding, version=99)
    assert response.status_code == 409 and response.json()["code"] == "stale_resource_version"
    with governed_postgres_engine.connect() as connection:
        refs = connection.execute(select(audit_event.c.evidence_refs).where(
            audit_event.c.approval_id == binding.approval_id,
            audit_event.c.outcome == "approval_denied",
        )).scalar_one()
    assert refs == [], "absence must be recorded as an empty set, not inferred from a missing row"
    assert _state(governed_postgres_engine, binding)[0] == "pending"


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
