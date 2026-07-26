"""Operator-only seeded planner provisioning contracts."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from adapters.postgres.fixture_history import PostgresFixtureHistoryAdapter
from adapters.postgres.schema import app_user, membership
from scripts.seed_planner import (
    SeedPlannerConflictError,
    provision_seed_planner,
    seed_planner_from_env,
)
from settings import default_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def _migrated_engine(database_url: str):
    engine = create_engine(database_url)
    config = Config(str(REPO_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine


@pytest.mark.postgres
def test_seed_planner_provisioning_is_semantically_idempotent(
    fresh_postgres_database_url,
) -> None:
    governed_postgres_engine = _migrated_engine(fresh_postgres_database_url)
    suffix = uuid4().hex
    site_id = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=governed_postgres_engine,
    ).ensure_seed_site(
        f"Seed Organization {suffix}",
        f"Seed Site {suffix}",
    )

    first = provision_seed_planner(
        subject=f"planner-{suffix}",
        email=f"planner-{suffix}@example.test",
        site_id=site_id,
        engine=governed_postgres_engine,
    )
    replay = provision_seed_planner(
        subject=f"planner-{suffix}",
        email=f"planner-{suffix}@example.test",
        site_id=site_id,
        engine=governed_postgres_engine,
    )

    assert first.created is True
    assert replay.created is False
    assert replay.app_user_id == first.app_user_id
    assert replay.membership_id == first.membership_id
    assert replay.site_id == first.site_id
    governed_postgres_engine.dispose()


@pytest.mark.postgres
def test_second_identity_is_rejected_without_mutating_seeded_rows(
    fresh_postgres_database_url,
) -> None:
    governed_postgres_engine = _migrated_engine(fresh_postgres_database_url)
    suffix = uuid4().hex
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=governed_postgres_engine,
    )
    site_id = adapter.ensure_seed_site(
        f"Conflict Organization {suffix}",
        f"Conflict Site {suffix}",
    )
    provision_seed_planner(
        subject=f"seeded-{suffix}",
        email=f"seeded-{suffix}@example.test",
        site_id=site_id,
        engine=governed_postgres_engine,
    )
    with governed_postgres_engine.connect() as connection:
        before_users = connection.execute(select(app_user)).all()
        before_memberships = connection.execute(select(membership)).all()

    with pytest.raises(SeedPlannerConflictError):
        provision_seed_planner(
            subject=f"second-{suffix}",
            email=f"second-{suffix}@example.test",
            site_id=site_id,
            engine=governed_postgres_engine,
        )

    with governed_postgres_engine.connect() as connection:
        assert connection.execute(select(app_user)).all() == before_users
        assert connection.execute(select(membership)).all() == before_memberships
    governed_postgres_engine.dispose()


def test_seed_planner_requires_operator_environment(monkeypatch) -> None:
    monkeypatch.delenv("SHIFTMIND_SEED_PLANNER_SUBJECT", raising=False)
    monkeypatch.delenv("SHIFTMIND_SEED_PLANNER_EMAIL", raising=False)
    settings = replace(
        default_settings(),
        database_url="postgresql+psycopg://unused:unused@unused/unused",
    )

    with pytest.raises(ValueError, match="SHIFTMIND_SEED_PLANNER_SUBJECT"):
        seed_planner_from_env(settings=settings)


@pytest.mark.postgres
def test_database_rejects_second_user_and_active_membership_atomically(
    fresh_postgres_database_url,
) -> None:
    engine = _migrated_engine(fresh_postgres_database_url)
    suffix = uuid4().hex
    site_id = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=engine,
    ).ensure_seed_site(f"Constraint Organization {suffix}", f"Site {suffix}")
    seeded = provision_seed_planner(
        subject=f"seeded-{suffix}",
        email=f"seeded-{suffix}@example.test",
        site_id=site_id,
        engine=engine,
    )
    with engine.connect() as connection:
        users_before = connection.execute(select(app_user)).all()
        memberships_before = connection.execute(select(membership)).all()

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                app_user.insert().values(
                    idp_subject=f"second-{suffix}",
                    email=f"second-{suffix}@example.test",
                )
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                membership.insert().values(
                    app_user_id=seeded.app_user_id,
                    site_id=seeded.site_id,
                )
            )

    with engine.connect() as connection:
        assert connection.execute(select(app_user)).all() == users_before
        assert connection.execute(select(membership)).all() == memberships_before
    engine.dispose()
