"""PydanticAI adapter for the owned `AgentRuntime` port.

Owned request -> framework call -> owned outcome. The seven capabilities the
Story 2.1 spike proved possible become real behavior here; the spike showed they
*can* be done, this module makes them ours.

Nothing framework-shaped leaves this module: every exception is re-raised as
`AgentRuntimeError` with its cause preserved, and every message is translated
through `agent/translate.py` before it is returned.
"""
from __future__ import annotations

import json
import re
import threading
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from pydantic_ai import (
    Agent,
    AgentRunError,
    CancellationToken,
    DeferredToolRequests,
    DeferredToolResults,
    InstrumentationSettings,
    ModelAPIError,
    ModelHTTPError,
    ModelRetry,
    RunCancelled,
    RunContext,
    ToolDenied,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai import capture_run_messages
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.exceptions import FallbackExceptionGroup
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import infer_model
from pydantic_ai.output import TextOutput, ToolOutput
from pydantic_ai.usage import RunUsage

from agent.translate import summarize, to_framework_messages, to_owned_turn
from agent.scheduling_instructions import SCHEDULING_ASSISTANT_INSTRUCTIONS
from application.contracts.agent_runtime import (
    AgentApprovalPendingV1,
    AgentBudgetV1,
    AgentRunOutcomeV1,
    AgentToolCallProposalV1,
    AgentToolResultV1,
    AgentTurnRequestV1,
)
from application.app_version import APP_VERSION
from application.contracts.telemetry import (
    AgentUsageV1,
    BudgetOutcomeV1,
    CorrelationV1,
    TelemetryRecordV1,
)
from application.ports.agent_runtime import (
    AgentInvalidOutputError,
    AgentProviderError,
    AgentRuntimeError,
)
from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError
from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1
from application.contracts.dialogue import ClarificationV1, RefusalV1
from application.contracts.proposal import DraftProposalV1
from application.capabilities.scheduling_compute import CAPABILITY_NAME as SCHEDULING_COMPUTE_CAPABILITY
from application.capabilities.scheduling_draft import CAPABILITY_NAME as SCHEDULING_DRAFT_CAPABILITY
from application.grounding.gate import numeric_prose_violation, trusted_numeric_words
from agent.capability_tools import render_capabilities

# The four named structured-output tools, declared ONCE here where the
# `ToolOutput`s are actually constructed. Evaluation imports these rather than
# re-declaring them: a hardcoded copy diverges silently the day a fourth variant
# is registered, and the divergence surfaces as every refuse/clarify case
# failing on an "unexpected tool call" that is really the output tool.
# `ANSWER_OUTPUT_TOOL` is byte-identical to the pre-Story-2.9 name -- ~15
# construction sites and every non-grounding golden case depend on that string.
ANSWER_OUTPUT_TOOL = "final_result"
CLARIFICATION_OUTPUT_TOOL = "clarification"
REFUSAL_OUTPUT_TOOL = "refusal"
DRAFT_OUTPUT_TOOL = "draft"
#: Appended to every in-loop correction. Without it the model answered the
#: retry as if it were a new user message ("Correction: ... the previously
#: displayed rows are unchanged"), so the planner received a delta instead of
#: the answer (live-suite-final-measurement, C2).
_COMPLETE_ANSWER = (
    " Reply with the COMPLETE corrected answer for the planner's request, not a"
    " correction, apology or description of what changed."
)

OUTPUT_TOOL_NAMES = frozenset(
    {
        ANSWER_OUTPUT_TOOL,
        CLARIFICATION_OUTPUT_TOOL,
        REFUSAL_OUTPUT_TOOL,
        DRAFT_OUTPUT_TOOL,
    }
)


def _trusted_texts(messages: list) -> list[str]:
    """Text a prose numeral may be copied from: never the model's own output.

    Planner prompts, system messages (the workflow snapshot), and tool results
    are application data. Assistant text is trusted only BEFORE the current
    user prompt, where it is rehydrated from persisted, gate-passed activities;
    text the model produced in this run is exactly what is being checked.
    """
    last_prompt = 0
    for index, message in enumerate(messages):
        if isinstance(message, ModelRequest) and any(
            isinstance(part, UserPromptPart) for part in message.parts
        ):
            last_prompt = index
    texts: list[str] = []
    for index, message in enumerate(messages):
        for part in message.parts:
            if isinstance(part, (UserPromptPart, SystemPromptPart)) and isinstance(part.content, str):
                texts.append(part.content)
            elif isinstance(part, ToolReturnPart):
                texts.append(
                    part.content if isinstance(part.content, str)
                    else json.dumps(part.content, default=str, ensure_ascii=False)
                )
            elif isinstance(part, TextPart) and index < last_prompt:
                texts.append(part.content)
    return texts


_WORD_GAP = re.compile(r"\w {2,}\w")
_CLAIM_PLACEHOLDERS = ("<claim", "[claim", "{claim", "[computed", "[value", "[count", "[number")


def _claim_placeholder(text: str, *, is_last: bool = True) -> str | None:
    """A stand-in the model left where a claim's number should be rendered."""
    lowered = text.casefold()
    for marker in _CLAIM_PLACEHOLDERS:
        if marker in lowered:
            return marker
    # "There are  workers in the scenario." -- the claim was dropped and only the
    # gap between its words survives. Required BETWEEN WORDS: ordinary prose may
    # double-space after a sentence ("Hello.  How can I help?").
    if _WORD_GAP.search(text):
        return "a gap between words"
    # "Staffed minutes for C Fork | Grid P 8GR:" -- the sentence announces a
    # number and then stops (live-suite-v2-measurement-final, C5).
    if is_last and text.rstrip().endswith((':', '=', '-', '—')):
        return "a dangling lead-in"
    return None


def _result_ids_this_run(messages: list) -> set[str]:
    """result_id values scheduling_compute actually returned after the current prompt.

    Scoped to scheduling_compute specifically: scheduling_draft's model-facing
    view also carries a `result_id` field (its draft_id, under a different
    name), and trusting that as if it were a calculation citation would let a
    model cite a draft's id as a numeric claim's evidence.
    """
    found: set[str] = set()
    for message in _messages_this_run(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if (isinstance(part, ToolReturnPart)
                    and part.tool_name == SCHEDULING_COMPUTE_CAPABILITY
                    and isinstance(part.content, dict)):
                value = part.content.get("result_id")
                if isinstance(value, str) and value:
                    found.add(value)
    return found


def _mistyped_result_id(cited: str, returned: set[str]) -> str | None:
    """The id this citation was evidently copied from, if it is a near-miss.

    Deliberately strict: an unrelated or invented id must NOT be treated as a
    typo, or the gate's `missing_evidence` state becomes unreachable.
    """
    if cited in returned:
        return None
    for candidate in sorted(returned):
        if SequenceMatcher(None, cited, candidate).ratio() >= .9:
            return candidate
    return None


_QUANTITY_QUESTION = re.compile(r"\bhow (?:many|much)\b", re.IGNORECASE)


def _asks_for_a_quantity(messages: list) -> bool:
    """True when the CURRENT planner prompt asks for a number."""
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                return bool(_QUANTITY_QUESTION.search(part.content))
    return False


def _messages_this_run(messages: list) -> list:
    start = 0
    for index, message in enumerate(messages):
        if isinstance(message, ModelRequest) and any(
            isinstance(part, UserPromptPart) for part in message.parts
        ):
            start = index
    return messages[start:]


def _latest_draft_id_this_run(messages: list) -> str | None:
    """The draft_id returned by scheduling_draft after the current user prompt.

    Rehydrated history also carries earlier turns' tool returns, so only parts
    after the last user prompt belong to this run.
    """
    draft_id = None
    for message in _messages_this_run(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == SCHEDULING_DRAFT_CAPABILITY:
                content = part.content
                if isinstance(content, dict) and isinstance(content.get("draft_id"), str):
                    draft_id = content["draft_id"]
    return draft_id


def _prose_answer(text: str) -> GroundedAnswerV1:
    """A plain-text model reply as one prose segment of a grounded answer."""
    return GroundedAnswerV1(segments=(GroundedProseSegmentV1(text=text.strip()),))


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
    retries_limit: int = 2
    reasoning_effort: str | None = None
    instructions: str = SCHEDULING_ASSISTANT_INSTRUCTIONS


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
        answer_type: type | None = None,
    ) -> None:
        """`model` is an injected framework model (a deterministic double in
        tests). `tracer_provider` lets a caller observe emitted spans; it does not
        change what is emitted.
        """
        self._config = config or AgentRuntimeConfig()
        # Name of the last in-loop rule that asked the model to retry. A closed
        # vocabulary, never the rejected text.
        self._last_retry_rule: str | None = None
        self._model = model if model is not None else _configured_model(self._config)
        self._deps = deps
        self._answer_type = answer_type

        # AD-12/AD-15: external telemetry excludes prompt, tool, workforce, and
        # schedule content BY DEFAULT. This is constructed content-disabled and
        # there is no parameter to turn it on — enabling content export is a
        # deliberate future decision, not an adapter option. Binary capture is
        # also explicitly disabled because the framework default is True.
        #
        # Deliberately NOT the Logfire SDK: Story 5.1 owns telemetry export.
        # `opentelemetry-api` arriving transitively under pydantic-ai-slim is all
        # this story needs.
        instrumentation_settings = (
            InstrumentationSettings(
                include_content=False,
                include_binary_content=False,
                tracer_provider=tracer_provider,
            )
            if tracer_provider is not None
            else InstrumentationSettings(
                include_content=False, include_binary_content=False
            )
        )

        output_type = (
            [str, DeferredToolRequests]
            if answer_type is None
            else [
                ToolOutput(answer_type, name=ANSWER_OUTPUT_TOOL),
                ToolOutput(ClarificationV1, name=CLARIFICATION_OUTPUT_TOOL),
                ToolOutput(RefusalV1, name=REFUSAL_OUTPUT_TOOL),
                ToolOutput(DraftProposalV1, name=DRAFT_OUTPUT_TOOL),
                DeferredToolRequests,
                # Plain text is accepted as a prose-only grounded answer. With
                # only output tools, the request carries tool_choice="required";
                # measured 2026-09-17, openai/gpt-5.6-luna still answered a
                # greeting in text after a tool result and, unable to end that
                # text under "required", repeated it until the upstream stream
                # broke (502 -> invalid_output). Accepting text lets the provider
                # send tool_choice="auto" and the reply terminate normally.
                # Nothing is trusted more: the numeric-prose validator below and
                # the grounding gate apply to this answer exactly as to a tool
                # answer, so a number still needs a cited claim.
                *((TextOutput(_prose_answer),) if answer_type is GroundedAnswerV1 else ()),
            ]
        )
        self._agent: Agent = Agent(
            deps_type=AgentDepsV1 | None,
            output_type=output_type,
            instructions=self._config.instructions,
            capabilities=[Instrumentation(settings=instrumentation_settings)],
            retries={
                "tools": self._config.retries_limit,
                "output": self._config.retries_limit,
            },
        )
        output_toolset = self._agent._output_toolset
        self._output_tool_names = frozenset(
            definition.name
            for definition in (() if output_toolset is None else output_toolset._tool_defs)
        )

        if answer_type is not None:
            # The grounding gate forbids numerals in prose segments, and it runs
            # AFTER the turn completes -- so a violation used to kill the whole
            # turn and persist an empty response. Registering the same rule as an
            # output validator turns it into one corrective retry inside the run,
            # which is the framework's own mechanism for "the model produced
            # something unusable" and is already how a non-structured answer is
            # handled.
            #
            # The rule itself stays in `application/grounding/gate.py`; this is
            # wiring only. `ground_answer` still enforces it as the backstop, so
            # bypassing the validator cannot bypass the invariant.
            @self._agent.output_validator
            def _reject_numeric_prose(
                ctx: RunContext[AgentDepsV1 | None], output: object
            ) -> object:
                # Clarification and refusal are distinct structured outputs. A
                # numeral in bounded refusal copy is operational context, not
                # an uncited grounded claim.
                if not isinstance(output, GroundedAnswerV1):
                    return output
                trusted = trusted_numeric_words(_trusted_texts(ctx.messages))
                for segment in getattr(output, "segments", ()) or ():
                    text = getattr(segment, "text", None)
                    if text is None:
                        continue
                    offending = numeric_prose_violation(text, trusted)
                    if offending is not None:
                        self._last_retry_rule = "numeric_prose"
                        raise ModelRetry(
                            f"The prose segment {text!r} contains {offending!r}, which does "
                            "not appear in any tool result, the workflow snapshot, or the "
                            "planner's messages. Names, IDs and values may be copied exactly "
                            "as they appear there. A quantity you counted, summed or "
                            "otherwise derived must instead be a claim citing a result_id "
                            "returned by a calculation tool. Never spell a number out in "
                            "words to avoid this rule." + _COMPLETE_ANSWER
                        )
                return output

            @self._agent.output_validator
            def _reject_uncited_claim(
                ctx: RunContext[AgentDepsV1 | None], output: object
            ) -> object:
                # A claim with no result_id reaches the gate as a rendered
                # "failed claim" beside otherwise correct prose (observed twice
                # in live-suite-v2-acceptance-b B5: a worker_count claim appended
                # to a draft description that needed no number at all).
                if not isinstance(output, GroundedAnswerV1):
                    return output
                if not getattr(output, "segments", ()):
                    # A structured-output answer with zero segments carries no
                    # text and no claim -- an empty reply the planner would see
                    # as nothing happening. Every other branch below assumes at
                    # least one segment.
                    self._last_retry_rule = "empty_answer"
                    raise ModelRetry(
                        "This answer carries no content -- no prose and no claim. "
                        "Answer the planner's request, clarify, or refuse; do not "
                        "return an empty response." + _COMPLETE_ANSWER
                    )
                returned = _result_ids_this_run(ctx.messages)
                for segment in getattr(output, "segments", ()) or ():
                    result_id = getattr(segment, "result_id", None)
                    if result_id is None:
                        continue
                    if result_id and not returned:
                        # No calculation ran in this turn, so NOTHING could have
                        # produced a citation: the id is invented outright
                        # (live-suite-B-diagnose B5 rep3 appended a worker_count
                        # claim after zero tool calls). Distinct from citing a
                        # wrong id among real results, which stays the gate's
                        # inspectable missing_evidence state.
                        self._last_retry_rule = "claim_without_calculation"
                        raise ModelRetry(
                            "A claim segment cites a result_id, but no calculation tool "
                            "returned a result in this turn, so nothing can support it. "
                            "Call the calculation tool and cite the result_id it returns, or "
                            "remove the claim and answer in prose alone." + _COMPLETE_ANSWER
                        )
                    if result_id:
                        # A citation the model MIS-TRANSCRIBED from a result it
                        # really received (observed: a 63- and a 68-character
                        # copy of a 64-character hash) is a slip it can fix. An
                        # unrelated id stays the gate's business, rendering an
                        # inspectable `missing_evidence` claim -- golden case
                        # grounding-missing-evidence pins that path.
                        intended = _mistyped_result_id(result_id, returned)
                        if intended is not None:
                            self._last_retry_rule = "result_id_mistyped"
                            raise ModelRetry(
                                f"The claim cites result_id {result_id!r}, which differs from "
                                f"the id the calculation returned in this turn: {intended!r}. "
                                "Copy the returned result_id exactly, character for character." + _COMPLETE_ANSWER
                            )
                        continue
                    self._last_retry_rule = "uncited_claim"
                    raise ModelRetry(
                        "A claim segment carries an empty result_id, so it can cite no "
                        "evidence at all. Either call the calculation tool and cite the "
                        "result_id it returns, or remove the claim and answer in prose "
                        "alone -- describing a draft or a stored record needs no claim." + _COMPLETE_ANSWER
                    )
                segments = list(getattr(output, "segments", ()) or ())
                has_claim = any(getattr(segment, "result_id", None) is not None
                                for segment in segments)
                if not has_claim and _asks_for_a_quantity(ctx.messages):
                    # "How many workers are qualified for it?" answered with
                    # "has qualified workers" (live-suite-evidence C6): a
                    # quantity question needs a claim, not a qualitative reply.
                    self._last_retry_rule = "quantity_without_claim"
                    raise ModelRetry(
                        "The planner asked for a quantity, but this answer carries no claim "
                        "segment, so it shows no number. Call the calculation tool and cite "
                        "the result_id it returns. If the quantity genuinely cannot be "
                        "computed, say so plainly instead of implying one." + _COMPLETE_ANSWER
                    )
                if not has_claim:
                    for position, segment in enumerate(segments):
                        text = getattr(segment, "text", "") or ""
                        # A lead-in ending in ':' is only a dropped claim when
                        # NOTHING follows it. Flagging every segment rejected a
                        # correct multi-segment answer until its retries ran out
                        # (live-suite-final-measurement, C7).
                        marker = _claim_placeholder(
                            text, is_last=position == len(segments) - 1)
                        if marker is not None:
                            # The model wrote prose AROUND a claim it never
                            # emitted, leaving the planner a gap where the number
                            # belongs (live-suite-v2-acceptance-c: "has <claim>
                            # staffed minutes", "There are  workers").
                            self._last_retry_rule = "claim_gap"
                            raise ModelRetry(
                                f"The prose segment {text!r} contains {marker!r} where a "
                                "number belongs, but the answer carries no claim segment. "
                                "Add the claim segment citing a result_id from a calculation "
                                "in this turn, or rewrite the sentence without the quantity." + _COMPLETE_ANSWER
                            )
                return output

            @self._agent.output_validator
            def _require_draft_output_after_drafting(
                ctx: RunContext[AgentDepsV1 | None], output: object
            ) -> object:
                # Story 5.7 (lesson 14): the model called scheduling_draft, then
                # answered "Created a draft" in prose. Only the `draft` output
                # persists a proposal, so that prose was a false success claim.
                # A draft created in THIS run must be returned as the draft
                # output; the model is told the exact id it received to cite.
                if isinstance(output, (DraftProposalV1, DeferredToolRequests)):
                    return output
                draft_id = _latest_draft_id_this_run(ctx.messages)
                if draft_id is not None:
                    self._last_retry_rule = "draft_output_missing"
                    raise ModelRetry(
                        "You created a draft in this turn (draft_id "
                        f"{draft_id!r}), but a draft is saved only when you return the "
                        f"`{DRAFT_OUTPUT_TOOL}` output citing that draft_id. Return the "
                        f"`{DRAFT_OUTPUT_TOOL}` output now instead of describing the draft." + _COMPLETE_ANSWER
                    )
                return output

        # Retained so a capability failure can be checked against the error
        # vocabulary its own manifest advertises (see `run_turn`).
        self._granted = capabilities

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

    def _declared_error_codes(self) -> frozenset[str]:
        """Every error code the granted manifests advertise for this run."""
        return frozenset(
            code for module in self._granted for code in module.manifest.errors
        )

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

        model_started = perf_counter()
        usage: AgentUsageV1 | None = None
        accumulated_usage = RunUsage()
        budget_outcome: BudgetOutcomeV1 = "unknown"
        # Captured so an unusable FINAL message cannot discard work the run
        # already did -- see the draft recovery in the UnexpectedModelBehavior
        # branch below.
        run_messages: list = []
        try:
          with capture_run_messages() as run_messages:
            result = self._agent.run_sync(
                request.prompt,
                model=self._model,
                message_history=history or None,
                deferred_tool_results=deferred,
                usage_limits=_to_usage_limits(budget),
                usage=accumulated_usage,
                cancellation_token=token,
                deps=self._deps,
            )
            framework_usage = result.usage
            usage = AgentUsageV1(
                requests=framework_usage.requests,
                tool_calls=framework_usage.tool_calls,
                input_tokens=framework_usage.input_tokens,
                output_tokens=framework_usage.output_tokens,
                cache_read_tokens=framework_usage.cache_read_tokens,
                cache_write_tokens=framework_usage.cache_write_tokens,
            )
            budget_outcome = "within_budget"
        except RunCancelled as exc:
            # Wall-clock expiry -> `timed_out` (AD-7), distinguished BY TYPE and
            # never by string-matching a message.
            budget_outcome = "deadline_expired"
            return AgentRunOutcomeV1(
                status="timed_out",
                summary=str(exc)[:200],
                budget_outcome=budget_outcome,
            )
        except UsageLimitExceeded as exc:
            # Any other budget ceiling -> `failed` + stable `budget_exhausted`.
            budget_outcome = "budget_exhausted"
            # Usage limits are checked between completed requests/tools. The
            # supplied accumulator survives an exception where result.usage
            # cannot be read. Cancellation/provider failures remain unknown:
            # an interrupted in-flight request may still be billed.
            usage = AgentUsageV1(
                requests=accumulated_usage.requests,
                tool_calls=accumulated_usage.tool_calls,
                input_tokens=accumulated_usage.input_tokens,
                output_tokens=accumulated_usage.output_tokens,
                cache_read_tokens=accumulated_usage.cache_read_tokens,
                cache_write_tokens=accumulated_usage.cache_write_tokens,
            )
            return AgentRunOutcomeV1(
                status="failed",
                failure_reason="budget_exhausted",
                failure_source="agent",
                summary=str(exc)[:200],
                budget_outcome=budget_outcome,
                usage=usage,
            )
        except FallbackExceptionGroup as exc:
            # Every retry of a transient provider failure failed too. That is
            # the provider's outage, not the model's output.
            failure = AgentProviderError("agent runtime provider call failed")
            # Partial usage from the failed attempts, same accounting as the
            # UsageLimitExceeded branch above -- otherwise a provider outage
            # silently drops whatever was already billed.
            failure.usage = AgentUsageV1(
                requests=accumulated_usage.requests,
                tool_calls=accumulated_usage.tool_calls,
                input_tokens=accumulated_usage.input_tokens,
                output_tokens=accumulated_usage.output_tokens,
                cache_read_tokens=accumulated_usage.cache_read_tokens,
                cache_write_tokens=accumulated_usage.cache_write_tokens,
            )
            raise failure from exc
        except UnexpectedModelBehavior as exc:
            # The model could not produce a usable final message, but a draft it
            # created in this turn is already persisted work whose identity comes
            # from the TRUSTED tool result, not from the model's prose. Returning
            # that citation is strictly better than discarding the draft and
            # telling the planner nothing happened (live-suite-v2-acceptance-b,
            # C8/C9: retries exhausted on the draft turn itself).
            draft_id = _latest_draft_id_this_run(run_messages)
            if draft_id is not None:
                return AgentRunOutcomeV1(
                    status="completed",
                    draft=DraftProposalV1(draft_id=draft_id),
                    summary="The draft was saved; the assistant produced no usable summary.",
                    budget_outcome="unknown",
                    usage=AgentUsageV1(
                        requests=accumulated_usage.requests,
                        tool_calls=accumulated_usage.tool_calls,
                        input_tokens=accumulated_usage.input_tokens,
                        output_tokens=accumulated_usage.output_tokens,
                        cache_read_tokens=accumulated_usage.cache_read_tokens,
                        cache_write_tokens=accumulated_usage.cache_write_tokens,
                    ),
                )
            failure = AgentInvalidOutputError("agent runtime produced unusable output")
            # Names the RULE, never the rejected text: an invalid-output failure
            # was otherwise undiagnosable after the fact (Story 5.7, B5).
            failure.retry_rule = self._last_retry_rule
            raise failure from exc
        except ModelHTTPError as exc:
            # Typed, not text-tagged: the request path classifies this by class,
            # so rewording the message can never reclassify a provider outage.
            raise AgentProviderError("agent runtime provider call failed") from exc
        except AgentRunError as exc:
            # Framework-level catch-all. Still an owned type, cause preserved —
            # never a bare `except Exception` that swallows the cause.
            raise AgentRuntimeError("agent runtime call failed") from exc
        except CapabilityError as exc:
            # A governed capability's own declared failure. Mapped to a stable
            # `failure_reason` drawn from the manifest's error vocabulary, so
            # the code the manifest advertises is the code callers observe.
            #
            # Provenance is CHECKED, not assumed: `failure_reason` admits any
            # manifest-declared code, so without this a typo, or the
            # `CapabilityError` base's own default code, would cross the port as
            # a stable-looking reason no manifest ever declared.
            if exc.code not in self._declared_error_codes():
                raise AgentRuntimeError(
                    f"capability failure code {exc.code!r} is not declared by any "
                    "granted capability manifest"
                ) from exc
            return AgentRunOutcomeV1(
                status="failed",
                failure_reason=exc.code,
                # Tagged at the raise site so the use case never has to guess
                # from the string. A manifest may declare a code spelled exactly
                # like an agent-level reason -- an installed module already
                # declares one -- and without this tag such a failure was
                # rendered to the planner as an agent budget exhaustion.
                failure_source="capability",
                summary=str(exc)[:200],
                budget_outcome="unknown",
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
            self._emit_model_telemetry(
                duration_ms=(perf_counter() - model_started) * 1_000,
                usage=usage,
                budget_outcome=budget_outcome,
            )

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
                usage=usage,
                budget_outcome=budget_outcome,
            )

        if self._answer_type is not None and not isinstance(
            result.output,
            (GroundedAnswerV1, ClarificationV1, RefusalV1, DraftProposalV1),
        ):
            raise AgentRuntimeError(
                f"unrecognized structured output {type(result.output).__name__}"
            )

        return AgentRunOutcomeV1(
            status="completed",
            output_text=(str(result.output) if self._answer_type is None else None),
            answer=(
                result.output
                if isinstance(result.output, GroundedAnswerV1)
                else None
            ),
            clarification=(
                result.output if isinstance(result.output, ClarificationV1) else None
            ),
            refusal=(result.output if isinstance(result.output, RefusalV1) else None),
            draft=(
                result.output if isinstance(result.output, DraftProposalV1) else None
            ),
            turn=turn,
            summary=summary,
            tool_results=_tool_results(turn, excluded_names=self._output_tool_names),
            usage=usage,
            budget_outcome=budget_outcome,
        )

    def _emit_model_telemetry(
        self,
        *,
        duration_ms: float,
        usage: AgentUsageV1 | None,
        budget_outcome: BudgetOutcomeV1,
    ) -> None:
        sink = getattr(self._deps, "telemetry", None)
        if sink is None:
            return
        deps = self._deps
        try:
            sink.emit(
                TelemetryRecordV1(
                    event="agent.model.calls.completed",
                    occurred_at=datetime.now(timezone.utc),
                    app_version=APP_VERSION,
                    correlation=CorrelationV1(
                        request_id=getattr(deps, "request_id", None),
                        site_id=getattr(deps, "site_id", None),
                        actor_id=getattr(deps, "actor_id", None),
                        conversation_id=getattr(deps, "conversation_id", None),
                        agent_run_id=getattr(deps, "agent_run_id", None),
                    ),
                    labels={
                        "model": self._config.model,
                        "budget_outcome": budget_outcome,
                    },
                    duration_ms=duration_ms,
                    usage=usage,
                    budget_outcome=budget_outcome,
                )
            )
        except Exception:  # noqa: BLE001 - telemetry cannot affect the run
            return


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


def _tool_results(
    turn, *, excluded_names: frozenset[str] = frozenset()
) -> tuple[AgentToolResultV1, ...]:
    return tuple(
        AgentToolResultV1(
            tool_call_id=part.tool_call_id or "",
            tool_name=part.tool_name or "",
            content=part.text or "",
        )
        for message in turn.messages
        if message.role == "tool_result"
        for part in message.parts
        if part.tool_name not in excluded_names
    )


def _openrouter_model_settings(reasoning_effort: str | None) -> dict | None:
    """Build the OpenRouter extra_body settings, or omit them entirely.

    Not every OpenRouter-routed model accepts the "reasoning" parameter (e.g.
    qwen/qwen3-235b-a22b-2507 does not list it in its supported_parameters) --
    sending it anyway makes the provider reject the whole call, failing every
    turn against that model with no usable content. "none" (like the absence
    of a configured value) means "send no reasoning settings", not "send
    reasoning.effort='none'", which is not a real OpenRouter effort value.
    """
    if reasoning_effort is None or reasoning_effort == "none":
        return None
    return {'extra_body': {'reasoning': {'effort': reasoning_effort}}}


#: Extra attempts for ONE model request when OpenRouter reports a transient
#: upstream failure. Retrying the request, not the turn, never re-runs a tool the
#: model already called. Measured 2026-09-17: about 1 in 4 live requests on
#: openai/gpt-5.6-luna ended `finish_reason: "error"`, which the generic
#: OpenAI chat model rejected as invalid output (Story 5.7 lesson 18).
OPENROUTER_TRANSIENT_RETRIES = 2


def _is_transient_openrouter_error(exc: Exception) -> bool:
    """Retry provider hiccups; never a request the provider rejected as invalid."""
    if isinstance(exc, ModelHTTPError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, ModelAPIError)


def _is_upstream_error_response(response: ModelResponse) -> bool:
    """OpenRouter's `finish_reason: "error"`: the upstream model failed mid-generation."""
    return response.finish_reason == "error"


def _configured_model(config: AgentRuntimeConfig) -> object:
    """Resolve the owned model setting without consulting another LLM seam."""
    normalized = config.model.strip().lower()
    if normalized == "deterministic":
        from agent.deterministic_model import build_deterministic_model

        return build_deterministic_model()
    if normalized == "test":
        return infer_model("test")
    provider_name, separator, model_name = config.model.partition(":")
    if not separator or not model_name:
        raise ValueError(
            "agent runtime model must be 'deterministic', 'test', or '<provider>:<model-name>'"
        )
    if provider_name == "openrouter":
        from pydantic_ai.models.fallback import FallbackModel
        from pydantic_ai.models.openrouter import OpenRouterModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider(api_key=config.api_key)
        attempts = [
            OpenRouterModel(
                model_name,
                provider=provider,
                settings=_openrouter_model_settings(config.reasoning_effort),
            )
            for _ in range(1 + OPENROUTER_TRANSIENT_RETRIES)
        ]
        return FallbackModel(
            *attempts,
            fallback_on=[_is_transient_openrouter_error, _is_upstream_error_response],
        )
    if provider_name == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(model_name, provider=GoogleProvider(api_key=config.api_key))
    if provider_name == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            model_name, provider=AnthropicProvider(api_key=config.api_key)
        )
    return infer_model(config.model)


def create_agent_runtime(
    *, settings=None, model: object | None = None,
    capabilities: tuple[CapabilityModuleV1, ...] = (),
    deps: AgentDepsV1 | None = None,
    answer_type: type | None = None,
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
                total_tokens_limit=settings.agent_runtime_total_tokens_limit,
                deadline_seconds=settings.agent_runtime_deadline_seconds,
            ),
            retries_limit=settings.agent_runtime_retries_limit,
            reasoning_effort=getattr(settings, 'agent_runtime_reasoning_effort', None),
        )
    return PydanticAIAgentRuntime(
        config=config,
        model=model,
        capabilities=capabilities,
        deps=deps,
        answer_type=answer_type,
    )
