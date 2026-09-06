from types import SimpleNamespace

from adapters.postgres.schedule_run import PostgresScheduleRunRepository
from adapters.telemetry import JsonLogTelemetrySink
from engine.governed_adapter import GovernedSchedulerAdapter
from worker.main import _load_runtime_factory


def test_production_runtime_factory_loads_through_worker_entry_point(monkeypatch) -> None:
    import worker.composition as composition

    settings = SimpleNamespace(
        database_url="postgresql+psycopg://shiftmind_login:secret@localhost/rosterai"
    )
    monkeypatch.setattr(composition, "default_settings", lambda: settings)

    runtime = _load_runtime_factory("worker.composition:create_runtime")()

    assert runtime.settings is settings
    assert runtime.engine.hide_parameters is True
    assert isinstance(runtime.repository, PostgresScheduleRunRepository)
    assert callable(runtime.scheduler)
    assert isinstance(runtime.scheduler(object()), GovernedSchedulerAdapter)
    assert isinstance(runtime.telemetry, JsonLogTelemetrySink)
    runtime.engine.dispose()
