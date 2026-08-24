from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from adapters.postgres import conversation as conversation_adapter
from adapters.postgres.conversation import (
    AgentRunNotQueuedError,
    PostgresConversationRepository,
    UnsupportedActivityPayloadError,
)
from adapters.postgres.proposal import PostgresProposalRepository
from application.contracts.proposal import DraftConstraintProposalV1, ProposalV1
from application.contracts.scenario_projection import TaskV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.activity import TerminalOutcomeActivityV1
from application.contracts.dialogue import TerminalOutcomeV1
from adapters.postgres.schema import (
    agent_run,
    app_user,
    conversation,
    message,
    membership,
    organization,
    persisted_event,
    proposal,
    proposal_version,
    command_idempotency,
    scenario,
    scenario_version,
    site,
)
from application.use_cases.accept_turn import accept_turn
from application.use_cases.finalize_agent_run import finalize_agent_run
from application.use_cases.manage_proposal import (
    IdempotencyKeyConflictError,
    RejectedProposalError,
    StaleProposalError,
    StaleResourceVersionError,
    ProposalCommandError,
    reject_proposal,
    revise_proposal,
)

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
        for name in ("org", "site", "other_site", "scenario", "v1", "v2", "actor", "membership")
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
            insert(membership).values(
                id=ids["membership"],
                app_user_id=ids["actor"],
                site_id=ids["site"],
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


def test_events_after_does_not_leak_a_different_conversations_events(
    governed_postgres_engine, ids
) -> None:
    """A stream scoped to one conversation returns none of another's events.

    `persisted_event` carries both `stream_id` and a `conversation_id`
    correlation column; the intent is that replay filters on `stream_id`, not
    the correlation column, so a future run-scoped stream sharing a
    conversation's correlation id could not bleed into this replay under a
    sequence numbering that does not constrain it. Today
    `ck_persisted_event_stream_is_conversation` forces the two columns always
    equal, so this test cannot yet distinguish "filtered on stream_id" from
    "filtered on conversation_id" — both conversations differ in both columns
    at once. It still proves basic stream isolation; re-verify it actually
    exercises `stream_id` specifically once a stream_id != conversation_id
    case becomes constructible (Story 3.5's run-scoped streams are a
    candidate)."""
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
            .values(payload={"activity_type": "run_progress", "schema_version": "1"})
        )

    with pytest.raises(UnsupportedActivityPayloadError):
        with _site_context(engine, ids["site"]) as c:
            repo.events_after(c, stream_id=created.id, after=Decimal(0), limit=200)


def test_an_unrenderable_activity_variant_fails_typed_not_as_a_key_error(
    governed_postgres_engine, ids
) -> None:
    """Three of AD-20's eight discriminants are reserved names with no shipped
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
            .values(payload={"activity_type": "comparison", "schema_version": "1"})
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


def test_create_draft_bundle_is_committed_as_one_transaction(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    conversations = PostgresConversationRepository()
    proposals = PostgresProposalRepository()
    with _site_context(engine, ids["site"]) as connection:
        accepted = accept_turn(
            conversations,
            connection,
            conversation_id=created.id,
            site_id=ids["site"],
            actor_id=ids["actor"],
            text="Draft a repair",
        )
    assert accepted is not None
    with _site_context(engine, ids["site"]) as connection:
        claimed = conversations.claim_queued_run(
            connection,
            conversation_id=created.id,
            agent_run_id=accepted.event.agent_run_id,
        )
    assert claimed is not None
    draft = ProposalV1(
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        scenario_id=claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id,
        consequence_summary="Preserves all existing locks.",
        canonical_hash="c" * 64,
    )

    with _site_context(engine, ids["site"]) as connection:
        completed = finalize_agent_run(
            conversations,
            proposals,
            connection,
            claimed=claimed,
            status="agent_completed",
            payload=draft,
            request_id=uuid4(),
        )

    assert completed.event.payload.activity_type == "draft"
    assert completed.event.payload.proposal_id == draft.proposal_id
    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal).where(proposal.c.id == draft.proposal_id)
        ).scalar_one() == 1
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.id == draft.proposal_version_id
            )
        ).scalar_one() == 1
        assert admin.execute(
            select(func.count()).select_from(persisted_event).where(
                persisted_event.c.agent_run_id == claimed.agent_run_id,
                persisted_event.c.event_type == "draft",
            )
        ).scalar_one() == 1


def test_create_draft_bundle_rolls_back_proposal_when_event_write_fails(
    governed_postgres_engine, ids, monkeypatch
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    conversations = PostgresConversationRepository()
    proposals = PostgresProposalRepository()
    with _site_context(engine, ids["site"]) as connection:
        accepted = accept_turn(
            conversations, connection, conversation_id=created.id,
            site_id=ids["site"], actor_id=ids["actor"], text="Draft then fail",
        )
    assert accepted is not None
    with _site_context(engine, ids["site"]) as connection:
        claimed = conversations.claim_queued_run(
            connection, conversation_id=created.id,
            agent_run_id=accepted.event.agent_run_id,
        )
    assert claimed is not None
    draft = ProposalV1(
        proposal_id=uuid4(), proposal_version_id=uuid4(),
        scenario_id=claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id,
        consequence_summary="This transaction must roll back.",
        canonical_hash="d" * 64,
    )

    def _explode(_activity):
        raise RuntimeError("injected after proposal persistence")

    monkeypatch.setattr(conversation_adapter, "_payload_to_json", _explode)
    with pytest.raises(RuntimeError):
        with _site_context(engine, ids["site"]) as connection:
            finalize_agent_run(
                conversations, proposals, connection,
                claimed=claimed, status="agent_completed", payload=draft,
                request_id=uuid4(),
            )

    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal).where(proposal.c.id == draft.proposal_id)
        ).scalar_one() == 0
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.id == draft.proposal_version_id
            )
        ).scalar_one() == 0
        assert admin.execute(
            select(agent_run.c.status).where(agent_run.c.id == claimed.agent_run_id)
        ).scalar_one() == "agent_running"


def _draft_for_commands(engine, ids):
    created = _create(engine, ids, "v2")
    assert created is not None
    conversations = PostgresConversationRepository()
    proposals = PostgresProposalRepository()
    with _site_context(engine, ids["site"]) as connection:
        accepted = accept_turn(
            conversations, connection, conversation_id=created.id,
            site_id=ids["site"], actor_id=ids["actor"], text="Draft command fixture",
        )
    assert accepted is not None
    with _site_context(engine, ids["site"]) as connection:
        claimed = conversations.claim_queued_run(
            connection, conversation_id=created.id,
            agent_run_id=accepted.event.agent_run_id,
        )
    assert claimed is not None
    value = ProposalV1(
        proposal_id=uuid4(), proposal_version_id=uuid4(),
        scenario_id=claimed.scenario_id, scenario_version_id=claimed.scenario_version_id,
        canonical_hash="e" * 64, consequence_summary="One reversible constraint.",
    )
    with _site_context(engine, ids["site"]) as connection:
        finalize_agent_run(
            conversations, proposals, connection, claimed=claimed,
            status="agent_completed", payload=value, request_id=uuid4(),
        )
    return value


def _revision_constraint(n=2):
    """The UNTRUSTED wire shape a browser posts.

    No `resolved_entities`, no `label`, no `description` - a client cannot
    supply any of them, and the application composes all three from the pinned
    projection. Passing the trusted `DraftConstraintV1` here would exercise a
    path the API no longer exposes.
    """
    return DraftConstraintProposalV1(
        kind="set_min_workers_per_task",
        group="work-areas-and-tasks",
        record_id="task:pick",
        n=n,
    )


class _CurrentProjection:
    """Resolves exactly one task, so revision resolution runs for real."""

    def __init__(self, version_id):
        self.version_id = version_id

    def get_overview(self, _connection, _scenario_id):
        return SimpleNamespace(
            scenario_version_id=self.version_id, horizon_minutes=10080
        )

    def resolve_task(self, _connection, _scenario_id, scenario_version_id, record_id):
        if record_id != "task:pick":
            return SimpleNamespace(
                outcome="not_found", item=None,
                current_scenario_version_id=scenario_version_id,
            )
        return SimpleNamespace(
            outcome="resolved",
            current_scenario_version_id=scenario_version_id,
            item=TaskV1(
                record_id="task:pick", task_id="PICK-1", name="Pick",
                function="outbound", area_id="A1", area_name="Pick Face",
                unit_type_id=None,
            ),
        )


def test_revision_replay_does_not_append_a_second_version(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    kwargs = dict(
        proposal_id=original.proposal_id, site_id=ids["site"], actor_id=ids["actor"],
        constraints=(_revision_constraint(),), expected_resource_version=1,
        idempotency_key="revision-replay",
    )
    with _site_context(engine, ids["site"]) as connection:
        first = revise_proposal(repository, projection, connection, **kwargs)
    with _site_context(engine, ids["site"]) as connection:
        replay = revise_proposal(repository, projection, connection, **kwargs)

    assert first is not None
    assert replay is not None
    assert replay.proposal.proposal_version_id == first.proposal.proposal_version_id
    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.proposal_id == original.proposal_id,
                proposal_version.c.version_ordinal > 1,
            )
        ).scalar_one() == 1
        assert admin.execute(
            select(func.count()).select_from(command_idempotency).where(
                command_idempotency.c.operation == f"revision:{original.proposal_id}",
                command_idempotency.c.idempotency_key == "revision-replay",
            )
        ).scalar_one() == 1


def test_replaying_a_key_against_another_expected_version_conflicts(
    governed_postgres_engine, ids
) -> None:
    """AD-8 scopes the key to the expected resource version too.

    Reusing one key while claiming a different expected version is a
    semantically different command, so it must conflict rather than hand back
    the first command's stored result. Before this was fixed the second call
    returned 200 carrying the first call's payload.
    """
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    kwargs = dict(
        proposal_id=original.proposal_id, site_id=ids["site"], actor_id=ids["actor"],
        constraints=(_revision_constraint(),), expected_resource_version=1,
        idempotency_key="version-scoped",
    )
    with _site_context(engine, ids["site"]) as connection:
        revise_proposal(repository, projection, connection, **kwargs)
    with pytest.raises(IdempotencyKeyConflictError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection,
                **{**kwargs, "expected_resource_version": 2},
            )


def test_a_revision_cannot_smuggle_client_authored_content(
    governed_postgres_engine, ids
) -> None:
    """Every persisted label and description is application-composed.

    The wire contract carries identifiers and numbers only, and the stored
    version's description is rebuilt from the resolved task, so it cannot
    disagree with the argument beside it.
    """
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    with _site_context(engine, ids["site"]) as connection:
        revised = revise_proposal(
            repository, projection, connection, proposal_id=original.proposal_id,
            site_id=ids["site"], actor_id=ids["actor"],
            constraints=(_revision_constraint(n=7),),
            expected_resource_version=1, idempotency_key="composed",
        )
    assert revised is not None
    constraint = revised.proposal.constraints[0]
    assert constraint.n == 7
    assert constraint.description == "Keep at least 7 workers on Pick (PICK-1)."
    assert constraint.resolved_entities[0].label == "Pick (PICK-1)"
    assert constraint.resolved_entities[0].scenario_version_id == ids["v2"]


def test_a_revision_naming_an_unresolvable_record_is_refused(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    with pytest.raises(ProposalCommandError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection, proposal_id=original.proposal_id,
                site_id=ids["site"], actor_id=ids["actor"],
                constraints=(
                    DraftConstraintProposalV1(
                        kind="set_min_workers_per_task",
                        group="work-areas-and-tasks", record_id="task:ghost", n=1,
                    ),
                ),
                expected_resource_version=1, idempotency_key="ghost",
            )
    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.proposal_id == original.proposal_id
            )
        ).scalar_one() == 1


def test_a_revision_with_an_out_of_range_argument_is_refused(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    with pytest.raises(ProposalCommandError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection, proposal_id=original.proposal_id,
                site_id=ids["site"], actor_id=ids["actor"],
                constraints=(_revision_constraint(n=-5),),
                expected_resource_version=1, idempotency_key="negative",
            )
    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.proposal_id == original.proposal_id
            )
        ).scalar_one() == 1


def test_same_idempotency_key_with_another_body_conflicts_without_applying(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    common = dict(
        proposal_id=original.proposal_id, site_id=ids["site"], actor_id=ids["actor"],
        expected_resource_version=1, idempotency_key="conflicting-body",
    )
    with _site_context(engine, ids["site"]) as connection:
        revise_proposal(
            repository, projection, connection,
            constraints=(_revision_constraint(n=2),), **common,
        )
    with pytest.raises(IdempotencyKeyConflictError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection,
                constraints=(_revision_constraint(n=3),), **common,
            )
    with engine.connect() as admin:
        assert admin.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.proposal_id == original.proposal_id
            )
        ).scalar_one() == 2


def test_reject_is_terminal_and_replay_safe(governed_postgres_engine, ids) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    kwargs = dict(
        proposal_id=original.proposal_id, site_id=ids["site"], actor_id=ids["actor"],
        expected_resource_version=1, idempotency_key="reject-once",
    )
    with _site_context(engine, ids["site"]) as connection:
        first = reject_proposal(repository, projection, connection, **kwargs)
    with _site_context(engine, ids["site"]) as connection:
        replay = reject_proposal(repository, projection, connection, **kwargs)
    assert first == replay
    assert first is not None and first.proposal.state == "rejected"
    with pytest.raises(RejectedProposalError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection, proposal_id=original.proposal_id,
                site_id=ids["site"], actor_id=ids["actor"],
                constraints=(_revision_constraint(),),
                expected_resource_version=2, idempotency_key="revise-rejected",
            )


def test_commands_refuse_stale_resource_and_stale_scenario_without_rows(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    original = _draft_for_commands(engine, ids)
    repository = PostgresProposalRepository()
    projection = _CurrentProjection(ids["v2"])
    with pytest.raises(StaleResourceVersionError):
        with _site_context(engine, ids["site"]) as connection:
            reject_proposal(
                repository, projection, connection, proposal_id=original.proposal_id,
                site_id=ids["site"], actor_id=ids["actor"],
                expected_resource_version=99, idempotency_key="stale-resource",
            )
    stale_original = _create(engine, ids, "v1")
    assert stale_original is not None
    # A v1 proposal is stale because the governed projection resolves v2.
    stale_draft = ProposalV1(
        proposal_id=uuid4(), proposal_version_id=uuid4(), scenario_id=ids["scenario"],
        scenario_version_id=ids["v1"], canonical_hash="f" * 64,
    )
    with _site_context(engine, ids["site"]) as connection:
        repository.create_draft(
            connection, proposal=stale_draft, site_id=ids["site"],
            conversation_id=stale_original.id, actor_id=ids["actor"],
        )
    # Revising a stale proposal is refused: it would silently rebase (AD-9).
    with pytest.raises(StaleProposalError):
        with _site_context(engine, ids["site"]) as connection:
            revise_proposal(
                repository, projection, connection, proposal_id=stale_draft.proposal_id,
                site_id=ids["site"], actor_id=ids["actor"],
                constraints=(_revision_constraint(),),
                expected_resource_version=1, idempotency_key="stale-scenario-revise",
            )
    # Rejecting it is not. Rejection changes no baseline and is the only
    # terminal path a stale draft has; refusing it would strand the aggregate
    # `active` forever after a scenario reimport.
    with _site_context(engine, ids["site"]) as connection:
        closed = reject_proposal(
            repository, projection, connection, proposal_id=stale_draft.proposal_id,
            site_id=ids["site"], actor_id=ids["actor"],
            expected_resource_version=1, idempotency_key="stale-scenario-reject",
        )
    assert closed is not None
    assert closed.proposal.state == "rejected"
    assert closed.stale is True


def test_two_executors_claim_one_run_but_persist_one_terminal_response(
    governed_postgres_engine, ids
) -> None:
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()
    with _site_context(engine, ids["site"]) as connection:
        accepted = accept_turn(
            repo,
            connection,
            conversation_id=created.id,
            site_id=ids["site"],
            actor_id=ids["actor"],
            text="execute once",
        )
    assert accepted is not None

    def execute_once() -> str:
        try:
            with _site_context(engine, ids["site"]) as connection:
                claimed = repo.claim_queued_run(
                    connection,
                    conversation_id=created.id,
                    agent_run_id=accepted.event.agent_run_id,
                )
            assert claimed is not None
            with _site_context(engine, ids["site"]) as connection:
                repo.finish_agent_run(
                    connection,
                    claimed=claimed,
                    status="agent_completed",
                    payload=GroundedResponseV1(
                        scenario_version_id=claimed.scenario_version_id
                    ),
                    request_id=uuid4(),
                )
            return "completed"
        except AgentRunNotQueuedError:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _value: execute_once(), range(2)))

    assert sorted(outcomes) == ["completed", "refused"]
    with engine.connect() as admin:
        assert admin.execute(
            select(agent_run.c.status).where(
                agent_run.c.id == accepted.event.agent_run_id
            )
        ).scalar_one() == "agent_completed"
        assert admin.execute(
            select(func.count())
            .select_from(persisted_event)
            .where(
                persisted_event.c.agent_run_id == accepted.event.agent_run_id,
                persisted_event.c.event_type == "agent_response",
            )
        ).scalar_one() == 1


def test_latest_terminal_outcome_for_site_reads_the_newest_typed_agent_failure(
    governed_postgres_engine, ids
) -> None:
    """Story 3.9's availability read, against the real schema and RLS.

    Every other repository read here is covered against a live database; this one
    shipped covered only by an in-memory fake (Story 3.9 review), so a wrong
    column, filter, or ordering could not fail a test. Trap 5 named exactly this:
    `agent_run` stores `status` only, and the reason lives in the persisted
    activity payload -- a query against `agent_run.failure_reason` would pass a
    fake and break here.
    """
    engine = governed_postgres_engine
    created = _create(engine, ids)
    assert created is not None
    repo = PostgresConversationRepository()

    def finish(text: str, reason: str) -> None:
        with _site_context(engine, ids["site"]) as connection:
            accepted = accept_turn(
                repo, connection, conversation_id=created.id, site_id=ids["site"],
                actor_id=ids["actor"], text=text,
            )
        assert accepted is not None
        with _site_context(engine, ids["site"]) as connection:
            claimed = repo.claim_queued_run(
                connection,
                conversation_id=created.id,
                agent_run_id=accepted.event.agent_run_id,
            )
        assert claimed is not None
        with _site_context(engine, ids["site"]) as connection:
            repo.finish_agent_run(
                connection,
                claimed=claimed,
                status="agent_failed",
                payload=TerminalOutcomeV1(
                    status="failed", reason=reason, detail="Bounded copy."
                ),
                request_id=uuid4(),
            )

    # (a) Nothing terminal yet -> None, not an error and not a stale row.
    with _site_context(engine, ids["site"]) as connection:
        assert repo.latest_terminal_outcome_for_site(
            connection, site_id=ids["site"]
        ) is None

    # (b) A provider outage is found, and its typed reason survives the round
    #     trip through JSONB.
    finish("provider down", "provider_error")
    with _site_context(engine, ids["site"]) as connection:
        found = repo.latest_terminal_outcome_for_site(connection, site_id=ids["site"])
    assert found is not None
    assert found.event_type == "terminal_outcome"
    assert found.agent_run_id is not None
    assert isinstance(found.payload, TerminalOutcomeActivityV1)
    assert found.payload.outcome.reason == "provider_error"

    # (c) NEWEST wins, not "any provider_error that ever happened". This is what
    #     lets the availability read recover: a later non-provider failure means
    #     the provider answered, so the composer must not stay disabled.
    finish("bad output", "invalid_output")
    with _site_context(engine, ids["site"]) as connection:
        newest = repo.latest_terminal_outcome_for_site(connection, site_id=ids["site"])
    assert newest is not None
    assert isinstance(newest.payload, TerminalOutcomeActivityV1)
    assert newest.payload.outcome.reason == "invalid_output"
    assert newest.occurred_at >= found.occurred_at

    # (d) Site isolation is enforced by the governed context, not only by the
    #     `site_id` predicate the query also carries.
    other_site = uuid4()
    with _site_context(engine, other_site) as connection:
        assert repo.latest_terminal_outcome_for_site(
            connection, site_id=other_site
        ) is None
