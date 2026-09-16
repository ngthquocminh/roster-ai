"""The actual projection adapter must expose promoted immutable assignments."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from application.contracts.scenario_projection import AssignmentV1
from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.scenario_projection import GroupQueryV1


def configured(monkeypatch, *, foreign=False, missing=False):
    from adapters.postgres.site_baseline import PostgresSiteBaselineReader
    from adapters.postgres.schedule_run import PostgresScheduleRunRepository
    scenario_id, version_id, site_id, schedule_id = (uuid4() for _ in range(4))
    row = SimpleNamespace(scenario_id=scenario_id, scenario_version_id=version_id, site_id=site_id)
    assignments = (AssignmentV1(record_id='a', worker_id='w', task_id='t', shift_id=None,
                                start_minute=0, end_minute=60),)
    schedule = ScheduleVersionV1(schedule_version_id=schedule_id, scenario_id=scenario_id,
        scenario_version_id=uuid4() if foreign else version_id, assignments=assignments)
    monkeypatch.setattr(PostgresScenarioProjectionReader, '_projection_row', lambda *a: row)
    monkeypatch.setattr(PostgresSiteBaselineReader, 'get', lambda *a: SimpleNamespace(schedule_version_id=schedule_id))
    monkeypatch.setattr(PostgresScheduleRunRepository, 'get_version', lambda *a, **k: None if missing else schedule)
    return PostgresScenarioProjectionReader(), row, assignments


def test_promoted_assignments_are_visible_and_resolvable(monkeypatch):
    reader, row, assignments = configured(monkeypatch)
    page = reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
    assert page.items == assignments and page.total_count == 1
    resolved = reader.resolve_assignment(None, row.scenario_id, row.scenario_version_id, 'a')
    assert resolved.item == assignments[0]


def test_baseline_for_different_scenario_version_does_not_leak_assignments(monkeypatch):
    reader, row, _ = configured(monkeypatch, foreign=True)
    page = reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
    assert page.items == ()


def test_missing_pointed_schedule_fails_instead_of_claiming_empty_baseline(monkeypatch):
    reader, row, _ = configured(monkeypatch, missing=True)
    with pytest.raises(ValueError, match='baseline schedule unavailable'):
        reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
