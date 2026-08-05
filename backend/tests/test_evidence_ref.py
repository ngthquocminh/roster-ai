from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from application.contracts.evidence_ref import (
    AssignmentResolutionV1,
    ConstraintResolutionV1,
    DemandIntervalResolutionV1,
    EvidenceRefV1,
    LockResolutionV1,
    TaskResolutionV1,
    WorkerResolutionV1,
)
from application.contracts.scenario_projection import TaskV1
from adapters.postgres.scenario_projection import (
    PostgresScenarioProjectionReader,
    _horizon,
    _normalize_constraints,
    _normalize_demand,
    _normalize_tasks,
    _normalize_workers,
)
from application.ports.scenario_projection import ScenarioProjectionReader


REPO_ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, row) -> None:
        self.row = row

    def one_or_none(self):
        return self.row


class _Connection:
    def __init__(self, row) -> None:
        self.row = row

    def execute(self, _statement):
        return _Result(self.row)


def test_evidence_ref_v1_has_the_normative_frozen_transport_free_shape() -> None:
    reference = EvidenceRefV1(
        scenario_version_id=uuid4(),
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        producing_run_version=None,
        baseline_schedule_version=None,
        group="work-areas-and-tasks",
        record_id="task-1",
        field="name",
        start_minute=0,
        end_minute=30,
    )

    assert [field.name for field in fields(reference)] == [
        "scenario_version_id",
        "checksum_algorithm",
        "checksum_schema_version",
        "checksum_digest",
        "producing_run_version",
        "baseline_schedule_version",
        "group",
        "record_id",
        "field",
        "start_minute",
        "end_minute",
    ]
    assert reference.producing_run_version is None
    assert reference.baseline_schedule_version is None
    with pytest.raises(FrozenInstanceError):
        reference.record_id = "changed"  # type: ignore[misc]

    module = __import__(EvidenceRefV1.__module__, fromlist=["*"])
    source_names = set(vars(module))
    assert "fastapi" not in source_names
    assert "pydantic" not in source_names
    assert "sqlalchemy" not in source_names


def test_resolution_contracts_are_group_specific_and_share_outcomes() -> None:
    scenario_id = uuid4()
    scenario_version_id = uuid4()
    task = TaskV1("task-1", "task-1", "Pick", "Pick", "a", "A", None)

    resolved = TaskResolutionV1(
        outcome="resolved",
        scenario_id=scenario_id,
        current_scenario_version_id=scenario_version_id,
        item=task,
    )
    assert resolved.item is task
    assert resolved.current_scenario_version_id == scenario_version_id

    resolution_types = (
        TaskResolutionV1,
        WorkerResolutionV1,
        DemandIntervalResolutionV1,
        AssignmentResolutionV1,
        LockResolutionV1,
        ConstraintResolutionV1,
    )
    for resolution_type in resolution_types:
        outcome = resolution_type(
            outcome="not_found",
            scenario_id=scenario_id,
            current_scenario_version_id=scenario_version_id,
            item=None,
        )
        assert outcome.outcome == "not_found"
        assert outcome.item is None
        with pytest.raises(FrozenInstanceError):
            outcome.outcome = "resolved"  # type: ignore[misc]


def test_projection_reader_port_exposes_all_exact_target_resolvers() -> None:
    assert {
        "resolve_task",
        "resolve_worker",
        "resolve_demand_interval",
        "resolve_assignment",
        "resolve_lock",
        "resolve_constraint",
    } <= set(vars(ScenarioProjectionReader))


def test_adapter_resolves_deep_demand_without_paging_or_retargeting() -> None:
    payload = json.loads(
        (REPO_ROOT / "data" / "sample_tiny_input_more_tm.json").read_text(
            encoding="utf-8"
        )
    )
    scenario_id = uuid4()
    version_id = uuid4()
    row = SimpleNamespace(
        scenario_id=scenario_id,
        scenario_version_id=version_id,
        site_id=uuid4(),
        payload=payload,
    )
    reader = PostgresScenarioProjectionReader()
    connection = _Connection(row)
    horizon_start, _ = _horizon(payload)
    demand = _normalize_demand(payload, horizon_start)
    target = demand[1_500]
    page = reader.get_demand(connection, scenario_id, cursor=1_500, limit=50)
    assert page is not None
    assert page.items[0] == target

    resolution = reader.resolve_demand_interval(
        connection, scenario_id, version_id, target.record_id
    )

    assert resolution is not None
    assert resolution.outcome == "resolved"
    assert resolution.item == target
    assert resolution.current_scenario_version_id == version_id

    mismatch = reader.resolve_demand_interval(
        connection, scenario_id, uuid4(), target.record_id
    )
    assert mismatch is not None
    assert mismatch.outcome == "version_mismatch"
    assert mismatch.item is None

    missing = reader.resolve_demand_interval(
        connection, scenario_id, version_id, "missing"
    )
    assert missing is not None
    assert missing.outcome == "not_found"
    assert missing.item is None


def test_adapter_resolves_each_normalized_group_and_keeps_empty_groups_empty() -> None:
    payload = json.loads(
        (REPO_ROOT / "data" / "sample_tiny_input_more_tm.json").read_text(
            encoding="utf-8"
        )
    )
    scenario_id = uuid4()
    version_id = uuid4()
    connection = _Connection(
        SimpleNamespace(
            scenario_id=scenario_id,
            scenario_version_id=version_id,
            payload=payload,
        )
    )
    reader = PostgresScenarioProjectionReader()
    horizon_start, _ = _horizon(payload)
    cases = (
        (reader.resolve_task, _normalize_tasks(payload)[0]),
        (reader.resolve_worker, _normalize_workers(payload, horizon_start)[0]),
        (reader.resolve_demand_interval, _normalize_demand(payload, horizon_start)[0]),
        (reader.resolve_constraint, _normalize_constraints(payload)[0]),
    )

    for resolver, target in cases:
        resolution = resolver(
            connection, scenario_id, version_id, target.record_id
        )
        assert resolution is not None
        assert resolution.outcome == "resolved"
        assert resolution.item == target

    for resolver in (reader.resolve_assignment, reader.resolve_lock):
        resolution = resolver(connection, scenario_id, version_id, "anything")
        assert resolution is not None
        assert resolution.outcome == "not_found"
        assert resolution.item is None


def test_adapter_returns_none_when_the_site_scoped_scenario_is_unavailable() -> None:
    reader = PostgresScenarioProjectionReader()
    assert reader.resolve_task(_Connection(None), uuid4(), uuid4(), "task-1") is None


def test_version_mismatch_returns_before_normalizing_the_payload() -> None:
    scenario_id = uuid4()
    current_version_id = uuid4()
    reader = PostgresScenarioProjectionReader()
    connection = _Connection(
        SimpleNamespace(
            scenario_id=scenario_id,
            scenario_version_id=current_version_id,
            payload={},
        )
    )

    resolution = reader.resolve_demand_interval(
        connection, scenario_id, uuid4(), "outbound:0"
    )

    assert resolution is not None
    assert resolution.outcome == "version_mismatch"
    assert resolution.item is None
