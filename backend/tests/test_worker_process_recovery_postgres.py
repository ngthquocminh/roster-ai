from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select, text, update

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.schema import job_queue, persisted_event, schedule_version
from tests.fixtures.worker_process import successful_empty_outcome
from tests.test_cancellation_race_postgres import _seed_valid_snapshot
from tests.test_job_leasing_postgres import _only_leasable, _queue_jobs, lease_ids
from worker.lease_worker import run_once


pytestmark = pytest.mark.postgres


def _wait_until(predicate, *, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("worker subprocess did not reach the expected state")


def test_hard_killed_worker_is_reclaimed_and_commits_one_candidate(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)

    env = dict(os.environ)
    env.update(
        SHIFTMIND_WORKER_TEST_DATABASE_URL=(
            governed_postgres_engine.url.render_as_string(hide_password=False)
        ),
        SHIFTMIND_WORKER_TEST_SLEEP_SECONDS="300",
    )
    worker_path = Path(__file__).resolve().parents[1] / "worker" / "main.py"
    process = subprocess.Popen(
        [
            sys.executable,
            str(worker_path),
            "--runtime-factory",
            "tests.fixtures.worker_process:create_runtime",
            "--lease-owner",
            "story-3.11-killed-worker",
            "--poll-interval-seconds",
            "0.05",
        ],
        cwd=worker_path.parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        def leased_and_running() -> bool:
            with governed_postgres_engine.connect() as connection:
                return connection.execute(
                    select(job_queue.c.status, job_queue.c.fencing_epoch)
                    .where(job_queue.c.id == job_id)
                ).one() == ("leased", 1)

        _wait_until(leased_and_running)
        process.kill()  # SIGKILL on POSIX; hard TerminateProcess on Windows.
        process.wait(timeout=10)
        assert process.returncode != 0

        with governed_postgres_engine.begin() as connection:
            connection.execute(
                update(job_queue)
                .where(job_queue.c.id == job_id)
                .values(lease_expires_at=text("pg_catalog.now() - interval '1 second'"))
            )

        recovered = run_once(
            governed_postgres_engine,
            PostgresScheduleRunRepository(),
            type("Scheduler", (), {"solve": lambda self, snapshot: successful_empty_outcome()})(),
            lease_owner="story-3.11-recovery-worker",
            lease_seconds=60,
        )
        assert recovered is not None

        with governed_postgres_engine.connect() as connection:
            job = connection.execute(
                select(job_queue.c.status, job_queue.c.fencing_epoch)
                .where(job_queue.c.id == job_id)
            ).one()
            candidates = connection.execute(
                select(schedule_version.c.id, schedule_version.c.schedule_run_id)
                .where(schedule_version.c.schedule_run_id == run_id)
            ).all()
            event_run_ids = connection.execute(
                select(persisted_event.c.schedule_run_id)
                .where(persisted_event.c.stream_id == run_id)
            ).scalars().all()

        assert job == ("completed", 2)
        assert len(candidates) == 1
        assert candidates[0].schedule_run_id == run_id
        assert event_run_ids and set(event_run_ids) == {run_id}
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_nfr35_live_worker_reaches_running_within_five_seconds(
    governed_postgres_engine, lease_ids
) -> None:
    """Measure the queue and real process path that Story 3.5 could not."""
    jobs = _queue_jobs(governed_postgres_engine, lease_ids, 4)
    for _job_id, run_id in jobs:
        _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id.in_([job_id for job_id, _run_id in jobs]))
            .values(status="completed")
        )

    env = dict(os.environ)
    env.update(
        SHIFTMIND_WORKER_TEST_DATABASE_URL=(
            governed_postgres_engine.url.render_as_string(hide_password=False)
        ),
        SHIFTMIND_WORKER_TEST_SLEEP_SECONDS="0.01",
    )
    worker_path = Path(__file__).resolve().parents[1] / "worker" / "main.py"
    process = subprocess.Popen(
        [
            sys.executable,
            str(worker_path),
            "--runtime-factory",
            "tests.fixtures.worker_process:create_runtime",
            "--lease-owner",
            "story-3.11-nfr35-worker",
            "--poll-interval-seconds",
            "0.01",
        ],
        cwd=worker_path.parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    measurements = []
    try:
        for index, (job_id, run_id) in enumerate(jobs):
            with governed_postgres_engine.begin() as connection:
                connection.execute(
                    update(job_queue)
                    .where(job_queue.c.id == job_id)
                    .values(status="queued")
                )
            acknowledged_at = time.perf_counter()

            def running_event_exists() -> bool:
                with governed_postgres_engine.connect() as connection:
                    return bool(
                        connection.scalar(
                            select(func.count())
                            .select_from(persisted_event)
                            .where(
                                persisted_event.c.stream_id == run_id,
                                persisted_event.c.event_type == "run.running.v1",
                            )
                        )
                    )

            _wait_until(running_event_exists, timeout_seconds=5.0)
            duration_ms = round(
                (time.perf_counter() - acknowledged_at) * 1_000, 3
            )
            if index:
                measurements.append(
                    {
                        "run": index,
                        "event": "run.running.v1",
                        "duration_ms": duration_ms,
                    }
                )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)

    assert len(measurements) == 3
    assert all(item["duration_ms"] <= 5_000 for item in measurements)
    print("NFR35_LIVE_WORKER_MEASUREMENTS=" + json.dumps(measurements))
