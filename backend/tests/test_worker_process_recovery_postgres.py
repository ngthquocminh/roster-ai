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
from adapters.postgres.schema import (
    job_queue,
    persisted_event,
    schedule_run,
    schedule_version,
)
from tests.fixtures.worker_process import successful_empty_outcome
from tests.test_cancellation_race_postgres import _seed_valid_snapshot
from tests.test_job_leasing_postgres import _only_leasable, _queue_jobs, lease_ids
from worker.lease_worker import run_once
from worker.main import DEFAULT_POLL_INTERVAL_SECONDS


pytestmark = pytest.mark.postgres


#: Poll granularity of `_wait_until`. It bounds the precision of every NFR35
#: figure, so it is recorded in the evidence rather than left implicit.
WAIT_RESOLUTION_SECONDS = 0.005


def _drain(process: subprocess.Popen) -> str:
    """Collect a dead child's output without risking a full-pipe deadlock."""
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        return "<worker output unavailable>"
    return f"stdout:\n{stdout or ''}\nstderr:\n{stderr or ''}"


def _wait_until(
    predicate,
    *,
    timeout_seconds: float = 15.0,
    process: subprocess.Popen | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        if process is not None and process.poll() is not None:
            # A worker that died at start-up (bad URL, import error) would
            # otherwise burn the whole timeout and report nothing useful, with
            # the child's traceback still sitting unread in its pipe.
            raise AssertionError(
                "worker subprocess exited before reaching the expected state "
                f"(returncode {process.returncode})\n{_drain(process)}"
            )
        time.sleep(WAIT_RESOLUTION_SECONDS)
    raise AssertionError(
        f"worker subprocess did not reach the expected state within {timeout_seconds}s"
    )


def _spawn_worker(
    governed_postgres_engine,
    *,
    lease_owner: str,
    sleep_seconds: str,
    poll_interval_seconds: float,
) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        SHIFTMIND_WORKER_TEST_DATABASE_URL=(
            governed_postgres_engine.url.render_as_string(hide_password=False)
        ),
        SHIFTMIND_WORKER_TEST_SLEEP_SECONDS=sleep_seconds,
    )
    worker_path = Path(__file__).resolve().parents[1] / "worker" / "main.py"
    return subprocess.Popen(
        [
            sys.executable,
            str(worker_path),
            "--runtime-factory",
            "tests.fixtures.worker_process:create_runtime",
            "--lease-owner",
            lease_owner,
            "--poll-interval-seconds",
            str(poll_interval_seconds),
        ],
        cwd=worker_path.parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _terminate(process: subprocess.Popen) -> None:
    """Tear the worker down without masking the assertion that brought us here."""
    try:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def _candidate_count(engine, run_id) -> int:
    with engine.connect() as connection:
        return connection.scalar(
            select(func.count())
            .select_from(schedule_version)
            .where(schedule_version.c.schedule_run_id == run_id)
        )


def _running_event_count(engine, run_id) -> int:
    with engine.connect() as connection:
        return connection.scalar(
            select(func.count())
            .select_from(persisted_event)
            .where(
                persisted_event.c.stream_id == run_id,
                persisted_event.c.event_type == "run.running.v1",
            )
        )


def test_hard_killed_worker_is_reclaimed_and_commits_one_candidate(
    governed_postgres_engine, lease_ids
) -> None:
    job_id, run_id = _queue_jobs(governed_postgres_engine, lease_ids, 1)[0]
    _only_leasable(governed_postgres_engine, job_id)
    _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)

    process = _spawn_worker(
        governed_postgres_engine,
        lease_owner="story-3.11-killed-worker",
        # Long enough that the kill lands mid-solve, after `solver_running` has
        # been committed by Transaction A and before any effect is written.
        sleep_seconds="300",
        poll_interval_seconds=0.05,
    )
    try:
        def leased_and_running() -> bool:
            with governed_postgres_engine.connect() as connection:
                leased = connection.execute(
                    select(job_queue.c.status, job_queue.c.fencing_epoch)
                    .where(job_queue.c.id == job_id)
                ).one() == ("leased", 1)
                # Gating on the lease alone would let the kill land BEFORE any
                # state change, proving only "killed right after leasing". The
                # run row reaching `solver_running` is what makes this a
                # mid-work kill, which is what the helper name promises.
                running = connection.scalar(
                    select(schedule_run.c.status).where(schedule_run.c.id == run_id)
                ) == "solver_running"
                return leased and running

        _wait_until(leased_and_running, process=process)
        killed_epoch_events = _running_event_count(governed_postgres_engine, run_id)
        assert killed_epoch_events == 1

        process.kill()  # SIGKILL on POSIX; hard TerminateProcess on Windows.
        process.wait(timeout=10)
        assert process.returncode != 0

        # The killed epoch committed `solver_running` but NO effect. Asserting
        # this before recovery is what makes the post-recovery count of exactly
        # one a real duplicate-effect check rather than arithmetic on zero.
        assert _candidate_count(governed_postgres_engine, run_id) == 0

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
            events = connection.execute(
                select(persisted_event.c.event_type, persisted_event.c.sequence)
                .where(persisted_event.c.stream_id == run_id)
                .order_by(persisted_event.c.sequence)
            ).all()

        # Fencing epoch advanced, so the recovery really was a new lease.
        assert job == ("completed", 2)
        assert len(candidates) == 1
        assert candidates[0].schedule_run_id == run_id
        # Lineage: the `run.running.v1` the KILLED epoch wrote is still on the
        # original stream, and the recovery epoch appended to that same stream
        # rather than starting a new one. `stream_id == schedule_run_id` alone
        # is enforced by a CHECK constraint and proves nothing.
        assert [event_type for event_type, _sequence in events][0] == "run.running.v1"
        assert len(events) > killed_epoch_events
        sequences = [sequence for _event_type, sequence in events]
        assert sequences == sorted(sequences)
    finally:
        _terminate(process)


def test_nfr35_live_worker_reaches_running_within_five_seconds(
    governed_postgres_engine, lease_ids
) -> None:
    """Measure the queue and real process path that Story 3.5 could not.

    Measured at the SHIPPED default poll interval, not a tuned-down one: an
    evidence figure produced at 0.01s says nothing about what an operator
    running this worker would actually wait. The first run is reported as the
    cold-start run rather than discarded, so the evidence's "includes worker
    start-up" claim is literally true.
    """
    jobs = _queue_jobs(governed_postgres_engine, lease_ids, 4)
    for _job_id, run_id in jobs:
        _seed_valid_snapshot(governed_postgres_engine, lease_ids, run_id)
    with governed_postgres_engine.begin() as connection:
        connection.execute(
            update(job_queue)
            .where(job_queue.c.id.in_([job_id for job_id, _run_id in jobs]))
            .values(status="completed")
        )

    process = _spawn_worker(
        governed_postgres_engine,
        lease_owner="story-3.11-nfr35-worker",
        sleep_seconds="0.01",
        poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
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
                return bool(_running_event_count(governed_postgres_engine, run_id))

            # Generously above the 5000 ms budget on purpose: if the wait
            # deadline were the budget, the assertion below could never fail and
            # a real NFR35 breach would surface as a generic wait error naming
            # neither the gate nor the threshold.
            _wait_until(
                running_event_exists, timeout_seconds=30.0, process=process
            )
            measurements.append(
                {
                    "run": index + 1,
                    "event": "run.running.v1",
                    "duration_ms": round(
                        (time.perf_counter() - acknowledged_at) * 1_000, 3
                    ),
                    "cold_start": index == 0,
                    "poll_interval_seconds": DEFAULT_POLL_INTERVAL_SECONDS,
                    "poll_resolution_ms": WAIT_RESOLUTION_SECONDS * 1_000,
                }
            )
    finally:
        _terminate(process)

    assert len(measurements) == 4
    assert measurements[0]["cold_start"] is True
    assert all(item["duration_ms"] <= 5_000 for item in measurements)
    print("NFR35_LIVE_WORKER_MEASUREMENTS=" + json.dumps(measurements))
