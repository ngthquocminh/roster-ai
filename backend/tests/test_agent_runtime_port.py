"""The AgentRuntime port is usable without the framework existing.

This is the executable form of AC2's first clause. Every test here drives the
port through a fake that imports nothing from `pydantic_ai` — if the port's
contracts had been shaped by the framework, this file could not be written.
"""
from __future__ import annotations

import pytest
from application.contracts.agent_runtime import (
    SCHEMA_VERSION,
    AgentApprovalDecisionV1,
    AgentApprovalPendingV1,
    AgentBudgetV1,
    AgentMessageV1,
    AgentPartV1,
    AgentRunOutcomeV1,
    AgentToolCallProposalV1,
    AgentTurnRequestV1,
    AgentTurnV1,
)
from application.ports.agent_runtime import AgentRuntime, AgentRuntimeError


class FakeAgentRuntime:
    """A complete AgentRuntime with no framework anywhere in sight."""

    name = "fake"

    def __init__(self, *, suspend: bool = False, fail: bool = False) -> None:
        self._suspend = suspend
        self._fail = fail
        self.seen: list[AgentTurnRequestV1] = []

    def run_turn(self, request: AgentTurnRequestV1) -> AgentRunOutcomeV1:
        self.seen.append(request)

        if self._fail:
            raise AgentRuntimeError("fake runtime failure")

        # Budgets come off the request, never from anywhere else.
        if request.budget.request_limit == 0:
            return AgentRunOutcomeV1(
                status="failed", failure_reason="budget_exhausted"
            )
        if request.budget.deadline_seconds == 0:
            return AgentRunOutcomeV1(status="timed_out")

        if self._suspend and not request.approvals:
            return AgentRunOutcomeV1(
                status="suspended",
                approval=AgentApprovalPendingV1(
                    pending_calls=(
                        AgentToolCallProposalV1(
                            tool_call_id="call-1",
                            tool_name="publish_roster",
                            tool_args_json='{"week": 34}',
                        ),
                    ),
                    turn=request.history,
                ),
            )

        if request.approvals:
            decision = request.approvals[0]
            text = (
                "published"
                if decision.approved
                else f"denied: {decision.denial_reason}"
            )
            return AgentRunOutcomeV1(status="completed", output_text=text)

        return AgentRunOutcomeV1(
            status="completed",
            output_text="ok",
            turn=AgentTurnV1(
                messages=(
                    AgentMessageV1(
                        role="assistant",
                        parts=(AgentPartV1(kind="text", text="ok"),),
                    ),
                )
            ),
        )


def test_fake_satisfies_the_port_protocol() -> None:
    runtime: AgentRuntime = FakeAgentRuntime()
    assert runtime.name == "fake"
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt="hello"))
    assert outcome.status == "completed"
    assert outcome.output_text == "ok"
    assert outcome.turn.visible_text() == "ok"


def test_every_contract_carries_schema_version() -> None:
    """Spine's Normative contract minimums: every contract carries schema_version."""
    for contract in (
        AgentBudgetV1(),
        AgentPartV1(),
        AgentMessageV1(),
        AgentTurnV1(),
        AgentToolCallProposalV1(),
        AgentApprovalPendingV1(),
        AgentApprovalDecisionV1(),
        AgentTurnRequestV1(),
        AgentRunOutcomeV1(),
    ):
        assert contract.schema_version == SCHEMA_VERSION


def test_suspension_and_resume_travel_as_owned_types() -> None:
    runtime = FakeAgentRuntime(suspend=True)

    suspended = runtime.run_turn(AgentTurnRequestV1(prompt="publish week 34"))
    assert suspended.status == "suspended"
    assert suspended.approval is not None
    pending = suspended.approval.pending_calls[0]
    assert pending.tool_name == "publish_roster"

    approved = runtime.run_turn(
        AgentTurnRequestV1(
            history=suspended.approval.turn,
            approvals=(
                AgentApprovalDecisionV1(
                    tool_call_id=pending.tool_call_id, approved=True
                ),
            ),
        )
    )
    assert approved.status == "completed"
    assert approved.output_text == "published"

    denied = runtime.run_turn(
        AgentTurnRequestV1(
            history=suspended.approval.turn,
            approvals=(
                AgentApprovalDecisionV1(
                    tool_call_id=pending.tool_call_id,
                    approved=False,
                    denial_reason="planner said no",
                ),
            ),
        )
    )
    assert denied.status == "completed"
    assert denied.output_text == "denied: planner said no"


def test_budget_exhaustion_and_timeout_are_distinct_outcomes() -> None:
    """AD-7: wall-time -> timed_out; other exhaustion -> failed + budget_exhausted."""
    runtime = FakeAgentRuntime()

    budget = runtime.run_turn(
        AgentTurnRequestV1(prompt="x", budget=AgentBudgetV1(request_limit=0))
    )
    assert budget.status == "failed"
    assert budget.failure_reason == "budget_exhausted"

    timeout = runtime.run_turn(
        AgentTurnRequestV1(prompt="x", budget=AgentBudgetV1(deadline_seconds=0))
    )
    assert timeout.status == "timed_out"
    assert timeout.failure_reason is None
    assert timeout.status != budget.status


def test_owned_error_type_is_not_the_llm_seam_error() -> None:
    """Two seams, two error types. Catching one must not catch the other."""
    from llm.base import LLMProviderError

    with pytest.raises(AgentRuntimeError):
        FakeAgentRuntime(fail=True).run_turn(AgentTurnRequestV1(prompt="x"))

    assert not issubclass(AgentRuntimeError, LLMProviderError)
    assert not issubclass(LLMProviderError, AgentRuntimeError)


def test_turn_request_exposes_no_authority_input() -> None:
    """AD-2/AD-15: the port takes trusted server-owned inputs only. A capability
    name, permission, or authority flag must not be settable on the request.
    """
    fields = set(AgentTurnRequestV1.__dataclass_fields__)
    for forbidden in (
        "capability_name",
        "capability",
        "permission",
        "permissions",
        "scope",
        "authority",
        "is_authorized",
        "allow",
        "role",
    ):
        assert forbidden not in fields
    assert fields == {
        "schema_version",
        "prompt",
        "history",
        "budget",
        "approvals",
    }
