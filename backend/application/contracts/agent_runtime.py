"""ShiftMind-owned contracts for the agent runtime seam.

These are the ONLY types allowed to cross the `AgentRuntime` port. Nothing here
imports `pydantic_ai`, and nothing here is shaped by it — AD-19: framework
"messages, deferred calls, tool objects, checkpoints, and framework event types
never become domain, persistence, browser, or audit contracts."

The distinction that matters: PydanticAI ships `ModelMessagesTypeAdapter` and
`to_jsonable_python`, and its docs teach `to_jsonable_python(result.all_messages())`
as the way to persist a conversation. That JSON carries PydanticAI's own
`part_kind` discriminator (measured — see docs/AGENT-RUNTIME-DECISION.md), so
persisting it makes the framework a persisted product contract. These dataclasses
are the durable shape instead; `backend/agent/` translates at the edge.

Naming: mirrors the existing `V1` convention (`EvidenceRefV1`,
`ScenarioProjectionV1`). Every contract carries `schema_version` per the spine's
*Normative contract minimums*.

Deliberately NOT defined here: `ActivityItemV1`, `PersistedEventV1`,
`CapabilityManifestV1`, and `JobLeaseV1`. Those are cross-epic contracts owned by
Stories 2.3, 2.4, 2.6, and Epic 3 respectively (AD-20). Defining a partial version
here would force a rename later, or worse, be quietly extended into a contract
this story never validated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from application.contracts.grounding import GroundedAnswerV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.agent_status import AgentRunStatusV1
from application.contracts.proposal import DraftProposalV1, ProposalV1
from application.contracts.telemetry import AgentUsageV1, BudgetOutcomeV1

SCHEMA_VERSION = "1"

# What an agent turn can be doing when control returns to the application.
#
# `timed_out` vs `failed`+`budget_exhausted` is AD-7's required distinction. It is
# a real distinction at the adapter, not a cosmetic one: PydanticAI's UsageLimits
# carries no deadline field, so wall-clock expiry and budget exhaustion arrive as
# two different exception types and the adapter maps them by type, never by
# string-matching an error message.
AgentFailureReasonV1 = Literal[
    "budget_exhausted",   # token / request / tool-call ceiling hit
    "provider_error",     # provider or transport failure
    "invalid_output",     # the model produced unusable output
    "cancelled",          # cancelled by something other than the deadline
]

# A governed capability may also fail with one of the error codes declared in
# its granted CapabilityManifestV1. Those codes are open at the type level --
# each module declares its own vocabulary -- so this alias is deliberately `str`
# and carries NO guarantee by itself.
#
# What makes the wider type safe is a runtime check, not the annotation:
# `PydanticAIAgentRuntime.run_turn` rejects any capability failure whose code is
# absent from the granted manifests' `errors`, so every value that actually
# reaches `failure_reason` is either an AgentFailureReasonV1 member or a
# manifest-declared code. The invariant is asserted per installed module in
# tests/test_capability_conformance.py.
CapabilityFailureReasonV1 = str

# Owned message roles. Not PydanticAI's `kind`/`part_kind` vocabulary — this is a
# whitelist of what ShiftMind chooses to record.
AgentMessageRoleV1 = Literal["user", "system", "assistant", "tool_result"]

AgentPartKindV1 = Literal["text", "tool_call", "tool_result"]


@dataclass(frozen=True)
class AgentBudgetV1:
    """Application-set execution bounds. AD-7: budgets come from application
    configuration, never from the model. The adapter reads these off the request;
    it does not read env vars of its own.
    """

    schema_version: str = SCHEMA_VERSION
    request_limit: int | None = None
    tool_calls_limit: int | None = None
    total_tokens_limit: int | None = None
    # Wall-clock deadline. The framework supplies only a cancellation mechanism;
    # owning the deadline itself is the adapter's obligation (recorded in
    # docs/AGENT-RUNTIME-DECISION.md).
    deadline_seconds: float | None = None


@dataclass(frozen=True)
class AgentPartV1:
    """One unit of a recorded turn. Hidden reasoning never becomes one of these:
    there is no `thinking` kind, by construction.
    """

    schema_version: str = SCHEMA_VERSION
    kind: AgentPartKindV1 = "text"
    text: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    # Tool arguments as a JSON string, because the owned record must be durable
    # without depending on the framework's argument object.
    tool_args_json: str | None = None


@dataclass(frozen=True)
class AgentMessageV1:
    schema_version: str = SCHEMA_VERSION
    role: AgentMessageRoleV1 = "user"
    parts: tuple[AgentPartV1, ...] = ()


@dataclass(frozen=True)
class AgentTurnV1:
    """The durable, owned transcript of one or more agent turns.

    This — not `to_jsonable_python(result.all_messages())` — is what a caller may
    persist and rehydrate from.
    """

    schema_version: str = SCHEMA_VERSION
    messages: tuple[AgentMessageV1, ...] = ()

    def visible_text(self) -> str:
        """Planner-visible assistant text only."""
        return "\n".join(
            part.text or ""
            for message in self.messages
            if message.role == "assistant"
            for part in message.parts
            if part.kind == "text" and part.text
        )


@dataclass(frozen=True)
class AgentToolCallProposalV1:
    """A typed tool call the model proposed and that the application has not yet
    authorized. The capability name here is model-supplied and therefore
    UNTRUSTED (AD-2, AD-15): the application resolves it against its own registry
    before anything executes. It is never itself an authority decision.
    """

    schema_version: str = SCHEMA_VERSION
    tool_call_id: str = ""
    tool_name: str = ""
    tool_args_json: str = "{}"


@dataclass(frozen=True)
class AgentToolResultV1:
    schema_version: str = SCHEMA_VERSION
    tool_call_id: str = ""
    tool_name: str = ""
    content: str = ""


@dataclass(frozen=True)
class AgentApprovalPendingV1:
    """Suspension marker: the run stopped because a tool needs a human decision.

    ShiftMind's approval is a persisted one-time state machine (AD-10), so the
    suspension is returned to the application rather than resolved by an in-process
    callback. `turn` is the resumable history in owned form.
    """

    schema_version: str = SCHEMA_VERSION
    pending_calls: tuple[AgentToolCallProposalV1, ...] = ()
    turn: AgentTurnV1 = field(default_factory=AgentTurnV1)


@dataclass(frozen=True)
class AgentApprovalDecisionV1:
    """The application's answer to one pending call. Server-owned: it is supplied
    by the application from a persisted approval record, never by model output.
    """

    schema_version: str = SCHEMA_VERSION
    tool_call_id: str = ""
    approved: bool = False
    denial_reason: str | None = None


@dataclass(frozen=True)
class AgentTurnRequestV1:
    """Trusted, server-owned inputs for one agent turn.

    There is deliberately no field here for a model-supplied capability name, a
    browser-supplied value, or an authority flag (AD-2, AD-15). `prompt` is
    untrusted *content*, which is a different thing from an authority input: it
    is passed to the model and never consulted to decide what is permitted.
    """

    schema_version: str = SCHEMA_VERSION
    prompt: str | None = None
    # Prior transcript in OWNED form. The adapter rehydrates framework messages
    # from this; the caller never hands the adapter framework objects.
    history: AgentTurnV1 = field(default_factory=AgentTurnV1)
    budget: AgentBudgetV1 = field(default_factory=AgentBudgetV1)
    # Approval decisions resolving a previous suspension.
    approvals: tuple[AgentApprovalDecisionV1, ...] = ()


# Mid-file only to keep the module's reading order (vocabularies first, then the
# DTOs that use them). There is NO import cycle to break: `AgentRunStatusV1` was
# extracted to `contracts/agent_status.py`, which both this module and
# `dialogue` import at the top. An earlier comment here claimed the cycle as the
# reason, which stopped being true in the same change that removed it.
from application.contracts.dialogue import ClarificationV1, RefusalV1, ResolvedClarificationV1


@dataclass(frozen=True)
class AgentRunOutcomeV1:
    """The single result type crossing back over the port.

    `summary` is an application-owned condensation, `turn` is the owned durable
    transcript, and neither may carry provider hidden reasoning (AD-15).
    """

    schema_version: str = SCHEMA_VERSION
    status: AgentRunStatusV1 = "completed"
    failure_reason: AgentFailureReasonV1 | CapabilityFailureReasonV1 | None = None
    # WHICH LAYER produced `failure_reason`. Required because
    # `CapabilityFailureReasonV1` is an open `str`: a module may declare a code
    # spelled exactly like an `AgentFailureReasonV1` member, and `demonstration`
    # already declares `budget_exhausted`. Without this tag the request path had
    # to compare strings, and a capability hitting its own internal limit was
    # reported to the planner as "The configured agent budget was exhausted".
    # Set at the raise site; `None` only for outcomes that did not fail.
    failure_source: Literal["agent", "capability"] | None = None
    # Planner-visible final content. None unless status == "completed".
    output_text: str | None = None
    # These fields deliberately sit on opposite sides of the trust boundary.
    # Model-side `answer`, `clarification`, and `refusal` are UNTRUSTED and set
    # in `backend/agent/`. Resolved persisted forms are written by the use case.
    #
    # Two grounding fields exist, though Task 5 declared only `answer`. They sit
    # on opposite sides of the trust boundary and collapsing them would erase it:
    #
    #   `answer`            UNTRUSTED. The model's structured output exactly as
    #                       the adapter received it. Set in `backend/agent/`.
    #   `grounded_response` TRUSTED. What the gate produced from that answer --
    #                       values and locators come only from calculator
    #                       results. Set by `use_cases/execute_turn.py`, never
    #                       by the adapter, and it is what gets persisted and
    #                       rendered.
    #
    # The second was added during Phase B without being recorded against Task 5,
    # which declared the adapter's one field; it is the USE CASE's field, which
    # is why it fell outside that task's wording rather than contradicting it.
    answer: GroundedAnswerV1 | None = None
    grounded_response: GroundedResponseV1 | None = None
    clarification: ClarificationV1 | None = None
    resolved_clarification: ResolvedClarificationV1 | None = None
    refusal: RefusalV1 | None = None
    # Drafts mirror the grounding and clarification trust-boundary pairs:
    # `draft` is the UNTRUSTED model citation set in `backend/agent/`;
    # `resolved_draft` is the TRUSTED proposal bound by the use case from this
    # turn's captured capability results. Only the latter may be persisted.
    draft: DraftProposalV1 | None = None
    resolved_draft: ProposalV1 | None = None
    turn: AgentTurnV1 = field(default_factory=AgentTurnV1)
    summary: str | None = None
    approval: AgentApprovalPendingV1 | None = None
    tool_results: tuple[AgentToolResultV1, ...] = ()
    usage: AgentUsageV1 | None = None
    budget_outcome: BudgetOutcomeV1 | None = None
