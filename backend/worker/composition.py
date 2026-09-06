"""Production composition for the durable schedule-run worker."""
from __future__ import annotations

from sqlalchemy import create_engine

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.postgres.solver_input import PostgresSolverInputSource
from adapters.telemetry import JsonLogTelemetrySink
from engine.governed_adapter import GovernedSchedulerAdapter
from settings import default_settings
from worker.main import WorkerRuntimeV1


def create_runtime() -> WorkerRuntimeV1:
    """Build one worker runtime using only the restricted application DSN."""
    settings = default_settings()
    engine = create_engine(settings.database_url, hide_parameters=True)
    return WorkerRuntimeV1(
        engine=engine,
        repository=PostgresScheduleRunRepository(),
        scheduler=lambda connection: GovernedSchedulerAdapter(
            PostgresSolverInputSource(connection)
        ),
        settings=settings,
        telemetry=JsonLogTelemetrySink(),
    )


__all__ = ["create_runtime"]
