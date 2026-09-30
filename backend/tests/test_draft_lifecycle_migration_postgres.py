"""Story 5.11 Task 2: the one-working-draft migration on real PostgreSQL.

Proves what only a real database can: the duplicate collapse (AC5), the
`ended_by` backfill, the partial unique index, the lifecycle CHECK, the grants,
`command.check` staying clean against `schema.py`, and a reversible one-step
downgrade that leaves an ancestor grant standing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.postgres

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD = "f7a8b9c0d1e2"
T0 = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _config(connection) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def _upgrade(engine, revision: str) -> None:
    with engine.begin() as connection:
        command.upgrade(_config(connection), revision)


def _seed_base(connection) -> dict[str, UUID]:
    ids = {n: uuid4() for n in ("org", "site", "actor", "scenario", "sv", "conversation")}
    connection.execute(text("INSERT INTO organization (id, name) VALUES (:org, 'O')"), ids)
    connection.execute(
        text("INSERT INTO site (id, organization_id, name) VALUES (:site, :org, 'S')"), ids
    )
    connection.execute(
        text("INSERT INTO app_user (id, idp_subject, email) VALUES (:actor, :s, :e)"),
        {**ids, "s": f"s-{uuid4()}", "e": f"{uuid4()}@example.test"},
    )
    connection.execute(
        text("INSERT INTO scenario (id, site_id, fixture_id, name) VALUES (:scenario, :site, 'f', 'F')"),
        ids,
    )
    connection.execute(
        text(
            "INSERT INTO scenario_version (id, site_id, scenario_id, fixture_id, version, payload,"
            " checksum_digest) VALUES (:sv, :site, :scenario, 'f', 'v1', '{}'::jsonb, :d)"
        ),
        {**ids, "d": "a" * 64},
    )
    connection.execute(
        text(
            "INSERT INTO conversation (id, site_id, scenario_id, scenario_version_id,"
            " created_by_actor_id) VALUES (:conversation, :site, :scenario, :sv, :actor)"
        ),
        ids,
    )
    return ids


def _seed_proposal(connection, ids, *, state="active", created_at=T0, proposal_id=None,
                   conversation_id=None, with_version=True) -> UUID:
    proposal_id = proposal_id or uuid4()
    connection.execute(
        text(
            "INSERT INTO proposal (id, site_id, scenario_id, scenario_version_id, conversation_id,"
            " created_by_actor_id, state, created_at) VALUES (:id, :site, :scenario, :sv, :conv,"
            " :actor, :state, :created_at)"
        ),
        {**ids, "id": proposal_id, "state": state, "created_at": created_at,
         "conv": conversation_id or ids["conversation"]},
    )
    return proposal_id


def _seed_conversation(connection, ids) -> UUID:
    conversation_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO conversation (id, site_id, scenario_id, scenario_version_id,"
            " created_by_actor_id) VALUES (:c, :site, :scenario, :sv, :actor)"
        ),
        {**ids, "c": conversation_id},
    )
    return conversation_id


def _rows(engine) -> dict[UUID, tuple]:
    with engine.connect() as connection:
        return {
            r.id: (r.state, r.ended_by, r.resource_version)
            for r in connection.execute(
                text("SELECT id, state, ended_by, resource_version FROM proposal")
            )
        }


def test_upgrade_collapses_duplicate_active_drafts_and_backfills_ended_by(
    fresh_postgres_database_url: str,
) -> None:
    engine = create_engine(fresh_postgres_database_url)
    try:
        _upgrade(engine, PREVIOUS_HEAD)
        with engine.begin() as connection:
            ids = _seed_base(connection)
            # Two rows share created_at exactly: the id tie-breaker must decide.
            low, high = sorted([uuid4(), uuid4()])
            oldest = _seed_proposal(connection, ids, created_at=T0 - timedelta(hours=1))
            tied_low = _seed_proposal(connection, ids, created_at=T0, proposal_id=low)
            tied_high = _seed_proposal(connection, ids, created_at=T0, proposal_id=high)
            planner_rejected = _seed_proposal(
                connection, ids, state="rejected", created_at=T0 - timedelta(hours=2)
            )
            other_conversation = _seed_conversation(connection, ids)
            lone = _seed_proposal(connection, ids, conversation_id=other_conversation)

        _upgrade(engine, "head")
        rows = _rows(engine)

        assert rows[tied_high][:2] == ("active", None)  # newest by (created_at, id)
        assert rows[tied_low][:2] == ("rejected", "system")
        assert rows[oldest][:2] == ("rejected", "system")
        assert rows[tied_low][2] == 2 and rows[oldest][2] == 2  # resource_version + 1
        assert rows[planner_rejected][:2] == ("rejected", "planner")  # C18 backfill
        assert rows[lone][:2] == ("active", None)  # other conversations untouched
        assert rows[lone][2] == 1
    finally:
        engine.dispose()


def test_the_partial_unique_index_and_lifecycle_check_are_enforced(
    fresh_postgres_database_url: str,
) -> None:
    engine = create_engine(fresh_postgres_database_url)
    try:
        _upgrade(engine, "head")
        with engine.begin() as connection:
            ids = _seed_base(connection)
            _seed_proposal(connection, ids)
        with pytest.raises(IntegrityError, match="uq_proposal_one_active_per_conversation"):
            with engine.begin() as connection:
                _seed_proposal(connection, ids)
        # A second row that is ended is fine: the index is partial.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO proposal (id, site_id, scenario_id, scenario_version_id,"
                    " conversation_id, created_by_actor_id, state, ended_by)"
                    " VALUES (:id, :site, :scenario, :sv, :conversation, :actor,"
                    " 'rejected', 'planner')"
                ),
                {**ids, "id": uuid4()},
            )
        # `rejected` must say who ended it; `active` must not.
        for state, ended_by in (("rejected", None), ("active", "planner"), ("applied", "system")):
            with pytest.raises(IntegrityError, match="ck_proposal_lifecycle"):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO proposal (id, site_id, scenario_id, scenario_version_id,"
                            " conversation_id, created_by_actor_id, state, ended_by)"
                            " VALUES (:id, :site, :scenario, :sv, :c, :actor, :state, :ended_by)"
                        ),
                        {**ids, "id": uuid4(), "c": _seed_conversation(connection, ids),
                         "state": state, "ended_by": ended_by},
                    )
    finally:
        engine.dispose()


def test_head_matches_schema_metadata_and_grants_the_new_columns(
    fresh_postgres_database_url: str,
) -> None:
    engine = create_engine(fresh_postgres_database_url)
    try:
        with engine.begin() as connection:
            command.upgrade(_config(connection), "head")
        with engine.begin() as connection:
            command.check(_config(connection))
        with engine.connect() as connection:
            for column in ("ended_by", "applied_version_id", "state", "current_version_id"):
                assert connection.execute(
                    text(
                        "SELECT has_column_privilege('shiftmind_runtime', 'proposal', :c, 'UPDATE')"
                    ),
                    {"c": column},
                ).scalar_one() is True, column
    finally:
        engine.dispose()


def test_one_step_downgrade_round_trips_and_keeps_the_ancestor_grant(
    fresh_postgres_database_url: str,
) -> None:
    engine = create_engine(fresh_postgres_database_url)
    try:
        _upgrade(engine, "head")
        with engine.begin() as connection:
            ids = _seed_base(connection)
            proposal_id = uuid4()
            version_id = uuid4()
            _seed_proposal(connection, ids, proposal_id=proposal_id)
            connection.execute(
                text(
                    "INSERT INTO proposal_version (id, site_id, proposal_id, version_ordinal,"
                    " payload, canonical_hash) VALUES (:v, :site, :p, 1, '{}'::jsonb, :h)"
                ),
                {**ids, "v": version_id, "p": proposal_id, "h": "b" * 64},
            )
            connection.execute(
                text(
                    "UPDATE proposal SET state = 'applied', ended_by = 'system',"
                    " applied_version_id = :v WHERE id = :p"
                ),
                {"v": version_id, "p": proposal_id},
            )

        with engine.begin() as connection:
            command.downgrade(_config(connection), PREVIOUS_HEAD)
        with engine.connect() as connection:
            columns = {
                r[0]
                for r in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'proposal'"
                    )
                )
            }
            assert {"ended_by", "applied_version_id"}.isdisjoint(columns)
            # The applied draft returns to its pre-feature state (spec 2.5).
            assert connection.execute(
                text("SELECT state FROM proposal WHERE id = :p"), {"p": proposal_id}
            ).scalar_one() == "active"
            # Ancestor `e9f0a1b2c3d4`'s column grant survives this reversal.
            assert connection.execute(
                text(
                    "SELECT has_column_privilege('shiftmind_runtime', 'proposal', 'state', 'UPDATE')"
                )
            ).scalar_one() is True

        _upgrade(engine, "head")
        assert _rows(engine)[proposal_id][:2] == ("active", None)
    finally:
        engine.dispose()
