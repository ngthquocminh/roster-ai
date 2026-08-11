"""PydanticAI adapter for the owned `AgentRuntime` port.

Owned request -> framework call -> owned outcome. The seven capabilities the
Story 2.1 spike proved possible become real behavior here; the spike showed they
*can* be done, this module makes them ours.

Nothing framework-shaped leaves this module: every exception is re-raised as
`AgentRuntimeError` with its cause preserved, and every message is translated
through `agent/translate.py` before it is returned.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    AgentRunError,
    ApprovalRequired,
    CancellationToken,
    DeferredToolRequests,
    DeferredToolResults,
    InstrumentationSettings,
    ModelHTTPError,
    RunCancelled,
    ToolDenied,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
    RunContext,
)
from pydantic_ai.capabilities import Instrumentation

from agent.translate import summarize, to_framework_messages, to_owned_turn
from application.contracts.agent_runtime import (
    AgentApprovalPendingV1,
    AgentBudgetV1,
    AgentRunOutcomeV1,
    AgentToolCallProposalV1,
    AgentToolResultV1,
    AgentTurnRequestV1,
)
from application.ports.agent_runtime import AgentRuntimeError
from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_inspect import (
    InspectCapabilityManifest,
    SchedulingInspectRequestV1,
    scheduling_inspect as run_scheduling_inspect,
)


class DemonstrationRequestV1(BaseModel):
    """Typed argument for the single throwaway demonstration tool.

    Pydantic-typed on purpose: it is what proves the model's raw JSON arguments
    arrive *validated* rather than passed through.
    """

    label: str
    repeat: int = 1


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Application configuration for the adapter.

    AD-7: budgets, limits, and timeouts are application configuration, never model
    output. The adapter reads them from here and from the per-request budget — it
    never reads an env var of its own. `settings.py` supplies the values; this
    seam has its OWN fields and deliberately does not overload
    `llm_provider`/`llm_model`, which belong to the separate `LLMProvider` seam.
    """

    model: str = "test"
    api_key: str | None = field(repr=False, default=None)
    default_budget: AgentBudgetV1 = field(default_factory=AgentBudgetV1)
    instructions: str = (
        "You are ShiftMind's scheduling assistant. Be concise and factual."
    )


class PydanticAIAgentRuntime:
    """Implements `application.ports.agent_runtime.AgentRuntime`."""

    def __init__(
        self,
        *,
        config: AgentRuntimeConfig | None = None,
        model: object | None = None,
        tracer_provider: object | None = None,
        capabilities: tuple[InspectCapabilityManifest, ...] = (),
        deps: AgentDepsV1 | None = None,
    ) -> None:
        """`model` is an injected framework model (a deterministic double in
        tests). `tracer_provider` lets a caller observe emitted spans; it does not
        change what is emitted.
        """
        self._config = config or AgentRuntimeConfig()
        self._model = model
        self._deps = deps
        self._registered_capability_names = tuple(
            capability.capability_name for capability in capabilities
        )

        # AD-12/AD-15: external telemetry excludes prompt, tool, workforce, and
        # schedule content BY DEFAULT. This is constructed content-disabled and
        # there is no parameter to turn it on — enabling content export is a
        # deliberate future decision, not an adapter option.
        #
        # Deliberately NOT the Logfire SDK: Story 5.1 owns telemetry export.
        # `opentelemetry-api` arriving transitively under pydantic-ai-slim is all
        # this story needs.
        instrumentation_settings = (
            InstrumentationSettings(
                include_content=False, tracer_provider=tracer_provider
            )
            if tracer_provider is not None
            else InstrumentationSettings(include_content=False)
        )

        self._agent: Agent = Agent(
            deps_type=AgentDepsV1 | None,
            output_type=[str, DeferredToolRequests],
            instructions=self._config.instructions,
            capabilities=[Instrumentation(settings=instrumentation_settings)],
        )

        # Exactly ONE throwaway demonstration tool, proving the typed-tool and
        # deferred-call seams end to end. It reads no scenario data, touches no
        # repository, and resembles no real capability — the capability registry
        # is Story 2.5's and `CapabilityManifestV1` is Story 2.6's.
        #
        # Approval is CONDITIONAL rather than unconditional so one tool can prove
        # both halves of the seam: `repeat == 1` executes freely (an ordinary
        # bounded tool loop), `repeat > 1` suspends for approval. Raising
        # ApprovalRequired from the body is also the shape ShiftMind actually
        # needs — approval is a persisted one-time state machine (AD-10), not an
        # in-process callback.
        @self._agent.tool
        def shiftmind_demonstration(ctx, payload: DemonstrationRequestV1) -> str:
            if payload.repeat > 1 and not ctx.tool_call_approved:
                raise ApprovalRequired
            return "|".join([payload.label] * payload.repeat)

        for capability in capabilities:
            if capability.capability_name == "scheduling_inspect":
                if deps is None:
                    raise ValueError("scheduling_inspect requires trusted AgentDepsV1")

                @self._agent.tool(name="scheduling_inspect")
                def scheduling_inspect(
                    ctx: RunContext[AgentDepsV1 | None],
                    request: SchedulingInspectRequestV1,
                ) -> dict[str, object]:
                    if ctx.deps is None:
                        raise RuntimeError("trusted agent dependencies are unavailable")
                    from dataclasses import asdict

                    return asdict(run_scheduling_inspect(ctx.deps, request))

    @property
    def name(self) -> str:
        return "pydantic-ai"

    @property
    def registered_capability_names(self) -> tuple[str, ...]:
        """Application-granted tools only; the demonstration seam is excluded."""
        return self._registered_capability_names

    def run_turn(self, request: AgentTurnRequestV1) -> AgentRunOutcomeV1:
        budget = _merge_budget(self._config.default_budget, request.budget)
        history = to_framework_messages(request.history)
        deferred = _to_deferred_results(request)

        token = CancellationToken()
        timer: threading.Timer | None = None
        if budget.deadline_seconds is not None:
            # The ADAPTER owns the wall-clock deadline. PydanticAI's UsageLimits
            # has no deadline field, so without this there would be no way to
            # distinguish AD-7's `timed_out` from `budget_exhausted`.
            timer = threading.Timer(budget.deadline_seconds, token.cancel)
            timer.daemon = True
            timer.start()

        try:
            result = self._agent.run_sync(
                request.prompt,
                model=self._model,
                message_history=history or None,
                deferred_tool_results=deferred,
                usage_limits=_to_usage_limits(budget),
                cancellation_token=token,
                deps=self._deps,
            )
        except RunCancelled as exc:
            # Wall-clock expiry -> `timed_out` (AD-7), distinguished BY TYPE and
            # never by string-matching a message.
            return AgentRunOutcomeV1(status="timed_out", summary=str(exc)[:200])
        except UsageLimitExceeded as exc:
            # Any other budget ceiling -> `failed` + stable `budget_exhausted`.
            return AgentRunOutcomeV1(
                status="failed",
                failure_reason="budget_exhausted",
                summary=str(exc)[:200],
            )
        except UnexpectedModelBehavior as exc:
            raise AgentRuntimeError("agent runtime produced unusable output") from exc
        except ModelHTTPError as exc:
            raise AgentRuntimeError("agent runtime provider call failed") from exc
        except AgentRunError as exc:
            # Framework-level catch-all. Still an owned type, cause preserved —
            # never a bare `except Exception` that swallows the cause.
            raise AgentRuntimeError("agent runtime call failed") from exc
        finally:
            if timer is not None:
                timer.cancel()

        turn = to_owned_turn(result.all_messages())
        summary = summarize(turn)

        if isinstance(result.output, DeferredToolRequests):
            return AgentRunOutcomeV1(
                status="suspended",
                turn=turn,
                summary=summary,
                approval=AgentApprovalPendingV1(
                    pending_calls=tuple(
                        AgentToolCallProposalV1(
                            tool_call_id=call.tool_call_id,
                            tool_name=call.tool_name,
                            tool_args_json=call.args_as_json_str(),
                        )
                        for call in result.output.approvals
                    ),
                    turn=turn,
                ),
            )

        return AgentRunOutcomeV1(
            status="completed",
            output_text=str(result.output),
            turn=turn,
            summary=summary,
            tool_results=_tool_results(turn),
        )


def _merge_budget(default: AgentBudgetV1, request: AgentBudgetV1) -> AgentBudgetV1:
    """Per-request budget wins; configured defaults fill the gaps. Both are
    application-owned — neither can originate in model output.
    """
    return AgentBudgetV1(
        request_limit=(
            request.request_limit
            if request.request_limit is not None
            else default.request_limit
        ),
        tool_calls_limit=(
            request.tool_calls_limit
            if request.tool_calls_limit is not None
            else default.tool_calls_limit
        ),
        total_tokens_limit=(
            request.total_tokens_limit
            if request.total_tokens_limit is not None
            else default.total_tokens_limit
        ),
        deadline_seconds=(
            request.deadline_seconds
            if request.deadline_seconds is not None
            else default.deadline_seconds
        ),
    )


def _to_usage_limits(budget: AgentBudgetV1) -> UsageLimits | None:
    if not any(
        (
            budget.request_limit is not None,
            budget.tool_calls_limit is not None,
            budget.total_tokens_limit is not None,
        )
    ):
        return None
    return UsageLimits(
        request_limit=budget.request_limit,
        tool_calls_limit=budget.tool_calls_limit,
        total_tokens_limit=budget.total_tokens_limit,
    )


def _to_deferred_results(request: AgentTurnRequestV1) -> DeferredToolResults | None:
    """Owned approval decisions -> framework deferred results.

    The decisions are server-owned: they come from the application's persisted
    approval record (AD-10), never from model output.
    """
    if not request.approvals:
        return None
    approvals: dict[str, object] = {}
    for decision in request.approvals:
        approvals[decision.tool_call_id] = (
            True
            if decision.approved
            else ToolDenied(
                decision.denial_reason
                if decision.denial_reason is not None
                else "denied by the application"
            )
        )
    return DeferredToolResults(approvals=approvals)


def _tool_results(turn) -> tuple[AgentToolResultV1, ...]:
    return tuple(
        AgentToolResultV1(
            tool_call_id=part.tool_call_id or "",
            tool_name=part.tool_name or "",
            content=part.text or "",
        )
        for message in turn.messages
        if message.role == "tool_result"
        for part in message.parts
    )


def create_agent_runtime(
    *, settings=None, model: object | None = None
) -> PydanticAIAgentRuntime:
    """Factory mirroring `llm/base.py:create_provider`'s shape.

    Kept separate from `create_provider` on purpose: two seams, two factories, two
    configurations (AD-19). This one reads `agent_runtime_*` settings fields and
    never `llm_provider`/`llm_model`.
    """
    config = AgentRuntimeConfig()
    if settings is not None:
        config = AgentRuntimeConfig(
            model=settings.agent_runtime_model,
            api_key=settings.agent_runtime_api_key,
            default_budget=AgentBudgetV1(
                request_limit=settings.agent_runtime_request_limit,
                tool_calls_limit=settings.agent_runtime_tool_calls_limit,
                deadline_seconds=settings.agent_runtime_deadline_seconds,
            ),
        )
    return PydanticAIAgentRuntime(config=config, model=model)
