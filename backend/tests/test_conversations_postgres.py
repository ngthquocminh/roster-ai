from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from adapters.postgres import conversation as conversation_adapter
from adapters.postgres.conversation import (
    PostgresConversationRepository,
    UnsupportedActivityPayloadError,
)
from adapters.postgres.schema import (
    agent_run,
    app_user,
    conversation,
    message,
    organization,
    persisted_event,
    scenario,
    scenario_version,
    site,
)
from application.use_cases.accept_turn import accept_turn

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def ids(governed_postgres_engine):
    """Seed the shared governed database once.

    `governed_postgres_engine` is module-scoped and several seed rows are
    singletons (`uq_app_user_singleton`), so seeding per test would collide.
    Tests therefore create their own conversation and scope every assertion to
    it rather than counting rows globally.
    """
    return _seed(governed_postgres_engine)


def _seed(engine):
    ids = {
        name: uuid4()
        for name in ("org", "site", "other_site", "scenario", "v1", "v2", "actor")
    }
    with engine.begin() as c:
        c.execute(insert(organization).values(id=ids["org"], name="Org"))
        c.execute(
            insert(site),
            [
                {"id": ids["site"], "organization_id": ids["org"], "name": "A"},
                {"id": ids["other_site"], "organization_id": ids["org"], "name": "B"},
            ],
        )
        c.execute(
            insert(app_user).values(
                id=ids["actor"], idp_subject="planner", email="planner@example.test"
            )
        )
        c.execute(
            insert(scenario).values(
                id=ids["scenario"],
                site_id=ids["site"],
                fixture_id="fixture",
                name="Fixture",
            )
        )
        # Two versions, so "the planner's selection" and "the newest row" are
        # distinguishable. v2 is inserted second and therefore wins any
        # latest-wins rule.
        c.execute(
            insert(scenario_version),
            [
                {
                    "id": ids["v1"],
                    "site_id": ids["site"],
                    "scenario_id": ids["scenario"],
                    "fixture_id": "fixture",
                    "version": "v1",
                    "payload": {},
                    "checksum_digest": "a" * 64,
                },
                {
                    "id": ids["v2"],
                    "site_id": ids["site"],
                    "scenario_id": ids["scenario"],
                    "fixture_id": "fixture",
                    "version": "v2",
                    "payload": {},
                    "checksum_digest": "b" * 64,
                },
            ],
        )
    return ids


@contextmanager
def _site_context(engine, site_id):
    """Mirror `api.deps.get_site_context` exactly.

    In particular the transaction is owned by `engine.begin()`, so a raised
    exception is rolled back by the same mechanism the request path uses — not
    by the test remembering to call `rollback()`.
    """
    with engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site, true)"),
            {"site": str(site_id)},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        yield connection


def _count_for(admin, table, conversation_id) -> int:
    """Rows of `table` belonging to one conversation.

    Scoped rather than global because the seeded database is shared across this
    module's tests.
    """
    return admin.execute(
        select(func.count())
        .select_from(table)
        .where(table.c.conversation_id == conversation_id)
    ).scalar_one()


def _create(engine, ids, version_key="v1"):
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        created = repo.create(
            c,
            scenario_id=ids["scenario"],
            scenario_version_id=ids[version_key],
            site_id=ids["site"],
            actor_id=ids["actor"],
        )
    return created


def test_create_pins_the_selected_version_not_the_newest(governed_postgres_engine, ids) -> None:
    engine = governed_postgres_engine

    created = _create(engine, ids, "v1")

    assert created is not None
    # v2 exists and is newer. A latest-wins resolution rule would return it.
    assert created.scenario_version_id == ids["v1"]


def test_create_rejects_a_version_belonging_to_another_scenario(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    other_scenario = uuid4()
    other_version = uuid4()
    with engine.begin() as c:
        c.execute(
            insert(scenario).values(
                id=other_scenario,
                site_id=ids["site"],
                fixture_id="other",
                name="Other",
            )
        )
        c.execute(
            insert(scenario_version).values(
                id=other_version,
                site_id=ids["site"],
                scenario_id=other_scenario,
                fixture_id="other",
                version="v1",
                payload={},
                checksum_digest="c" * 64,
            )
        )

    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        assert (
            repo.create(
                c,
                scenario_id=ids["scenario"],
                scenario_version_id=other_version,
                site_id=ids["site"],
                actor_id=ids["actor"],
            )
            is None
        )


def test_a_failure_after_the_message_leaves_no_partial_bundle(
    governed_postgres_engine, ids, monkeypatch
) -> None:
    """Atomicity proven by an injected failure, with no production seam.

    The injection point is a module-private helper, patched for this test only:
    it raises after `message` and `agent_run` are inserted and before the
    `persisted_event` insert, which is the widest partial-bundle window the
    accept-turn transaction has.
    """
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()

    def _explode(_activity):
        raise RuntimeError("injected")

    monkeypatch.setattr(conversation_adapter, "_payload_to_json", _explode)

    with pytest.raises(RuntimeError):
        with _site_context(engine, ids["site"]) as c:
            accept_turn(
                repo,
                c,
                conversation_id=created.id,
                site_id=ids["site"],
                actor_id=ids["actor"],
                text="rollback",
            )

    with engine.connect() as admin:
        for table in (message, agent_run, persisted_event):
            assert _count_for(admin, table, created.id) == 0
        # The version bump is part of the same bundle and must not survive either.
        assert (
            admin.execute(
                select(conversation.c.resource_version).where(
                    conversation.c.id == created.id
                )
            ).scalar_one()
            == 1
        )


def test_concurrent_turns_commit_and_bump_the_conversation_once_each(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()

    def send(value: str) -> str:
        with _site_context(engine, ids["site"]) as c:
            result = accept_turn(
                repo,
                c,
                conversation_id=created.id,
                site_id=ids["site"],
                actor_id=ids["actor"],
                text=value,
            )
            assert result
            return str(result.event.sequence)

    with ThreadPoolExecutor(max_workers=2) as pool:
        sequences = set(pool.map(send, ("one", "two")))

    assert sequences == {"1", "2"}
    with engine.connect() as admin:
        for table in (message, agent_run, persisted_event):
            assert _count_for(admin, table, created.id) == 2
        assert (
            admin.execute(
                select(conversation.c.resource_version).where(
                    conversation.c.id == created.id
                )
            ).scalar_one()
            == 3
        )


def test_the_unique_constraint_is_what_rejects_a_duplicate_sequence(
    governed_postgres_engine, ids
) -> None:
    """The serialization above is an optimisation; this is the guarantee.

    Task 2 requires the constraint itself to be the proof, so this bypasses the
    adapter and writes a colliding `(stream_id, sequence)` directly. Deleting
    `uq_persisted_event_stream_sequence` makes this test fail — which is the
    property the concurrency test alone cannot give.
    """
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accepted = accept_turn(
            repo,
            c,
            conversation_id=created.id,
            site_id=ids["site"],
            actor_id=ids["actor"],
            text="first",
        )
    assert accepted is not None

    with pytest.raises(IntegrityError):
        with _site_context(engine, ids["site"]) as c:
            c.execute(
                insert(persisted_event).values(
                    id=uuid4(),
                    site_id=ids["site"],
                    stream_id=created.id,
                    sequence=accepted.event.sequence,
                    event_type="planner_message_accepted",
                    resource_version=2,
                    request_id=uuid4(),
                    conversation_id=created.id,
                    agent_run_id=accepted.event.agent_run_id,
                    actor_id=ids["actor"],
                    payload={},
                )
            )


def test_a_stream_id_that_is_not_the_conversation_is_rejected(
    governed_postgres_engine, ids
) -> None:
    """AD-21 fixes the conversation stream's identity as the conversation UUID.

    Enforced by CHECK rather than convention so a later story cannot number a
    second stream against this conversation and collide inside one timeline.
    """
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accepted = accept_turn(
            repo, c, conversation_id=created.id, site_id=ids["site"],
            actor_id=ids["actor"], text="first",
        )
    assert accepted is not None

    with pytest.raises(DBAPIError):
        with _site_context(engine, ids["site"]) as c:
            c.execute(
                insert(persisted_event).values(
                    id=uuid4(),
                    site_id=ids["site"],
                    stream_id=uuid4(),
                    sequence=Decimal(99),
                    event_type="planner_message_accepted",
                    resource_version=2,
                    request_id=uuid4(),
                    conversation_id=created.id,
                    agent_run_id=accepted.event.agent_run_id,
                    actor_id=ids["actor"],
                    payload={},
                )
            )


def test_the_timeline_window_is_anchored_at_the_newest_events(
    governed_postgres_engine, ids
) -> None:
    """A head-anchored window stops showing the planner their own new messages
    once the stream passes `limit`; this asserts the opposite."""
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    for value in ("one", "two", "three"):
        with _site_context(engine, ids["site"]) as c:
            accept_turn(
                repo, c, conversation_id=created.id, site_id=ids["site"],
                actor_id=ids["actor"], text=value,
            )

    with _site_context(engine, ids["site"]) as c:
        window = repo.timeline(c, conversation_id=created.id, limit=2)
        full = repo.timeline(c, conversation_id=created.id, limit=200)

    assert window is not None and full is not None
    # Newest two, still in ascending order — and the truncation is reported.
    assert [e.payload.text for e in window.events] == ["two", "three"]
    assert window.has_more is True
    assert [str(e.sequence) for e in window.events] == ["2", "3"]
    assert [e.payload.text for e in full.events] == ["one", "two", "three"]
    assert full.has_more is False


def test_events_after_drains_forward_from_a_cursor_in_ascending_order(
    governed_postgres_engine, ids
) -> None:
    """Replay is the mirror image of `timeline()`, not a copy of it.

    `timeline()` shows the newest window of an unbounded history; replay drains
    forward from wherever a disconnected client stopped. Ascending order here is
    the whole point — a descending replay would deliver the backlog newest-first
    and a client applying it in arrival order would render the conversation
    inverted.
    """
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    for value in ("one", "two", "three"):
        with _site_context(engine, ids["site"]) as c:
            accept_turn(
                repo, c, conversation_id=created.id, site_id=ids["site"],
                actor_id=ids["actor"], text=value,
            )

    with _site_context(engine, ids["site"]) as c:
        everything = repo.events_after(
            c, stream_id=created.id, after=Decimal(0), limit=200
        )
        tail = repo.events_after(c, stream_id=created.id, after=Decimal(1), limit=200)
        drained = repo.events_after(c, stream_id=created.id, after=Decimal(3), limit=200)
        bounded = repo.events_after(c, stream_id=created.id, after=Decimal(0), limit=2)

    # (a) `after=0` replays the whole stream, oldest first.
    assert everything is not None
    assert [e.payload.text for e in everything] == ["one", "two", "three"]
    assert [str(e.sequence) for e in everything] == ["1", "2", "3"]
    # Strictly greater, never greater-or-equal: a client that already rendered
    # sequence 1 must not be handed it a second time.
    assert tail is not None
    assert [str(e.sequence) for e in tail] == ["2", "3"]
    # (b) `after=max` is a legal, common state meaning "nothing outstanding".
    assert drained == ()
    # The limit bounds the batch; the caller drains by advancing the cursor.
    assert bounded is not None
    assert [str(e.sequence) for e in bounded] == ["1", "2"]


def test_events_after_filters_on_stream_id_not_the_conversation_correlation(
    governed_postgres_engine, ids
) -> None:
    """`persisted_event` carries both `stream_id` and a `conversation_id`
    correlation column. Filtering on the latter would let a future run-scoped
    stream on the same conversation bleed into this replay under a sequence
    numbering that does not constrain it."""
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accept_turn(
            repo, c, conversation_id=created.id, site_id=ids["site"],
            actor_id=ids["actor"], text="only",
        )

    other = _create(engine, ids)
    assert other is not None
    with _site_context(engine, ids["site"]) as c:
        assert repo.events_after(
            c, stream_id=other.id, after=Decimal(0), limit=200
        ) == ()


def test_events_after_denies_another_site_indistinguishably_from_absence(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accept_turn(
            repo, c, conversation_id=created.id, site_id=ids["site"],
            actor_id=ids["actor"], text="private",
        )

    with _site_context(engine, ids["other_site"]) as c:
        # (c) `None`, exactly as `timeline()` answers — denial and absence are
        # the same answer (AD-3). An empty tuple would disclose existence.
        assert repo.events_after(
            c, stream_id=created.id, after=Decimal(0), limit=200
        ) is None
        assert repo.events_after(
            c, stream_id=uuid4(), after=Decimal(0), limit=200
        ) is None


def test_events_after_raises_typed_on_an_unrenderable_variant(
    governed_postgres_engine, ids
) -> None:
    """Same failure mode as `timeline()`. The SSE endpoint terminates that one
    connection on it rather than letting a 500 escape mid-body."""
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accept_turn(
            repo, c, conversation_id=created.id, site_id=ids["site"],
            actor_id=ids["actor"], text="first",
        )
    with engine.begin() as admin:
        admin.execute(
            persisted_event.update()
            .where(persisted_event.c.stream_id == created.id)
            .values(payload={"activity_type": "draft", "schema_version": "1"})
        )

    with pytest.raises(UnsupportedActivityPayloadError):
        with _site_context(engine, ids["site"]) as c:
            repo.events_after(c, stream_id=created.id, after=Decimal(0), limit=200)


def test_an_unrenderable_activity_variant_fails_typed_not_as_a_key_error(
    governed_postgres_engine, ids
) -> None:
    """Seven of AD-20's eight discriminants are reserved names with no shipped
    payload. Reaching one must not take the whole timeline down with a
    KeyError-turned-500."""
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as c:
        accepted = accept_turn(
            repo, c, conversation_id=created.id, site_id=ids["site"],
            actor_id=ids["actor"], text="first",
        )
    assert accepted is not None
    with engine.begin() as admin:
        admin.execute(
            persisted_event.update()
            .where(persisted_event.c.stream_id == created.id)
            .values(payload={"activity_type": "agent_response", "schema_version": "1"})
        )

    with pytest.raises(UnsupportedActivityPayloadError):
        with _site_context(engine, ids["site"]) as c:
            repo.timeline(c, conversation_id=created.id)


def test_another_site_can_neither_read_nor_write_this_conversation(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()

    with _site_context(engine, ids["other_site"]) as c:
        # Denial is indistinguishable from absence (AD-3): both are None, not
        # a distinct error.
        assert repo.timeline(c, conversation_id=created.id) is None
        assert (
            accept_turn(
                repo, c, conversation_id=created.id, site_id=ids["other_site"],
                actor_id=ids["actor"], text="hidden",
            )
            is None
        )
        assert (
            repo.create(
                c,
                scenario_id=ids["scenario"],
                scenario_version_id=ids["v1"],
                site_id=ids["other_site"],
                actor_id=ids["actor"],
            )
            is None
        )
        assert repo.list_for_scenario(c, scenario_id=ids["scenario"]).items == ()
