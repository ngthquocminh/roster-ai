"""Idempotently bootstrap the local PostgreSQL environment without Gate A cutover."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

from adapters.postgres.fixture_history import FixtureImportResult, PostgresFixtureHistoryAdapter
from scripts.gate_a_cutover import REPO_ROOT, default_fixtures
from scripts.seed_planner import SeedPlannerResult, provision_seed_planner
from settings import Settings, default_settings


@dataclass(frozen=True)
class BootstrapResult:
    fixtures: tuple[FixtureImportResult, ...]
    planner: SeedPlannerResult


def bootstrap_local(
    *, settings: Settings | None = None, engine: Engine | None = None
) -> BootstrapResult:
    resolved = settings or default_settings()
    owned_engine = engine is None
    privileged_engine = engine or create_engine(
        resolved.provisioning_database_url, hide_parameters=True
    )
    try:
        config = Config(str(REPO_ROOT / "alembic.ini"))
        with privileged_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        importer = PostgresFixtureHistoryAdapter(
            resolved.provisioning_database_url, engine=privileged_engine
        )
        site_id = importer.ensure_seed_site("ShiftMind", "Seeded Site")
        imported = []
        for fixture in default_fixtures():
            payload = json.loads(fixture.path.read_text(encoding="utf-8"))
            imported.append(
                importer.import_fixture(
                    site_id=site_id,
                    fixture_id=fixture.fixture_id,
                    version=fixture.version,
                    payload=payload,
                    source_package="predefined-fixtures",
                    source_path=str(fixture.path.resolve().relative_to(REPO_ROOT)),
                )
            )
        planner = provision_seed_planner(
            subject=resolved.seed_planner_subject,
            email=resolved.seed_planner_email,
            site_id=site_id,
            engine=privileged_engine,
        )
        return BootstrapResult(fixtures=tuple(imported), planner=planner)
    finally:
        if owned_engine:
            privileged_engine.dispose()


def main() -> None:
    result = bootstrap_local()
    print(
        f"bootstrapped {len(result.fixtures)} fixtures; "
        f"planner_created={result.planner.created}"
    )


if __name__ == "__main__":
    main()


__all__ = ["BootstrapResult", "bootstrap_local"]
