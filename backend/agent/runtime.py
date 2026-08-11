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
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError
from agent.capability_tools import render_capabilities


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
        capabilities: tuple[CapabilityModuleV1, ...] = (),
        deps: AgentDepsV1 | None = None,
    ) -> None:
        """`model` is an injected framework model (a deterministic double in
        tests). `tracer_provider` lets a caller observe emitted spans; it does not
        change what is emitted.
        """
        self._config = config or AgentRuntimeConfig()
        self._model = model
        self._deps = deps

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

        # Collected as each tool is actually registered, so this can never
        # over-report a granted-but-unrendered capability.
        self._registered_capability_names = render_capabilities(
            self._agent, capabilities, deps
        )

    @property
    def name(self) -> str:
        return "pydantic-ai"

    @property
    def registered_capability_names(self) -> tuple[str, ...]:
        """Names of the application-granted tools actually registered on this run.

        Loading a module grants no authority: only the supplied granted tuple is
        rendered, and absent modules cannot be called by a model-generated name.
        """
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
        except CapabilityError as exc:
            # A governed capability's own declared failure. Mapped to a stable
            # `failure_reason` drawn from the manifest's error vocabulary, so
            # the code the manifest advertises is the code callers observe.
            return AgentRunOutcomeV1(
                status="failed",
                failure_reason=exc.code,
                summary=str(exc)[:200],
            )
        except Exception as exc:  # noqa: BLE001
            # Nothing raw crosses this port. PydanticAI converts only
            # `ToolFailed`/`ModelRetry`; every other tool-body exception
            # propagates, so an unowned builtin would otherwise reach the
            # caller as `KeyError`/`TypeError` instead of an owned type.
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
