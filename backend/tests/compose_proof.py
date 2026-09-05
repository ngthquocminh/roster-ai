"""Opt-in proof against the built, networked local composition."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine

from adapters.postgres.proposal import PostgresProposalRepository
from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import (
    SchedulingDraftRequestV1,
    scheduling_draft,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.proposal import DraftConstraintProposalV1
from worker.lease_worker import runtime_context


pytestmark = pytest.mark.compose
REPO_ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"solver_completed", "solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed"}


def _find(value, key: str):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find(child, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find(child, key)
            if found is not None:
                return found
    return None


def _compose(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", "shiftmind-compose-proof", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def _create_deterministic_draft(
    *,
    database_url: str,
    site_id: UUID,
    actor_id: UUID,
    conversation_id: UUID,
    scenario_id: UUID,
    scenario_version_id: UUID,
    task_record_id: str,
):
    """Drive the real draft application boundary without scripting model prose.

    TestModel is still exercised through the public HTTP agent-run route. It is
    deliberately not treated as a source of meaningful fixture identifiers:
    this proof obtains those from the governed projection and supplies them to
    the same capability and repository used by an agent turn.
    """
    engine = create_engine(database_url, hide_parameters=True)
    try:
        with runtime_context(engine, site_id) as connection:
            result = scheduling_draft(
                AgentDepsV1(
                    actor_id=actor_id,
                    site_id=site_id,
                    membership_id=uuid4(),
                    request_id=uuid4(),
                    agent_run_id=uuid4(),
                    conversation_id=conversation_id,
                    scenario_id=scenario_id,
                    scenario_version_id=scenario_version_id,
                    policy_version="one-user-mvp-v1",
                    clock=lambda: datetime.now(timezone.utc),
                    projection_reader=PostgresScenarioProjectionReader(),
                    connection=connection,
                    remaining_budget=AgentBudgetV1(),
                ),
                SchedulingDraftRequestV1(
                    expected_scenario_version_id=scenario_version_id,
                    constraints=(
                        DraftConstraintProposalV1(
                            kind="set_min_workers_per_task",
                            group="work-areas-and-tasks",
                            record_id=task_record_id,
                            n=1,
                        ),
                    ),
                ),
            )
            PostgresProposalRepository().create_draft(
                connection,
                proposal=result.proposal,
                site_id=site_id,
                conversation_id=conversation_id,
                actor_id=actor_id,
            )
            return result.proposal
    finally:
        engine.dispose()


def test_one_command_stack_serves_real_oidc_and_worker() -> None:
    env = dict(os.environ)
    env.update(
        POSTGRES_PORT="55433",
        WEB_PORT="18081",
        APP_ORIGIN="http://localhost:18081",
    )
    origin = env["APP_ORIGIN"]
    try:
        _compose(env, "up", "-d", "--build")
        subprocess.run(
            [sys.executable, "-m", "scripts.record_image_digests"],
            cwd=REPO_ROOT / "backend",
            check=True,
        )
        deadline = time.monotonic() + 120
        while True:
            try:
                if httpx.get(f"{origin}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= deadline:
                raise AssertionError(_compose(env, "logs", "--no-color").stdout)
            time.sleep(1)

        with httpx.Client(follow_redirects=False) as client:
            login = client.get(f"{origin}/api/v1/auth/login")
            authorize = client.get(login.headers["location"])
            callback = client.get(authorize.headers["location"])
            assert callback.status_code == 302
            assert "__Host-shiftmind_session=" in callback.headers["set-cookie"]
            session_cookie = callback.headers["set-cookie"].split(";", 1)[0]
            session = client.get(
                f"{origin}/api/v1/auth/session", headers={"Cookie": session_cookie}
            )
            assert session.status_code == 200
            catalogue = client.get(
                f"{origin}/api/v1/scenarios", headers={"Cookie": session_cookie}
            )
            assert catalogue.status_code == 200
            assert len(catalogue.json()) == 2
            fixture = catalogue.json()[0]
            command_headers = {
                "Cookie": session_cookie,
                "Origin": origin,
                "X-CSRF-Token": session.json()["csrf_token"],
            }
            conversation = client.post(
                f"{origin}/api/v1/conversations",
                headers=command_headers,
                json={
                    "scenario_id": fixture["scenario_id"],
                    "scenario_version_id": fixture["scenario_version_id"],
                },
            )
            assert conversation.status_code == 201, conversation.text
            conversation_id = conversation.json()["id"]
            accepted = client.post(
                f"{origin}/api/v1/conversations/{conversation_id}/messages",
                headers=command_headers,
                json={"text": "Draft a scheduling repair and run optimization."},
            )
            assert accepted.status_code == 201, accepted.text
            executed = client.post(
                f"{origin}/api/v1/conversations/{conversation_id}/agent-runs/"
                f"{accepted.json()['agent_run_id']}/execute",
                headers=command_headers,
            )
            assert executed.status_code == 200, executed.text
            assert executed.json()["agent_run_status"] in {
                "agent_completed",
                "agent_failed",
                "agent_suspended",
            }

            tasks = client.get(
                f"{origin}/api/v1/scenarios/{fixture['scenario_id']}"
                "/projection/work-areas-and-tasks?limit=1",
                headers={"Cookie": session_cookie},
            )
            assert tasks.status_code == 200, tasks.text
            proposal_value = _create_deterministic_draft(
                database_url=(
                    "postgresql+psycopg://shiftmind_login:shiftmind_login@"
                    f"localhost:{env['POSTGRES_PORT']}/rosterai"
                ),
                site_id=UUID(session.json()["site_id"]),
                actor_id=UUID(session.json()["app_user_id"]),
                conversation_id=UUID(conversation_id),
                scenario_id=UUID(fixture["scenario_id"]),
                scenario_version_id=UUID(fixture["scenario_version_id"]),
                task_record_id=tasks.json()["items"][0]["record_id"],
            )
            proposal_id = str(proposal_value.proposal_id)
            proposal = client.get(
                f"{origin}/api/v1/proposals/{proposal_id}",
                headers={"Cookie": session_cookie},
            )
            assert proposal.status_code == 200, proposal.text
            started = client.post(
                f"{origin}/api/v1/schedule-runs",
                headers={**command_headers, "Idempotency-Key": "compose-proof-run"},
                json={
                    "proposal_id": proposal_id,
                    "expected_resource_version": proposal.json()["resource_version"],
                },
            )
            assert started.status_code == 200, started.text
            run_id = started.json()["schedule_run_id"]
            deadline = time.monotonic() + 120
            while started.json()["status"] not in TERMINAL:
                if time.monotonic() >= deadline:
                    raise AssertionError(f"worker did not terminate run: {started.text}")
                time.sleep(1)
                started = client.get(
                    f"{origin}/api/v1/schedule-runs/{run_id}",
                    headers={"Cookie": session_cookie},
                )
                assert started.status_code == 200, started.text
        services = _compose(env, "ps", "--status", "running", "--services").stdout
        assert {"api", "worker", "web", "postgres"}.issubset(set(services.splitlines()))
    finally:
        _compose(env, "down", "--volumes", "--remove-orphans")
