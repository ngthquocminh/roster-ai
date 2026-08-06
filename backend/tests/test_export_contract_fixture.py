"""Contract snapshot generation for the two Gate A fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_contract_fixture import (
    CONTRACT_DIRECTORY,
    build_contract_fixture,
    export_contract_fixtures,
)
from scripts.gate_a_cutover import default_fixtures


@pytest.mark.parametrize("fixture", default_fixtures(), ids=lambda item: item.fixture_id)
def test_contract_fixture_uses_existing_normalizers_and_all_projection_groups(
    fixture,
) -> None:
    payload = json.loads(fixture.path.read_text(encoding="utf-8"))

    contract = build_contract_fixture(fixture, payload)

    assert contract["contract_version"] == "ScenarioProjectionV1"
    assert contract["fixture"] == {
        "fixture_id": fixture.fixture_id,
        "version": fixture.version,
        "source_path": f"data/{fixture.path.name}",
    }
    assert tuple(contract["groups"]) == (
        "work-areas-and-tasks",
        "workers",
        "demand",
        "baseline-assignments",
        "locks",
        "constraints-and-objectives",
    )
    assert contract["groups"]["baseline-assignments"] == []
    assert contract["groups"]["locks"] == []
    assert contract["overview"]["baseline_assignment_count"] == 0
    assert contract["overview"]["lock_count"] == 0


def test_committed_contract_fixtures_are_current_and_deterministic(tmp_path: Path) -> None:
    first = export_contract_fixtures(tmp_path)
    second = export_contract_fixtures(tmp_path)

    assert [path.name for path in first] == [
        "sample_tiny_input.projection-v1.json",
        "sample_tiny_input_more_tm.projection-v1.json",
    ]
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    for generated in first:
        committed = CONTRACT_DIRECTORY / generated.name
        assert committed.read_bytes() == generated.read_bytes()
