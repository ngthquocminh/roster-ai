from dataclasses import replace
from pathlib import Path

import pytest

from scripts.bootstrap_local import bootstrap_local
from settings import default_settings


@pytest.mark.postgres
def test_bootstrap_is_idempotent(
    fresh_postgres_database_url, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_SUBJECT", "local-planner")
    monkeypatch.setenv("SHIFTMIND_SEED_PLANNER_EMAIL", "planner@shiftmind.local")
    settings = replace(
        default_settings(),
        provisioning_database_url=fresh_postgres_database_url,
        database_url=fresh_postgres_database_url,
    )

    first = bootstrap_local(settings=settings)
    replay = bootstrap_local(settings=settings)

    assert len(first.fixtures) == 2
    assert all(item.created for item in first.fixtures)
    assert all(not item.created for item in replay.fixtures)
    assert first.planner.created is True
    assert replay.planner.created is False


def test_bootstrap_imports_the_canonical_fixture_list() -> None:
    source = (Path(__file__).parents[1] / "scripts/bootstrap_local.py").read_text()
    assert "default_fixtures()" in source
    assert "sample_tiny_input" not in source
    assert "_enable_maintenance" not in source
    assert "_snapshot_sqlite" not in source
