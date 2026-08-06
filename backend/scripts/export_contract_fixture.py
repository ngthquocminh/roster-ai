"""Export the deterministic Gate A projection contract fixtures.

Regenerate from the repository root with:
    uv run --directory backend python scripts/export_contract_fixture.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from adapters.postgres.scenario_projection import (
    SITE_TIMEZONE,
    _horizon,
    _normalize_constraints,
    _normalize_demand,
    _normalize_tasks,
    _normalize_workers,
    _rows,
)
from scripts.gate_a_cutover import FixtureSpec, REPO_ROOT, default_fixtures


CONTRACT_DIRECTORY = REPO_ROOT / "data" / "contract"


def _records(items: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def build_contract_fixture(
    fixture: FixtureSpec,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Normalize one governed source with the production projection functions."""
    horizon_start, horizon_minutes = _horizon(payload)
    tasks = _normalize_tasks(payload)
    workers = _normalize_workers(payload, horizon_start)
    demand = _normalize_demand(payload, horizon_start)
    constraints = _normalize_constraints(payload)
    work_areas = {
        area.get("AreaID")
        for area in _rows(payload, "Area")
        if area.get("AreaID")
    }
    return {
        "contract_version": "ScenarioProjectionV1",
        "fixture": {
            "fixture_id": fixture.fixture_id,
            "version": fixture.version,
            "source_path": f"data/{fixture.path.name}",
        },
        "overview": {
            "horizon_start": horizon_start.isoformat().replace("+00:00", "Z"),
            "site_timezone": SITE_TIMEZONE,
            "horizon_minutes": horizon_minutes,
            "baseline_schedule_version": None,
            "work_area_count": len(work_areas),
            "task_count": len(tasks),
            "worker_count": len(workers),
            "demand_interval_count": len(demand),
            "baseline_assignment_count": 0,
            "lock_count": 0,
            "constraint_count": len(constraints),
        },
        "groups": {
            "work-areas-and-tasks": _records(tasks),
            "workers": _records(workers),
            "demand": _records(demand),
            "baseline-assignments": [],
            "locks": [],
            "constraints-and-objectives": _records(constraints),
        },
    }


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def export_contract_fixtures(
    output_directory: Path = CONTRACT_DIRECTORY,
) -> tuple[Path, ...]:
    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fixture in default_fixtures():
        payload = json.loads(fixture.path.read_text(encoding="utf-8"))
        contract = build_contract_fixture(fixture, payload)
        output_path = output_directory / f"{fixture.fixture_id}.projection-v1.json"
        output_path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        written.append(output_path)
    return tuple(written)


def main() -> None:
    for path in export_contract_fixtures():
        print(path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
