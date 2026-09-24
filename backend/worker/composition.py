"""Production composition for the durable schedule-run worker."""
from __future__ import annotations

from sqlalchemy import create_engine

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.solver_input import PostgresSolverInputSource
from adapters.telemetry import JsonLogTelemetrySink
from adapters.telemetry.spans import build_process_tracing, trace_engine, traced_scheduler
from engine.governed_adapter import GovernedSchedulerAdapter
from settings import default_settings
from worker.main import WorkerRuntimeV1


def create_runtime() -> WorkerRuntimeV1:
    """Build one worker runtime using only the restricted application DSN."""
    settings = default_settings()
    # `None` keyless: nothing is constructed and every helper below returns its
    # input unchanged (Story 5.9, AC1).
    tracing = build_process_tracing(settings, service_name="shiftmind-worker")
    engine = trace_engine(
        create_engine(settings.database_url, hide_parameters=True), tracing
    )
    return WorkerRuntimeV1(
        engine=engine,
        repository=PostgresScheduleRunRepository(),
        scheduler=traced_scheduler(
            lambda connection: GovernedSchedulerAdapter(
                PostgresSolverInputSource(connection)
            ),
            tracing,
        ),
        settings=settings,
        telemetry=JsonLogTelemetrySink(),
        tracing=tracing,
    )


__all__ = ["create_runtime"]
