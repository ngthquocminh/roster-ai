"""One-shot Gate A cutover from legacy SQLite to governed fixture history.

Operational contract (offline maintenance window):
    1. Disable supervisor auto-restart, or scale the API service to zero.
    2. Stop the running `uvicorn api.main:app` process and wait for it to fully
       exit — process termination is the authoritative worker-drain boundary,
       not this script.
    3. Run this script (`python backend/scripts/gate_a_cutover.py`). It writes
       the persistent maintenance flag before snapshotting SQLite and
       importing fixtures.
    4. Restart the application only after validating the import.

`_drain_worker_pool()` below only observes `run_service._pool` within this
script's own process — it is a defensive check for same-process/test
invocations, not a substitute for step 2 above. There is no in-process admin
trigger for this script (no authenticated admin model exists yet); the live
server must already be stopped before this runs.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import UUID

from adapters.postgres.fixture_history import (
    FixtureImportResult,
    PostgresFixtureHistoryAdapter,
)
from services import run_service
from settings import Settings, default_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


@dataclass(frozen=True)
class FixtureSpec:
    path: Path
    fixture_id: str
    version: str


@dataclass(frozen=True)
class CutoverResult:
    maintenance_flag_path: Path
    snapshot_path: Path
    worker_drained: bool
    site_id: UUID
    imported_versions: tuple[FixtureImportResult, ...]


class FixtureImporter(Protocol):
    def ensure_seed_site(
        self,
        organization_name: str,
        site_name: str,
    ) -> UUID: ...

    def import_fixture(
        self,
        *,
        site_id: UUID,
        fixture_id: str,
        version: str,
        payload: Any,
        source_package: str,
        source_path: str,
    ) -> FixtureImportResult: ...


def default_fixtures() -> tuple[FixtureSpec, ...]:
    """Return the two predefined fixtures governed by Story 1.1."""
    return (
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input.json",
            "sample_tiny_input",
            "v1",
        ),
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input_more_tm.json",
            "sample_tiny_input_more_tm",
            "v1",
        ),
    )


def _enable_maintenance(flag_path: Path) -> None:
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    flag_path.write_text(
        datetime.now(timezone.utc).isoformat(),
        encoding="utf-8",
    )


def _drain_worker_pool() -> bool:
    """Cancel queued solves and wait for any running solve before snapshotting.

    Defensive, same-process check only (see module docstring) — the real
    server, running in a separate OS process, must already be stopped by the
    operator per the operational contract above.
    """
    with run_service._pool_lock:
        pool = run_service._pool
        run_service._pool = None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)
    return run_service._pool is None


def _snapshot_sqlite(db_path: Path) -> Path:
    if not db_path.is_file():
        raise FileNotFoundError(f"Legacy SQLite database does not exist: {db_path}")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_path = db_path.with_name(
        f"{db_path.stem}.pre-gate-a-{timestamp}{db_path.suffix}"
    )
    with sqlite3.connect(db_path) as source, sqlite3.connect(snapshot_path) as target:
        source.backup(target)
    return snapshot_path


def run_cutover(
    *,
    settings: Settings | None = None,
    fixtures: Sequence[FixtureSpec] | None = None,
    importer: FixtureImporter | None = None,
) -> CutoverResult:
    """Disable legacy writes, drain work, snapshot SQLite, and import fixtures."""
    resolved_settings = settings or default_settings()
    resolved_fixtures = tuple(fixtures or default_fixtures())
    resolved_importer = importer or PostgresFixtureHistoryAdapter(
        resolved_settings.provisioning_database_url
    )
    flag_path = Path(resolved_settings.maintenance_flag_path).resolve()

    _enable_maintenance(flag_path)
    worker_drained = _drain_worker_pool()
    if not worker_drained:
        raise RuntimeError("Legacy worker pool did not drain")
    snapshot_path = _snapshot_sqlite(Path(resolved_settings.db_path).resolve())

    site_id = resolved_importer.ensure_seed_site("ShiftMind", "Seeded Site")
    imported_versions = []
    for fixture in resolved_fixtures:
        with fixture.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        resolved_fixture_path = fixture.path.resolve()
        try:
            source_path = str(resolved_fixture_path.relative_to(REPO_ROOT))
        except ValueError:
            source_path = resolved_fixture_path.name
        imported_versions.append(
            resolved_importer.import_fixture(
                site_id=site_id,
                fixture_id=fixture.fixture_id,
                version=fixture.version,
                payload=payload,
                source_package="predefined-fixtures",
                source_path=source_path,
            )
        )

    return CutoverResult(
        maintenance_flag_path=flag_path,
        snapshot_path=snapshot_path,
        worker_drained=worker_drained,
        site_id=site_id,
        imported_versions=tuple(imported_versions),
    )


def main() -> None:
    result = run_cutover()
    print(json.dumps(asdict(result), default=str, indent=2))


if __name__ == "__main__":
    main()
