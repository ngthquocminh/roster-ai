"""Contract tests for the PostgreSQL/Alembic toolchain introduced by Story 1.1."""
from __future__ import annotations

from pathlib import Path

from settings import default_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def test_postgres_dependencies_are_locked_to_architecture_versions() -> None:
    project = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"sqlalchemy==2.0.51"' in project
    assert '"psycopg[binary]==3.3.4"' in project
    assert '"alembic==1.18.5"' in project


def test_database_url_uses_psycopg3_default(monkeypatch) -> None:
    monkeypatch.delenv("ROSTERAI_DATABASE_URL", raising=False)

    assert (
        default_settings().database_url
        == "postgresql+psycopg://shiftmind_login:shiftmind_login@localhost:5432/rosterai"
    )


def test_database_url_can_be_overridden(monkeypatch) -> None:
    url = "postgresql+psycopg://test_user:test_password@db:5432/test_db"
    monkeypatch.setenv("ROSTERAI_DATABASE_URL", url)

    assert default_settings().database_url == url


def test_provisioning_database_url_defaults_to_the_privileged_superuser(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ROSTERAI_PROVISIONING_DATABASE_URL", raising=False)

    assert (
        default_settings().provisioning_database_url
        == "postgresql+psycopg://rosterai:rosterai@localhost:5432/rosterai"
    )


def test_provisioning_database_url_can_be_overridden(monkeypatch) -> None:
    url = "postgresql+psycopg://migrator:migrator@db:5432/test_db"
    monkeypatch.setenv("ROSTERAI_PROVISIONING_DATABASE_URL", url)

    assert default_settings().provisioning_database_url == url


def test_compose_defines_only_the_postgres_18_service() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "postgres:" in compose
    assert "postgres:18" in compose
    assert "5432:5432" in compose
    assert "postgres_data:/var/lib/postgresql" in compose
    assert "postgres_data:/var/lib/postgresql/data" not in compose
    services_block = compose.split("services:\n", 1)[1].split("\nvolumes:", 1)[0]
    service_lines = [
        line.strip()
        for line in services_block.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
    ]
    assert service_lines == ["postgres:"]


def test_alembic_is_wired_to_application_settings_and_metadata() -> None:
    config = (REPO_ROOT / "alembic.ini").read_text(encoding="utf-8")
    env = (BACKEND_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "script_location = %(here)s/backend/migrations" in config
    assert "default_settings().provisioning_database_url" in env
    assert "target_metadata = metadata" in env
    assert "context.configure(" in env
    assert "connection=connection" in env
    assert "target_metadata=target_metadata" in env
