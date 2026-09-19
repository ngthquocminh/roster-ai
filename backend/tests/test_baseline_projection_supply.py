"""The actual projection adapter must expose promoted immutable assignments."""
from types import SimpleNamespace
from uuid import uuid4

from adapters.postgres.scenario_projection import PostgresScenarioProjectionReader
from application.contracts.scenario_projection import AssignmentV1
from application.contracts.schedule_version import ScheduleVersionV1
from application.ports.scenario_projection import GroupQueryV1


def configured(monkeypatch, *, foreign=False, foreign_scenario=False, missing=False):
    from adapters.postgres.site_baseline import PostgresSiteBaselineReader
    from adapters.postgres.schedule_run import PostgresScheduleRunRepository
    scenario_id, version_id, site_id, schedule_id = (uuid4() for _ in range(4))
    row = SimpleNamespace(scenario_id=scenario_id, scenario_version_id=version_id, site_id=site_id)
    assignments = (AssignmentV1(record_id='a', worker_id='w', task_id='t', shift_id=None,
                                start_minute=0, end_minute=60),)
    schedule = ScheduleVersionV1(schedule_version_id=schedule_id,
        scenario_id=uuid4() if foreign_scenario else scenario_id,
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
    assert page.items == () and page.total_count == 0


def test_baseline_for_a_different_scenario_id_does_not_leak_assignments(monkeypatch):
    # The pin check compares scenario_id AND scenario_version_id; the foreign
    # fixture above only varies the version, so this varies the other half.
    reader, row, _ = configured(monkeypatch, foreign_scenario=True)
    page = reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
    assert page.items == () and page.total_count == 0


def test_a_dangling_baseline_pointer_reports_no_assignments_instead_of_failing_the_read(monkeypatch):
    # Reviewed behaviour (Story 5.7 core-app review): the read path cannot repair a
    # dangling pointer, and failing the whole projection read with an unhandled 500
    # is worse than reporting no baseline assignments. The "baseline schedule
    # unavailable" ValueError now lives only in the workflow-context loader, which
    # has its own tests.
    reader, row, _ = configured(monkeypatch, missing=True)
    page = reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
    assert page.items == () and page.total_count == 0
    resolved = reader.resolve_assignment(None, row.scenario_id, row.scenario_version_id, 'a')
    assert resolved.item is None


def test_the_baseline_schedule_is_looked_up_within_the_scenarios_own_site(monkeypatch):
    from adapters.postgres.schedule_run import PostgresScheduleRunRepository
    reader, row, _ = configured(monkeypatch)
    seen = {}
    original = PostgresScheduleRunRepository.get_version

    def spy(self, connection, **kwargs):
        seen.update(kwargs)
        return original(self, connection, **kwargs)

    monkeypatch.setattr(PostgresScheduleRunRepository, 'get_version', spy)
    reader.get_baseline_assignments(None, row.scenario_id, GroupQueryV1())
    assert seen['site_id'] == row.site_id


def test_the_overview_reuses_the_baseline_pointer_it_already_read(monkeypatch):
    import json
    from pathlib import Path
    from adapters.postgres.site_baseline import PostgresSiteBaselineReader

    reader, row, assignments = configured(monkeypatch)
    payload = json.loads((Path(__file__).resolve().parents[2] / 'data'
                          / 'sample_tiny_input_more_tm.json').read_text(encoding='utf-8'))
    for name, value in dict(payload=payload, fixture_id='f', scenario_name='n', fixture_version='1',
                            checksum_algorithm='sha256', checksum_schema_version='1',
                            checksum_digest='d').items():
        setattr(row, name, value)
    reads = []
    original = PostgresSiteBaselineReader.get

    def counting(self, *args):
        reads.append(args)
        return original(self, *args)

    monkeypatch.setattr(PostgresSiteBaselineReader, 'get', counting)
    overview = reader.get_overview(None, row.scenario_id)
    # One lookup serves both the version label and the assignment count.
    assert len(reads) == 1
    assert overview.baseline_schedule_version is not None
    assert overview.baseline_assignment_count == len(assignments)
