"""Story 5.11: the one-working-draft lifecycle and its races, on real PostgreSQL.

Drives the REAL tool handlers (`scheduling_draft`, `scheduling_draft_discard`)
with a real `DraftTurnState` reader, and the REAL `finalize_agent_run` on real
repositories. A race is staged sequentially and deterministically (Decision 16):

1. the tool observes the working draft;
2. the competing action commits (planner edit, planner discard, a real
   promotion, or another turn's finalize);
3. the first turn finalizes.

Plus one two-connection test for the conversation lock itself. Spec 5.1's
"golden multi-turn case" is `test_the_five_turn_lifecycle...` here, because the
golden multi-turn harness persists nothing (C16).
"""
from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError

from adapters.postgres.conversation import PostgresConversationRepository
from adapters.postgres.proposal import PostgresProposalRepository
from adapters.postgres.schema import (
    agent_run,
    command_idempotency,
    conversation,
    persisted_event,
    proposal,
    proposal_version,
    scenario,
    scenario_version,
)
from api.deps import site_context
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import (
    SchedulingDraftRequestV1,
    SchedulingDraftResultV1,
    scheduling_draft,
)
from application.capabilities.scheduling_draft_discard import (
    DraftChangedThisTurnError,
    NoWorkingDraftError,
    SchedulingDraftDiscardRequestV1,
    scheduling_draft_discard,
)
from application.contracts.agent_runtime import AgentBudgetV1, AgentRunOutcomeV1
from application.contracts.dialogue import TerminalOutcomeV1
from application.contracts.grounding import GroundedProseSegmentV1, GroundedResponseV1
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    DraftProposalV1,
    WorkingDraftObservationV1,
)
from application.contracts.scenario_projection import ScenarioOverviewV1, TaskV1, WorkerV1
from application.drafting.turn_state import DraftTurnState
from application.ports.scenario_projection import LockPageV1
from application.use_cases.accept_turn import accept_turn
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval
from application.use_cases.execute_turn import (
    activity_payload,
    resolve_discard,
    resolve_draft_citation,
    terminal_status,
)
from application.use_cases.finalize_agent_run import (
    DRAFT_CHANGED_DETAIL,
    DRAFT_CHANGED_NEXT_STEP,
    finalize_agent_run,
)
from application.use_cases.manage_proposal import (
    AppliedProposalError,
    RejectedProposalError,
    get_proposal,
    reject_proposal,
    revise_proposal,
)
from tests.test_approval_audit_invariants_postgres import _request
from tests.test_approval_governance_postgres import (
    NOW,
    _decision_dependencies,
    _governance_headers,
    _seed_candidate_run,
    decision_http_client,  # noqa: F401  (fixture)
    site_ids,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.postgres


# --- a projection that resolves exactly one task and one worker ----------------


class _Projection:
    """In-memory projection for the tool and the planner command paths.

    The lifecycle under test is the persistence one; resolution is exercised by
    its own suites, so this resolves `task-1` and `worker-1` and nothing else.
    """

    def __init__(self, conv: dict) -> None:
        self.conv = conv
        self.task = TaskV1("task-1", "task-1", "Picking", "Pick", "area-1", "Area 1", None)
        self.worker = WorkerV1("worker-1", "worker-1", "Alex", "FT", "1", "EBA", 38.0, (), ())

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            scenario_id=self.conv["scenario"], scenario_version_id=self.conv["version"],
            site_id=self.conv["site"], fixture_id="fixture", scenario_name="Scenario",
            fixture_version="v1", checksum_algorithm="sha256",
            checksum_schema_version="rfc8785-v1", checksum_digest="a" * 64,
            horizon_start=datetime(2026, 8, 18, tzinfo=timezone.utc), site_timezone="UTC",
            horizon_minutes=10080, baseline_schedule_version=None,
            projection_generated_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            work_area_count=1, task_count=1, worker_count=1, demand_interval_count=0,
            baseline_assignment_count=0, lock_count=0, constraint_count=0,
        )

    def get_locks(self, _connection, _scenario_id, query):
        return LockPageV1(
            scenario_id=self.conv["scenario"], scenario_version_id=self.conv["version"],
            site_id=self.conv["site"], items=(), next_cursor=None, total_count=0,
            matching_count=0,
        )

    def resolve_task(self, _c, _s, version_id, record_id):
        return self._resolution(self.task, version_id, record_id)

    def resolve_worker(self, _c, _s, version_id, record_id):
        return self._resolution(self.worker, version_id, record_id)

    def _resolution(self, item, version_id, record_id):
        found = record_id == item.record_id
        return type("Resolution", (), {
            "outcome": "resolved" if found else "not_found",
            "item": item if found else None,
            "current_scenario_version_id": self.conv["version"],
        })()


def _hours(value: float = 40.0) -> DraftConstraintProposalV1:
    return DraftConstraintProposalV1(
        kind="set_max_hours", group="workers", record_id="worker-1", max_hours=value,
    )


def _min_workers(n: int = 2) -> DraftConstraintProposalV1:
    return DraftConstraintProposalV1(
        kind="set_min_workers_per_task", group="work-areas-and-tasks",
        record_id="task-1", n=n,
    )


# --- conversation seeding and the turn driver ----------------------------------


@pytest.fixture()
def conv(governed_postgres_engine, site_ids) -> dict:  # noqa: F811
    """One fresh scenario, version and conversation; every assertion is scoped to it."""
    engine = governed_postgres_engine
    ids = {
        "site": site_ids["site"], "actor": site_ids["actor"], "scenario": uuid4(),
        "version": uuid4(), "conversation": uuid4(),
    }
    fixture_id = f"f-{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(insert(scenario).values(
            id=ids["scenario"], site_id=ids["site"], fixture_id=fixture_id, name="F"))
        connection.execute(insert(scenario_version).values(
            id=ids["version"], site_id=ids["site"], scenario_id=ids["scenario"],
            fixture_id=fixture_id, version="v1", payload={}, checksum_digest="a" * 64))
        connection.execute(insert(conversation).values(
            id=ids["conversation"], site_id=ids["site"], scenario_id=ids["scenario"],
            scenario_version_id=ids["version"], created_by_actor_id=ids["actor"]))
    return ids


CONVERSATIONS = PostgresConversationRepository()
PROPOSALS = PostgresProposalRepository()


class Turn:
    """One agent turn: accepted, claimed, then driven tool by tool, then finalized."""

    def __init__(self, engine, conv: dict, prompt: str = "Draft it") -> None:
        self.engine, self.conv = engine, conv
        with site_context(engine, conv["site"]) as connection:
            accepted = accept_turn(
                CONVERSATIONS, connection, conversation_id=conv["conversation"],
                site_id=conv["site"], actor_id=conv["actor"], text=prompt)
        assert accepted is not None
        with site_context(engine, conv["site"]) as connection:
            self.claimed = CONVERSATIONS.claim_queued_run(
                connection, conversation_id=conv["conversation"],
                agent_run_id=accepted.event.agent_run_id)
        assert self.claimed is not None
        self.results: list[object] = []
        self.state = DraftTurnState(self._read_working)
        self.deps = AgentDepsV1(
            actor_id=conv["actor"], site_id=conv["site"], membership_id=uuid4(),
            request_id=uuid4(), agent_run_id=self.claimed.agent_run_id,
            conversation_id=conv["conversation"], scenario_id=conv["scenario"],
            scenario_version_id=conv["version"], policy_version="v1",
            clock=lambda: datetime.now(timezone.utc), projection_reader=_Projection(conv),
            connection=None, remaining_budget=AgentBudgetV1(tool_calls_limit=10),
            tool_result_sink=self.results.append, draft_turn=self.state,
        )

    def _read_working(self) -> WorkingDraftObservationV1 | None:
        with site_context(self.engine, self.conv["site"]) as connection:
            working = PROPOSALS.get_working(
                connection, conversation_id=self.conv["conversation"], for_update=False)
        if working is None:
            return None
        return WorkingDraftObservationV1(
            working.proposal.proposal_id, working.proposal.resource_version,
            working.version_ordinal)

    # the real tool handlers -----------------------------------------------------
    def draft(self, *constraints: DraftConstraintProposalV1) -> SchedulingDraftResultV1:
        result = scheduling_draft(self.deps, SchedulingDraftRequestV1(
            expected_scenario_version_id=self.conv["version"], constraints=constraints))
        self.results.append(result)
        return result

    def discard(self):
        result = scheduling_draft_discard(self.deps, SchedulingDraftDiscardRequestV1())
        self.results.append(result)
        return result

    def finalize(self, *, cite: SchedulingDraftResultV1 | None = None):
        """Bind and finalize exactly as the route does."""
        outcome = AgentRunOutcomeV1(status="completed")
        if cite is not None:
            outcome = replace(outcome, draft=DraftProposalV1(draft_id=cite.result_id))
            outcome = resolve_draft_citation(
                outcome, {r.result_id: r for r in self.results
                          if isinstance(r, SchedulingDraftResultV1)})
        else:
            outcome = replace(outcome, grounded_response=GroundedResponseV1(
                scenario_version_id=self.conv["version"],
                segments=(GroundedProseSegmentV1(text="Done."),)))
        outcome = replace(outcome, resolved_discard=resolve_discard(self.results))
        status = terminal_status(outcome)
        with site_context(self.engine, self.conv["site"]) as connection:
            return finalize_agent_run(
                CONVERSATIONS, PROPOSALS, connection, claimed=self.claimed, status=status,
                payload=activity_payload(outcome, self.deps),
                discard=outcome.resolved_discard if status == "agent_completed" else None,
                request_id=self.deps.request_id)


# --- reading state back ----------------------------------------------------------


def _proposals(engine, conv: dict) -> list[tuple]:
    with engine.connect() as connection:
        return [
            (r.id, r.state, r.ended_by, r.resource_version, r.current_version_id)
            for r in connection.execute(
                select(proposal).where(proposal.c.conversation_id == conv["conversation"])
                .order_by(proposal.c.created_at, proposal.c.id))
        ]


def _version_count(engine, conv: dict) -> int:
    with engine.connect() as connection:
        return connection.execute(
            select(func.count()).select_from(proposal_version).where(
                proposal_version.c.proposal_id.in_(
                    select(proposal.c.id).where(proposal.c.conversation_id == conv["conversation"])
                ))).scalar_one()


def _ordinals(engine, proposal_id: UUID) -> list[int]:
    with engine.connect() as connection:
        return [r for r in connection.execute(
            select(proposal_version.c.version_ordinal)
            .where(proposal_version.c.proposal_id == proposal_id)
            .order_by(proposal_version.c.version_ordinal)).scalars()]


def _active(engine, conv: dict) -> list[UUID]:
    return [row[0] for row in _proposals(engine, conv) if row[1] == "active"]


def _events(engine, run_id: UUID) -> list:
    with engine.connect() as connection:
        return list(connection.execute(
            select(persisted_event.c.event_type, persisted_event.c.payload)
            .where(persisted_event.c.agent_run_id == run_id)
            .order_by(persisted_event.c.sequence)))


def _run_status(engine, run_id: UUID) -> str:
    """The PERSISTED `agent_run.status`, not the use case's return value (AC2)."""
    with engine.connect() as connection:
        return connection.execute(
            select(agent_run.c.status).where(agent_run.c.id == run_id)).scalar_one()


def _planner_revise(engine, conv, proposal_id, constraints, expected_resource_version, key=None):
    with site_context(engine, conv["site"]) as connection:
        return revise_proposal(
            PROPOSALS, _Projection(conv), connection, proposal_id=proposal_id,
            site_id=conv["site"], actor_id=conv["actor"], constraints=tuple(constraints),
            expected_resource_version=expected_resource_version,
            idempotency_key=key or uuid4().hex[:30])


def _planner_reject(engine, conv, proposal_id, expected_resource_version, key=None):
    with site_context(engine, conv["site"]) as connection:
        return reject_proposal(
            PROPOSALS, _Projection(conv), connection, proposal_id=proposal_id,
            site_id=conv["site"], actor_id=conv["actor"],
            expected_resource_version=expected_resource_version,
            idempotency_key=key or uuid4().hex[:30])


def _promote(engine, conv, site_ids, proposal_id: UUID, version_id: UUID):  # noqa: F811
    """A REAL promotion (request + approve) of a run pinning `version_id`."""
    ids = _seed_candidate_run(
        engine, site_id=conv["site"], actor_id=conv["actor"],
        reuse={"scenario": conv["scenario"], "scenario_version": conv["version"],
               "conversation": conv["conversation"], "proposal": proposal_id,
               "proposal_version": version_id})
    binding = _request(engine, ids, site_ids)
    with site_context(engine, conv["site"]) as connection:
        result = decide_approval(
            connection,
            command=DecideApprovalCommandV1(
                site_id=conv["site"], actor_id=conv["actor"], approval_id=binding.approval_id,
                decision="approve", expected_resource_version=binding.resource_version,
                request_id=uuid4()),
            **_decision_dependencies())
    assert result.outcome == "consumed"
    return ids


def _draft_and_finalize(engine, conv, *constraints, prompt="Draft it"):
    turn = Turn(engine, conv, prompt)
    result = turn.draft(*constraints)
    return turn, result, turn.finalize(cite=result)


# ===================================================================================
# AC1 - one working draft: created, then updated in place
# ===================================================================================


def test_no_working_draft_creates_v1_active(governed_postgres_engine, conv) -> None:
    engine = governed_postgres_engine
    _, result, executed = _draft_and_finalize(engine, conv, _hours())
    assert (result.outcome, result.version_ordinal) == ("created", 1)
    rows = _proposals(engine, conv)
    assert [(row[1], row[2], row[3]) for row in rows] == [("active", None, 1)]
    assert executed.event.payload.activity_type == "draft"
    assert executed.event.payload.proposal_id == result.proposal.proposal_id
    assert _ordinals(engine, result.proposal.proposal_id) == [1]


def test_a_working_draft_is_updated_in_place_with_the_next_version(governed_postgres_engine, conv) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours(40.0), _min_workers(2))
    with engine.connect() as connection:
        idempotency_before = connection.execute(
            select(func.count()).select_from(command_idempotency)).scalar_one()
    turn = Turn(engine, conv, "Drop the minimum, cap at 35")
    second = turn.draft(_hours(35.0))
    executed = turn.finalize(cite=second)

    assert (second.outcome, second.version_ordinal) == ("updated", 2)
    assert second.proposal.proposal_id == first.proposal.proposal_id
    (row,) = _proposals(engine, conv)
    assert row[:4] == (first.proposal.proposal_id, "active", None, 2)  # resource_version + 1
    assert row[4] == second.proposal.proposal_version_id  # pointer moved
    assert _ordinals(engine, first.proposal.proposal_id) == [1, 2]
    # A NEW draft activity carries the existing proposal id and the new version id.
    assert executed.event.payload.proposal_id == first.proposal.proposal_id
    assert executed.event.payload.proposal_version_id == second.proposal.proposal_version_id
    assert executed.event.payload.proposal_version_id != first.proposal.proposal_version_id
    # The full list was REPLACED, not merged.
    with site_context(engine, conv["site"]) as connection:
        record = PROPOSALS.get_current(connection, proposal_id=first.proposal.proposal_id)
        assert [c.kind for c in record.proposal.constraints] == ["set_max_hours"]
        assert record.version_ordinal == 2
    # No idempotency row: the claimable-run guard already makes finalize exactly-once.
    with engine.connect() as connection:
        assert connection.execute(
            select(func.count()).select_from(command_idempotency)).scalar_one() == idempotency_before


def test_a_second_active_proposal_for_a_conversation_violates_the_unique_index(
    governed_postgres_engine, conv
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    other = replace(first.proposal, proposal_id=uuid4(), proposal_version_id=uuid4())
    with pytest.raises(IntegrityError, match="uq_proposal_one_active_per_conversation"):
        with site_context(engine, conv["site"]) as connection:
            PROPOSALS.create_draft(
                connection, proposal=other, site_id=conv["site"],
                conversation_id=conv["conversation"], actor_id=conv["actor"])
    assert len(_active(engine, conv)) == 1


def test_the_five_turn_lifecycle_ends_with_exactly_one_active_draft(governed_postgres_engine, conv) -> None:
    """Spec 5.1: draft -> add -> remove -> discard -> new request."""
    engine = governed_postgres_engine
    _, t1, _ = _draft_and_finalize(engine, conv, _hours(40.0))
    _, t2, _ = _draft_and_finalize(engine, conv, _hours(40.0), _min_workers(2))
    _, t3, _ = _draft_and_finalize(engine, conv, _min_workers(2))
    assert [t.outcome for t in (t1, t2, t3)] == ["created", "updated", "updated"]
    assert _ordinals(engine, t1.proposal.proposal_id) == [1, 2, 3]

    turn4 = Turn(engine, conv, "Throw my draft away")
    turn4.discard()
    turn4.finalize()
    assert _active(engine, conv) == []

    _, t5, _ = _draft_and_finalize(engine, conv, _hours(30.0))
    assert (t5.outcome, t5.version_ordinal) == ("created", 1)
    rows = {row[0]: row for row in _proposals(engine, conv)}
    assert len(rows) == 2 and _active(engine, conv) == [t5.proposal.proposal_id]
    assert rows[t1.proposal.proposal_id][1:3] == ("rejected", "assistant")
    assert _ordinals(engine, t1.proposal.proposal_id) == [1, 2, 3]
    assert _ordinals(engine, t5.proposal.proposal_id) == [1]


def test_get_working_returns_only_this_conversations_active_draft(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    other = {**conv, "conversation": uuid4()}
    with engine.begin() as connection:
        connection.execute(insert(conversation).values(
            id=other["conversation"], site_id=conv["site"], scenario_id=conv["scenario"],
            scenario_version_id=conv["version"], created_by_actor_id=conv["actor"]))
    _, mine, _ = _draft_and_finalize(engine, conv, _hours())
    _draft_and_finalize(engine, other, _min_workers())
    with site_context(engine, conv["site"]) as connection:
        working = PROPOSALS.get_working(
            connection, conversation_id=conv["conversation"], for_update=True)
        assert working.proposal.proposal_id == mine.proposal.proposal_id
        assert (working.version_ordinal, working.proposal.state, working.ended_by) == (1, "active", None)
    _planner_reject(engine, conv, mine.proposal.proposal_id, 1)
    with site_context(engine, conv["site"]) as connection:
        assert PROPOSALS.get_working(
            connection, conversation_id=conv["conversation"], for_update=False) is None
        ended = PROPOSALS.get_current(connection, proposal_id=mine.proposal.proposal_id)
        assert (ended.proposal.state, ended.ended_by) == ("rejected", "planner")


# ===================================================================================
# AC3 - agent discard and its ordering
# ===================================================================================


def test_an_agent_discard_ends_the_draft_as_rejected_by_the_assistant(governed_postgres_engine, conv) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Discard the draft")
    discarded = turn.discard()
    executed = turn.finalize()
    assert executed.agent_run_status == "agent_completed"
    (row,) = _proposals(engine, conv)
    assert row[:4] == (first.proposal.proposal_id, "rejected", "assistant", 2)
    assert discarded.version_ordinal == 1


def test_discard_then_draft_in_one_turn_replaces_the_old_draft_with_a_fresh_v1(
    governed_postgres_engine, conv
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Throw it away and draft just 35 hours")
    turn.discard()
    second = turn.draft(_hours(35.0))
    turn.finalize(cite=second)
    assert (second.outcome, second.version_ordinal) == ("created", 1)
    rows = {row[0]: row for row in _proposals(engine, conv)}
    assert rows[first.proposal.proposal_id][1:3] == ("rejected", "assistant")
    assert rows[second.proposal.proposal_id][1:3] == ("active", None)
    assert _active(engine, conv) == [second.proposal.proposal_id]


def test_draft_then_discard_is_refused_and_the_draft_applies(governed_postgres_engine, conv) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Cap at 35, then discard")
    updated = turn.draft(_hours(35.0))
    with pytest.raises(DraftChangedThisTurnError):
        turn.discard()
    turn.finalize(cite=updated)
    (row,) = _proposals(engine, conv)
    assert row[:4] == (first.proposal.proposal_id, "active", None, 2)
    assert _ordinals(engine, first.proposal.proposal_id) == [1, 2]


def test_a_discard_with_no_working_draft_is_refused_at_tool_time(governed_postgres_engine, conv) -> None:
    turn = Turn(governed_postgres_engine, conv, "Discard the draft")
    with pytest.raises(NoWorkingDraftError):
        turn.discard()


# ===================================================================================
# AC2 - the four races; nothing is written, and the turn says so
# ===================================================================================


def _assert_lost(engine, conv, turn: Turn, before, executed) -> None:
    """The visible outcome, on unchanged proposal rows (AC2)."""
    assert _proposals(engine, conv) == before[0]
    assert _version_count(engine, conv) == before[1]
    assert executed.agent_run_status == "agent_failed"
    assert _run_status(engine, turn.claimed.agent_run_id) == "agent_failed"
    payload = executed.event.payload
    assert payload.activity_type == "terminal_outcome"
    assert payload.outcome == TerminalOutcomeV1(
        status="failed", reason="capability_error",
        detail="Your draft changed while I was working, so I didn't apply this change.",
        next_step="Ask again to apply it to the current draft.")
    assert (payload.outcome.detail, payload.outcome.next_step) == (
        DRAFT_CHANGED_DETAIL, DRAFT_CHANGED_NEXT_STEP)
    persisted = [e for e in _events(engine, turn.claimed.agent_run_id)
                 if e.event_type == "terminal_outcome"]
    assert len(persisted) == 1
    assert persisted[0].payload["outcome"]["reason"] == "capability_error"
    assert not any(e.event_type == "draft" for e in _events(engine, turn.claimed.agent_run_id))


def _snapshot(engine, conv):
    return _proposals(engine, conv), _version_count(engine, conv)


@pytest.mark.parametrize("action", ["update", "discard"])
def test_a_card_edit_mid_turn_makes_the_turn_lose(governed_postgres_engine, conv, action) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours(), _min_workers())
    turn = Turn(engine, conv, "Change it")
    if action == "update":
        pending = turn.draft(_hours(33.0))
    else:
        turn.discard()
    # The planner edits the card while the turn is in flight.
    _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(44.0)], 1)
    before = _snapshot(engine, conv)
    executed = turn.finalize(cite=pending) if action == "update" else turn.finalize()
    _assert_lost(engine, conv, turn, before, executed)


@pytest.mark.parametrize("action", ["update", "discard"])
def test_a_card_discard_mid_turn_makes_the_turn_lose(governed_postgres_engine, conv, action) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Change it")
    if action == "update":
        pending = turn.draft(_hours(33.0))
    else:
        turn.discard()
    _planner_reject(engine, conv, first.proposal.proposal_id, 1)
    before = _snapshot(engine, conv)
    executed = turn.finalize(cite=pending) if action == "update" else turn.finalize()
    _assert_lost(engine, conv, turn, before, executed)


@pytest.mark.parametrize("action", ["update", "discard"])
def test_a_promotion_mid_turn_makes_the_turn_lose(
    governed_postgres_engine, conv, site_ids, action  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Change it")
    if action == "update":
        pending = turn.draft(_hours(33.0))
    else:
        turn.discard()
    _promote(engine, conv, site_ids, first.proposal.proposal_id, first.proposal.proposal_version_id)
    assert _proposals(engine, conv)[0][1] == "applied"
    before = _snapshot(engine, conv)
    executed = turn.finalize(cite=pending) if action == "update" else turn.finalize()
    _assert_lost(engine, conv, turn, before, executed)


@pytest.mark.parametrize("kind", ["created", "updated"])
def test_a_second_turn_finalizing_first_makes_the_first_turn_lose(
    governed_postgres_engine, conv, kind
) -> None:
    engine = governed_postgres_engine
    if kind == "updated":
        _draft_and_finalize(engine, conv, _hours())
    slow = Turn(engine, conv, "Slow turn")
    pending = slow.draft(_min_workers(3))
    assert pending.outcome == kind
    # Another turn in the same conversation observes, drafts and finalizes first.
    fast = Turn(engine, conv, "Fast turn")
    fast_result = fast.draft(_hours(20.0))
    fast.finalize(cite=fast_result)
    before = _snapshot(engine, conv)
    executed = slow.finalize(cite=pending)
    _assert_lost(engine, conv, slow, before, executed)


def test_a_lost_turn_can_be_repeated_against_the_current_draft(governed_postgres_engine, conv) -> None:
    """The terminal copy's promise: 'Ask again to apply it to the current draft.'"""
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    turn = Turn(engine, conv, "Change it")
    pending = turn.draft(_hours(33.0))
    _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(44.0)], 1)
    turn.finalize(cite=pending)
    again = Turn(engine, conv, "Change it again")
    retried = again.draft(_hours(33.0))
    again.finalize(cite=retried)
    assert (retried.outcome, retried.version_ordinal) == ("updated", 3)
    assert _active(engine, conv) == [first.proposal.proposal_id]


def test_the_conversation_lock_serializes_two_finalizes_and_never_reaches_the_index(
    governed_postgres_engine, conv
) -> None:
    """Two connections: turn A holds its finalize transaction open; turn B's
    finalize BLOCKS on the conversation lock, then loses with the terminal outcome
    (never an IntegrityError). Mutation: drop `lock_conversation` from the guard
    and B's create hits the unique index instead."""
    engine = governed_postgres_engine
    a, b = Turn(engine, conv, "Turn A"), Turn(engine, conv, "Turn B")
    result_a, result_b = a.draft(_hours(30.0)), b.draft(_hours(31.0))
    assert result_a.outcome == result_b.outcome == "created"

    a_holds, release_a, b_returned = threading.Event(), threading.Event(), threading.Event()
    outcomes: dict[str, object] = {}

    def finalize_a() -> None:
        try:
            with site_context(engine, conv["site"]) as connection:
                outcomes["a"] = finalize_agent_run(
                    CONVERSATIONS, PROPOSALS, connection, claimed=a.claimed,
                    status="agent_completed",
                    payload=activity_payload(
                        resolve_draft_citation(
                            AgentRunOutcomeV1(status="completed",
                                              draft=DraftProposalV1(draft_id=result_a.result_id)),
                            {result_a.result_id: result_a}), a.deps),
                    request_id=uuid4())
                a_holds.set()
                assert release_a.wait(timeout=30)  # the transaction stays open here
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            outcomes["a_error"] = exc
            a_holds.set()

    def finalize_b() -> None:
        try:
            outcomes["b"] = b.finalize(cite=result_b)
        except BaseException as exc:  # noqa: BLE001
            outcomes["b_error"] = exc
        finally:
            b_returned.set()

    thread_a = threading.Thread(target=finalize_a)
    thread_a.start()
    assert a_holds.wait(timeout=30)
    thread_b = threading.Thread(target=finalize_b)
    thread_b.start()
    # B is blocked on the conversation lock while A's transaction is open.
    assert not b_returned.wait(timeout=1.5), "B finalized while A held the lock"
    release_a.set()
    thread_a.join(timeout=30)
    thread_b.join(timeout=30)

    assert "a_error" not in outcomes and "b_error" not in outcomes, outcomes
    assert outcomes["a"].event.payload.activity_type == "draft"
    assert outcomes["b"].agent_run_status == "agent_failed"
    assert _run_status(engine, b.claimed.agent_run_id) == "agent_failed"
    assert _run_status(engine, a.claimed.agent_run_id) == "agent_completed"
    assert outcomes["b"].event.payload.outcome.reason == "capability_error"
    assert _active(engine, conv) == [result_a.proposal.proposal_id]
    assert len(_proposals(engine, conv)) == 1


# ===================================================================================
# AC4 - promotion marks the draft applied, exactly once, at the pinned version
# ===================================================================================


def test_a_promotion_marks_the_draft_applied_at_the_pinned_version(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    _promote(engine, conv, site_ids, first.proposal.proposal_id, first.proposal.proposal_version_id)
    with engine.connect() as connection:
        row = connection.execute(select(proposal).where(
            proposal.c.id == first.proposal.proposal_id)).one()
    assert (row.state, row.ended_by, row.applied_version_id) == (
        "applied", "system", first.proposal.proposal_version_id)
    assert row.resource_version == 2


def test_an_already_rejected_draft_stays_rejected_through_a_promotion(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    """Mutation: drop `AND state = 'active'` from `mark_applied` and this reddens."""
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    _planner_reject(engine, conv, first.proposal.proposal_id, 1)
    _promote(engine, conv, site_ids, first.proposal.proposal_id, first.proposal.proposal_version_id)
    (row,) = _proposals(engine, conv)
    assert row[:4] == (first.proposal.proposal_id, "rejected", "planner", 2)
    with engine.connect() as connection:
        assert connection.execute(select(proposal.c.applied_version_id).where(
            proposal.c.id == first.proposal.proposal_id)).scalar_one() is None


def test_mark_applied_reports_zero_rows_for_an_ended_or_unpinned_draft(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    ids = _seed_candidate_run(
        engine, site_id=conv["site"], actor_id=conv["actor"],
        reuse={"scenario": conv["scenario"], "scenario_version": conv["version"],
               "conversation": conv["conversation"], "proposal": first.proposal.proposal_id,
               "proposal_version": first.proposal.proposal_version_id})
    with site_context(engine, conv["site"]) as connection:
        assert PROPOSALS.mark_applied(
            connection, site_id=conv["site"], schedule_version_id=uuid4()) is False
        assert PROPOSALS.mark_applied(
            connection, site_id=conv["site"], schedule_version_id=ids["candidate"]) is True
    with site_context(engine, conv["site"]) as connection:
        assert PROPOSALS.mark_applied(
            connection, site_id=conv["site"], schedule_version_id=ids["candidate"]) is False


def test_a_draft_promoted_at_v2_then_edited_to_v3_reads_applied_at_v2(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _draft_and_finalize(engine, conv, _hours(40.0))
    turn, v2, _ = _draft_and_finalize(engine, conv, _hours(40.0), _min_workers(2))
    assert v2.version_ordinal == 2
    ids = _seed_candidate_run(
        engine, site_id=conv["site"], actor_id=conv["actor"],
        reuse={"scenario": conv["scenario"], "scenario_version": conv["version"],
               "conversation": conv["conversation"], "proposal": v2.proposal.proposal_id,
               "proposal_version": v2.proposal.proposal_version_id})
    # The planner edits the card to v3 AFTER the run pinned v2, before approval.
    revised = _planner_revise(engine, conv, v2.proposal.proposal_id, [_hours(50.0)], 2)
    assert revised.version_ordinal == 3
    binding = _request(engine, ids, site_ids)
    with site_context(engine, conv["site"]) as connection:
        decide_approval(
            connection,
            command=DecideApprovalCommandV1(
                site_id=conv["site"], actor_id=conv["actor"], approval_id=binding.approval_id,
                decision="approve", expected_resource_version=binding.resource_version,
                request_id=uuid4()),
            **_decision_dependencies())
    with site_context(engine, conv["site"]) as connection:
        view = get_proposal(
            PROPOSALS, _Projection(conv), connection, proposal_id=v2.proposal.proposal_id)
    assert (view.proposal.state, view.ended_by) == ("applied", "system")
    assert (view.version_ordinal, view.applied_version_ordinal) == (3, 2)
    with site_context(engine, conv["site"]) as connection:
        record = PROPOSALS.get_current(connection, proposal_id=v2.proposal.proposal_id)
        assert record.applied_version_id == v2.proposal.proposal_version_id
        ordinal, pinned = PROPOSALS.get_version(
            connection, proposal_version_id=record.applied_version_id)
        assert ordinal == 2 and [c.kind for c in pinned.constraints] == [
            "set_max_hours", "set_min_workers_per_task"]
    del turn


# --- ended drafts refuse every planner command --------------------------------------


def test_revise_and_reject_on_an_applied_draft_answer_applied_even_when_stale_or_out_of_date(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    _promote(engine, conv, site_ids, first.proposal.proposal_id, first.proposal.proposal_version_id)
    # The resource version moved (2) and the request still carries 1: the ended
    # state must win over the resource-version comparison (C5).
    with pytest.raises(AppliedProposalError):
        _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(30.0)], 1)
    with pytest.raises(AppliedProposalError):
        _planner_reject(engine, conv, first.proposal.proposal_id, 1)
    # ...and a stale scenario does not hide it either.
    stale = _Projection(conv)
    stale_version = uuid4()
    stale.get_overview = lambda c, s, _orig=stale.get_overview: replace(
        _orig(c, s), scenario_version_id=stale_version)
    with pytest.raises(AppliedProposalError):
        with site_context(engine, conv["site"]) as connection:
            revise_proposal(
                PROPOSALS, stale, connection, proposal_id=first.proposal.proposal_id,
                site_id=conv["site"], actor_id=conv["actor"], constraints=(_hours(30.0),),
                expected_resource_version=2, idempotency_key=uuid4().hex[:30])


def test_a_planner_discard_is_rejected_and_a_rejected_draft_refuses_revise_and_reject(
    governed_postgres_engine, conv
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    rejected = _planner_reject(engine, conv, first.proposal.proposal_id, 1)
    assert (rejected.proposal.state, rejected.ended_by) == ("rejected", "planner")
    with pytest.raises(RejectedProposalError):
        _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(30.0)], 2)
    with pytest.raises(RejectedProposalError):
        _planner_reject(engine, conv, first.proposal.proposal_id, 2)


def test_a_replay_after_the_draft_became_applied_returns_the_stored_original(
    governed_postgres_engine, conv, site_ids  # noqa: F811
) -> None:
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    key = uuid4().hex[:30]
    original = _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(31.0)], 1, key)
    _promote(engine, conv, site_ids, first.proposal.proposal_id, original.proposal.proposal_version_id)
    replay = _planner_revise(engine, conv, first.proposal.proposal_id, [_hours(31.0)], 1, key)
    assert replay.proposal.proposal_version_id == original.proposal.proposal_version_id
    assert (replay.version_ordinal, replay.ended_by) == (original.version_ordinal, None)


def test_a_replayed_discard_keeps_the_stored_lifecycle_fields(governed_postgres_engine, conv) -> None:
    """A replay answers "what did my command do": the stored `ended_by` comes
    back, not a default. Mutation: drop the lifecycle fields from
    `_replay_or_conflict` => this reddens (code review of story-5.11)."""
    engine = governed_postgres_engine
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    key = uuid4().hex[:30]
    original = _planner_reject(engine, conv, first.proposal.proposal_id, 1, key)
    replay = _planner_reject(engine, conv, first.proposal.proposal_id, 1, key)
    assert original.ended_by == "planner"
    assert (replay.proposal.state, replay.ended_by, replay.version_ordinal) == (
        "rejected", "planner", original.version_ordinal)


def _route_headers(settings, key=None):
    return _governance_headers(settings, key=key or uuid4().hex[:30])


@pytest.mark.parametrize(
    ("ended", "code"), [("rejected", "rejected_proposal"), ("applied", "applied_proposal")]
)
def test_every_ended_draft_command_answers_409_with_the_ended_code_through_the_routes(
    governed_postgres_engine, conv, site_ids, decision_http_client, ended, code  # noqa: F811
) -> None:
    from api.routers.proposals import get_projection_reader

    engine = governed_postgres_engine
    client, settings = decision_http_client
    # The app and dependency object the CLIENT is actually serving: another suite
    # may reload `api.main` / `api.deps`, so a freshly imported name can point at a
    # different object than the one this client routes through.
    app = client.app
    # The routes read the proposal's scenario through the real projection reader; the
    # seeded scenario carries no fixture rows, so resolve it with the in-memory one.
    app.dependency_overrides[get_projection_reader] = lambda: _Projection(conv)
    _, first, _ = _draft_and_finalize(engine, conv, _hours())
    pid = str(first.proposal.proposal_id)
    if ended == "rejected":
        _planner_reject(engine, conv, first.proposal.proposal_id, 1)
        stale_version = 1  # the run request carries a now-old resource version
    else:
        _promote(engine, conv, site_ids, first.proposal.proposal_id,
                 first.proposal.proposal_version_id)
        stale_version = 1  # `mark_applied` bumped it to 2: C5 says applied still wins

    constraint = {"kind": "set_max_hours", "group": "workers", "record_id": "worker-1",
                  "max_hours": 30.0}
    revise = client.post(
        f"/api/v1/proposals/{pid}/revisions", headers=_route_headers(settings),
        json={"constraints": [constraint], "expected_resource_version": stale_version})
    reject = client.post(
        f"/api/v1/proposals/{pid}/rejection", headers=_route_headers(settings),
        json={"expected_resource_version": stale_version})
    run = client.post(
        "/api/v1/schedule-runs", headers=_route_headers(settings),
        json={"proposal_id": pid, "expected_resource_version": stale_version})
    for response in (revise, reject, run):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == code, response.text

    # Decision 11: the read model reports the lifecycle, nothing stored twice.
    read = client.get(f"/api/v1/proposals/{pid}", headers=_route_headers(settings))
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["state"] == ended and body["ended_by"] == ("planner" if ended == "rejected" else "system")
    assert body["version_ordinal"] == 1
    assert body["applied_version_ordinal"] == (None if ended == "rejected" else 1)
