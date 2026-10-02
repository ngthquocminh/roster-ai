"""Story 5.11 Task 5: the finalize guard with recording doubles (Decision 8).

The real-PostgreSQL race proofs live in `test_draft_lifecycle_postgres.py`; these
prove the guard's own logic -- ordering, the applies-only-if table, and the
literal failure -- without a database.
"""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from application.contracts.dialogue import TerminalOutcomeV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.proposal import AgentDraftDiscardV1, AgentDraftWriteV1, ProposalV1
from application.ports.conversation import ClaimedAgentRunV1
from application.ports.proposal import ProposalRecordV1
from application.use_cases.finalize_agent_run import (
    DRAFT_CHANGED_DETAIL,
    DRAFT_CHANGED_NEXT_STEP,
    finalize_agent_run,
)

CONNECTION = object()
WORKING_ID = UUID(int=900)
CLAIMED = ClaimedAgentRunV1(
    agent_run_id=UUID(int=1), conversation_id=UUID(int=2), scenario_id=UUID(int=3),
    scenario_version_id=UUID(int=4), site_id=UUID(int=5), actor_id=UUID(int=6),
    membership_id=UUID(int=7), prompt="Draft",
)


def _proposal(proposal_id=UUID(int=8), resource_version=1) -> ProposalV1:
    return ProposalV1(
        proposal_id=proposal_id, proposal_version_id=UUID(int=9),
        scenario_id=CLAIMED.scenario_id, scenario_version_id=CLAIMED.scenario_version_id,
        consequence_summary="One constraint.", canonical_hash="a" * 64,
        resource_version=resource_version,
    )


class Log:
    def __init__(self) -> None:
        self.calls: list[tuple] = []


class Conversations:
    def __init__(self, log: Log) -> None:
        self.log = log

    def lock_conversation(self, connection, **kwargs) -> None:
        assert connection is CONNECTION
        self.log.calls.append(("lock", kwargs["conversation_id"]))

    def finish_agent_run(self, connection, **kwargs):
        assert connection is CONNECTION
        self.log.calls.append(("finish", kwargs["status"], kwargs["payload"]))
        return "executed"


class Proposals:
    def __init__(self, log: Log, working: ProposalRecordV1 | None) -> None:
        self.log = log
        self.working = working

    def get_working(self, connection, **kwargs):
        assert connection is CONNECTION
        self.log.calls.append(("get_working", kwargs["for_update"]))
        return self.working

    def create_draft(self, connection, **kwargs):
        self.log.calls.append(("create_draft", kwargs["proposal"].proposal_id))

    def append_agent_version(self, connection, **kwargs):
        self.log.calls.append(("append", kwargs["proposal"].proposal_id, kwargs["version_ordinal"]))

    def end_by_assistant(self, connection, **kwargs):
        self.log.calls.append(("end_by_assistant", kwargs["proposal_id"], kwargs["resource_version"]))


def _record(resource_version: int = 4, proposal_id: UUID = WORKING_ID) -> ProposalRecordV1:
    return ProposalRecordV1(
        proposal=_proposal(proposal_id, resource_version), version_ordinal=3,
        created_by_actor_id=CLAIMED.actor_id,
    )


def _run(working, *, payload, discard=None, status="agent_completed"):
    log = Log()
    result = finalize_agent_run(
        Conversations(log), Proposals(log, working), CONNECTION,
        claimed=CLAIMED, status=status, payload=payload, discard=discard,
        request_id=UUID(int=10),
    )
    return result, log.calls


def _names(calls) -> list[str]:
    return [call[0] for call in calls]


CREATED = AgentDraftWriteV1(_proposal(UUID(int=20)), "created", 1)
UPDATED = AgentDraftWriteV1(_proposal(WORKING_ID, 5), "updated", 4, WORKING_ID, 4)
DISCARD = AgentDraftDiscardV1(WORKING_ID, 4, 3)


def test_a_turn_with_no_draft_and_no_discard_takes_no_lock_and_reads_no_proposal() -> None:
    answer = GroundedResponseV1(scenario_version_id=CLAIMED.scenario_version_id, segments=())
    result, calls = _run(None, payload=answer)
    assert result == "executed"
    assert _names(calls) == ["finish"]
    # A terminal outcome payload takes the same unguarded path.
    terminal = TerminalOutcomeV1(status="failed", reason="invalid_output", detail="x")
    assert _names(_run(None, payload=terminal)[1]) == ["finish"]


def test_the_guard_orders_lock_then_working_read_then_finish_then_the_write() -> None:
    _, calls = _run(None, payload=CREATED)
    assert _names(calls) == ["lock", "get_working", "finish", "create_draft"]
    assert calls[1] == ("get_working", True)  # FOR UPDATE


def test_created_applies_only_when_there_is_no_working_draft() -> None:
    _, calls = _run(None, payload=CREATED)
    assert _names(calls)[-1] == "create_draft"
    _, refused = _run(_record(), payload=CREATED)
    assert _names(refused) == ["lock", "get_working", "finish"]


def test_updated_applies_only_if_the_same_draft_at_the_same_resource_version() -> None:
    _, calls = _run(_record(4), payload=UPDATED)
    assert calls[-1] == ("append", WORKING_ID, 4)
    # Mutation "guard skips the resource_version comparison" reddens this row.
    for working in (_record(5), _record(4, UUID(int=901)), None):
        _, refused = _run(working, payload=UPDATED)
        assert "append" not in _names(refused)
        assert refused[-1][1] == "agent_failed"


def test_a_discard_applies_only_to_the_observed_draft_at_the_observed_version() -> None:
    answer = GroundedResponseV1(scenario_version_id=CLAIMED.scenario_version_id, segments=())
    _, calls = _run(_record(4), payload=answer, discard=DISCARD)
    assert _names(calls) == ["lock", "get_working", "finish", "end_by_assistant"]
    assert calls[-1] == ("end_by_assistant", WORKING_ID, 5)  # observed + 1
    for working in (_record(5), None):
        _, refused = _run(working, payload=answer, discard=DISCARD)
        assert "end_by_assistant" not in _names(refused)
        assert refused[-1][1] == "agent_failed"


def test_discard_then_created_ends_the_old_draft_before_creating_the_new_one() -> None:
    _, calls = _run(_record(4), payload=CREATED, discard=DISCARD)
    assert _names(calls) == ["lock", "get_working", "finish", "end_by_assistant", "create_draft"]
    # ...and the pair is judged by the discard's observation, not "no working draft".
    _, refused = _run(_record(5), payload=CREATED, discard=DISCARD)
    assert _names(refused) == ["lock", "get_working", "finish"]


def test_updated_together_with_a_discard_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="both update and discard"):
        _run(_record(4), payload=UPDATED, discard=DISCARD)


def test_a_lost_race_finishes_agent_failed_with_the_exact_literal_terminal_outcome() -> None:
    result, calls = _run(_record(9), payload=UPDATED)
    assert result == "executed"
    assert _names(calls) == ["lock", "get_working", "finish"]
    _, status, payload = calls[-1]
    assert status == "agent_failed"
    assert payload == TerminalOutcomeV1(
        status="failed",
        reason="capability_error",
        detail="Your draft changed while I was working, so I didn't apply this change.",
        next_step="Ask again to apply it to the current draft.",
    )
    assert (DRAFT_CHANGED_DETAIL, DRAFT_CHANGED_NEXT_STEP) == (payload.detail, payload.next_step)


def test_a_draft_without_durable_identifiers_is_refused_before_any_lock() -> None:
    bad = AgentDraftWriteV1(replace(_proposal(), proposal_id=None), "created", 1)
    log = Log()
    with pytest.raises(ValueError, match="durable identifiers"):
        finalize_agent_run(
            Conversations(log), Proposals(log, None), CONNECTION,
            claimed=CLAIMED, status="agent_completed", payload=bad, request_id=UUID(int=10),
        )
    assert log.calls == []
