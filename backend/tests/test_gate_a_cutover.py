"""Gate A maintenance-window orchestration and mutation lockout tests."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from adapters.postgres.fixture_history import FixtureImportResult
from api.main import app
from scripts.gate_a_cutover import FixtureSpec, run_cutover
from services import run_service
from settings import default_settings


class _FakePool:
    def __init__(self) -> None:
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class _CapturingImporter:
    def __init__(self) -> None:
        self.site_id = uuid4()
        self.imports: list[dict] = []

    def ensure_seed_site(self, organization_name: str, site_name: str) -> UUID:
        assert organization_name == "ShiftMind"
        assert site_name == "Seeded Site"
        return self.site_id

    def import_fixture(self, **kwargs) -> FixtureImportResult:
        self.imports.append(kwargs)
        return FixtureImportResult(
            scenario_version_id=uuid4(),
            site_id=kwargs["site_id"],
            fixture_id=kwargs["fixture_id"],
            version=kwargs["version"],
            checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            created=True,
        )


def test_api_refuses_mutating_requests_when_cutover_flag_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flag_path = tmp_path / "gate-a-maintenance"
    flag_path.write_text("maintenance", encoding="utf-8")
    monkeypatch.setenv("ROSTERAI_MAINTENANCE_FLAG", str(flag_path))
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/scenarios", json={})

    assert response.status_code == 503
    assert response.json()["title"] == "Gate A maintenance window"


def test_api_refuses_legacy_reads_when_cutover_flag_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flag_path = tmp_path / "gate-a-maintenance"
    flag_path.write_text("maintenance", encoding="utf-8")
    monkeypatch.setenv("ROSTERAI_MAINTENANCE_FLAG", str(flag_path))
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    monkeypatch.setenv("ROSTERAI_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        scenarios_response = client.get("/scenarios")
        run_response = client.get(f"/runs/{uuid4().hex}")
        health_response = client.get("/health")
        fixtures_response = client.get("/fixtures")

    assert scenarios_response.status_code == 503
    assert scenarios_response.json()["title"] == "Gate A maintenance window"
    assert run_response.status_code == 503
    assert run_response.json()["title"] == "Gate A maintenance window"
    assert health_response.status_code == 200
    assert fixtures_response.status_code == 200


def test_api_treats_directory_at_flag_path_as_maintenance_active(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flag_path = tmp_path / "gate-a-maintenance"
    flag_path.mkdir()
    monkeypatch.setenv("ROSTERAI_MAINTENANCE_FLAG", str(flag_path))
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))

    with TestClient(app) as client:
        response = client.get("/scenarios")

    assert response.status_code == 503


def test_cutover_drains_workers_snapshots_sqlite_and_imports_fixtures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_db = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("CREATE TABLE legacy_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserved')")

    fixture_paths = []
    for name, marker in (("fixture-a.json", "a"), ("fixture-b.json", "b")):
        path = tmp_path / name
        path.write_text(json.dumps({"marker": marker}), encoding="utf-8")
        fixture_paths.append(path)

    maintenance_flag = tmp_path / "maintenance" / "gate-a"
    settings = replace(
        default_settings(),
        db_path=str(legacy_db),
        maintenance_flag_path=str(maintenance_flag),
    )
    fake_pool = _FakePool()
    monkeypatch.setattr(run_service, "_pool", fake_pool)
    importer = _CapturingImporter()

    result = run_cutover(
        settings=settings,
        fixtures=(
            FixtureSpec(fixture_paths[0], "fixture-a", "v1"),
            FixtureSpec(fixture_paths[1], "fixture-b", "v1"),
        ),
        importer=importer,
    )

    assert maintenance_flag.exists()
    assert result.worker_drained is True
    assert fake_pool.shutdown_calls == [(True, True)]
    assert run_service._pool is None
    assert result.snapshot_path.exists()
    assert result.snapshot_path != legacy_db
    with sqlite3.connect(result.snapshot_path) as snapshot:
        assert snapshot.execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserved"
    assert [item["fixture_id"] for item in importer.imports] == [
        "fixture-a",
        "fixture-b",
    ]
    assert [item["payload"] for item in importer.imports] == [
        {"marker": "a"},
        {"marker": "b"},
    ]
    assert len(result.imported_versions) == 2
