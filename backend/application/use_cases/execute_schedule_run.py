"""Execute one already-running governed run and preserve every terminal outcome."""
from __future__ import annotations

import threading
from typing import Any, Callable, ContextManager
from uuid import UUID

from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import SolverOutcomeV1
from application.ports.scheduler import SchedulerPort
from application.ports.schedule_run import ScheduleRunRepository
from application.use_cases.finalize_schedule_run import (
    FinalizedScheduleRunV1,
    finalize_schedule_run,
)
from datetime import datetime, timezone
from application.app_version import APP_VERSION
from application.contracts.telemetry import CorrelationV1, TelemetryRecordV1
from application.ports.telemetry import TelemetrySink


#: Bounded so a heartbeat blocked on an exhausted connection pool cannot stall
#: the worker after the solve has already produced a result. The thread is a
#: daemon, so one abandoned here cannot keep the process alive.
_HEARTBEAT_JOIN_TIMEOUT_S = 5.0


class _FencedFinalizationRepository:
    """Inject the lease epoch without widening the frozen finalizer use case."""

    def __init__(
        self,
        repository: ScheduleRunRepository,
        fencing_epoch: int,
        request_id: UUID | None = None,
    ) -> None:
        self._repository = repository
        self._fencing_epoch = fencing_epoch
        self._request_id = request_id

    def finalize_run(self, connection: Any, **values) -> None:
        # `request_id` rides the same seam as `fencing_epoch`: the worker knows
        # the attempt that produced this outcome, and `finalize_schedule_run`
        # stays frozen rather than growing a parameter for it.
        self._repository.finalize_run(
            connection,
            fencing_epoch=self._fencing_epoch,
            request_id=self._request_id,
            **values,
        )


class HeartbeatObservationsV1:
    """What the heartbeat thread saw while the solve was in flight.

    The thread cannot interrupt `scheduler.solve`, so everything it learns is
    recorded here rather than raised. Reads happen after `join()`, but the
    lock keeps a mid-solve inspection well-defined.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.lost_lease = False
        self.cancellation_requested = False
        self.error: BaseException | None = None

    def record_lost_lease(self) -> None:
        with self._lock:
            self.lost_lease = True

    def record_cancellation(self) -> None:
        with self._lock:
            self.cancellation_requested = True

    def record_error(self, exc: BaseException) -> None:
        with self._lock:
            # Keep the first failure: later ticks are usually the same cause
            # repeating, and the first one is closest to the trigger.
            if self.error is None:
                self.error = exc


def execute_schedule_run(
    repository: ScheduleRunRepository,
    scheduler: SchedulerPort,
    connection: Any,
    *,
    snapshot: RunSnapshotV1,
    site_id: UUID,
    fencing_epoch: int,
    job_id: UUID | None = None,
    lease_seconds: int | None = None,
    runtime_connection_factory: Callable[[UUID], ContextManager[Any]] | None = None,
    observations: HeartbeatObservationsV1 | None = None,
    request_id: UUID | None = None,
    telemetry: TelemetrySink | None = None,
) -> FinalizedScheduleRunV1:
    assert snapshot.schedule_run_id is not None
    # All three arguments drive one feature. Accepting a partial set would
    # silently disable lease renewal for a long solve -- the failure this
    # heartbeat exists to prevent -- so refuse instead of degrading quietly.
    heartbeat_arguments = (job_id, lease_seconds, runtime_connection_factory)
    if any(argument is not None for argument in heartbeat_arguments) and not all(
        argument is not None for argument in heartbeat_arguments
    ):
        raise ValueError(
            "job_id, lease_seconds and runtime_connection_factory must be supplied "
            "together to renew the lease, or all omitted to run without renewal"
        )
    # `workflow.renew_job_lease` raises SQLSTATE 22023 on a non-positive
    # extension. Reject it here, where the caller can still be identified.
    if lease_seconds is not None and lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive to renew a lease")

    monitor = observations if observations is not None else HeartbeatObservationsV1()
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    if (
        job_id is not None
        and lease_seconds is not None
        and runtime_connection_factory is not None
    ):
        interval_seconds = max(1, lease_seconds // 3)

        def _heartbeat() -> None:
            while not heartbeat_stop.wait(interval_seconds):
                try:
                    with runtime_connection_factory(site_id) as heartbeat_connection:
                        renewal = repository.renew_job_lease(
                            heartbeat_connection,
                            job_id=job_id,
                            fencing_epoch=fencing_epoch,
                            extension_seconds=lease_seconds,
                        )
                except Exception as exc:  # noqa: BLE001
                    # Dying here would leave the solve running on a lease
                    # nobody extends, and `lease_next_job` would hand the same
                    # job to a second worker once it expired. A dropped
                    # connection or a saturated pool is the common case and is
                    # transient, so record it and try again on the next tick.
                    monitor.record_error(exc)
                    continue
                if renewal.cancellation_requested:
                    # The SQL function returns this so a leased-but-cancelled
                    # job can surface to the worker. Renewal deliberately
                    # continues: dropping the lease now would let a second
                    # worker start duplicate work while this solve is still in
                    # flight. Preempting the in-flight solve needs a
                    # solver-level cancellation hook (deferred-work).
                    monitor.record_cancellation()
                if not renewal.renewed:
                    # The row was re-leased under a newer fencing epoch. The
                    # fence is already lost and `_claim_epoch` will reject this
                    # attempt's finalize, so stop renewing.
                    monitor.record_lost_lease()
                    return

        heartbeat_thread = threading.Thread(
            target=_heartbeat,
            name=f"schedule-run-heartbeat-{snapshot.schedule_run_id}",
            daemon=True,
        )
        heartbeat_thread.start()
    try:
        outcome = scheduler.solve(snapshot)
    except Exception as exc:
        outcome = SolverOutcomeV1(
            solver_status="UNKNOWN",
            reason=getattr(exc, "code", "solver_adapter_failed"),
        )
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=_HEARTBEAT_JOIN_TIMEOUT_S)
    finalized = finalize_schedule_run(
        _FencedFinalizationRepository(repository, fencing_epoch, request_id),
        connection,
        snapshot=snapshot,
        outcome=outcome,
        site_id=site_id,
    )
    if telemetry is not None:
        try:
            telemetry.emit(
                TelemetryRecordV1(
                    event="solver.run.completed",
                    occurred_at=datetime.now(timezone.utc),
                    app_version=APP_VERSION,
                    correlation=CorrelationV1(
                        request_id=request_id,
                        site_id=site_id,
                        schedule_run_id=snapshot.schedule_run_id,
                        schedule_version_id=(
                            finalized.candidate.schedule_version_id
                            if finalized.candidate is not None
                            else None
                        ),
                    ),
                    labels={"solver_status": outcome.solver_status},
                    duration_ms=outcome.wall_time_seconds * 1_000,
                )
            )
        except Exception:  # noqa: BLE001 - finalized result wins
            pass
    return finalized


__all__ = ["HeartbeatObservationsV1", "execute_schedule_run"]
