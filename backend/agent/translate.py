"""Framework <-> owned translation. The edge, and the only place it happens.

Mirrors the intent of `llm/translate.py`: unpack the vendor payload into a
neutral shape before it crosses a seam.

**Translation is a whitelist.** We name the part kinds ShiftMind understands and
drop everything else. This is not stylistic. AD-15 says "discard provider
hidden-reasoning parts" — not "discard the one class named ThinkingPart". At
PydanticAI 2.27.0 a `ModelResponse` can already carry `TextPart`, `ThinkingPart`,
`ToolCallPart`, `FilePart`, `NativeToolCallPart`, `NativeToolReturnPart`,
`ToolSearchCallPart`, `ToolSearchReturnPart`, `LoadCapabilityCallPart`,
`LoadCapabilityReturnPart` and `CompactionPart`; a blacklist that skips
`ThinkingPart` alone would silently admit the next reasoning-bearing kind the
framework introduces.

The reverse direction rebuilds framework messages from owned records, so a caller
can resume a conversation without ever having held a framework object.
"""
from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from application.contracts.agent_runtime import (
    SCHEMA_VERSION,
    AgentMessageV1,
    AgentPartV1,
    AgentTurnV1,
)


def to_owned_turn(messages: list[ModelMessage]) -> AgentTurnV1:
    """framework messages -> owned durable transcript.

    Never `to_jsonable_python(result.all_messages())`: that JSON carries
    PydanticAI's own `part_kind` discriminator, and persisting it would make the
    framework a persisted product contract (AD-19).
    """
    owned: list[AgentMessageV1] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            owned.extend(_from_request(message))
        elif isinstance(message, ModelResponse):
            translated = _from_response(message)
            if translated.parts:
                owned.append(translated)
        # Any future top-level message kind is dropped, not guessed at.
    return AgentTurnV1(schema_version=SCHEMA_VERSION, messages=tuple(owned))


def to_framework_messages(turn: AgentTurnV1) -> list[ModelMessage]:
    """owned durable transcript -> framework messages, for resuming a run."""
    rebuilt: list[ModelMessage] = []
    for message in turn.messages:
        if message.role == "user":
            if any(part.kind != "text" for part in message.parts):
                raise ValueError("user messages may contain only text parts")
            rebuilt.append(
                ModelRequest(
                    parts=[UserPromptPart(content=p.text or "") for p in message.parts]
                )
            )
        elif message.role == "system":
            if any(part.kind != "text" for part in message.parts):
                raise ValueError("system messages may contain only text parts")
            rebuilt.append(
                ModelRequest(
                    parts=[SystemPromptPart(content=p.text or "") for p in message.parts]
                )
            )
        elif message.role == "tool_result":
            if any(part.kind != "tool_result" for part in message.parts):
                raise ValueError("tool-result messages may contain only tool_result parts")
            rebuilt.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            tool_name=p.tool_name or "",
                            content=p.text or "",
                            tool_call_id=p.tool_call_id or "",
                        )
                        for p in message.parts
                    ]
                )
            )
        elif message.role == "assistant":
            parts: list[Any] = []
            for p in message.parts:
                if p.kind == "text":
                    parts.append(TextPart(content=p.text or ""))
                elif p.kind == "tool_call":
                    parts.append(
                        ToolCallPart(
                            tool_name=p.tool_name or "",
                            args=p.tool_args_json or "{}",
                            tool_call_id=p.tool_call_id or "",
                        )
                    )
                else:
                    raise ValueError(f"unsupported assistant part kind: {p.kind!r}")
            if parts:
                rebuilt.append(ModelResponse(parts=parts))
        else:
            raise ValueError(f"unsupported agent message role: {message.role!r}")
    return rebuilt


def summarize(turn: AgentTurnV1, *, limit: int = 280) -> str | None:
    """An application-owned condensation of what the planner may see.

    Built from already-translated owned text, so hidden reasoning cannot reach it
    even in principle — there is no code path from a dropped part to this string.
    """
    visible = turn.visible_text().strip()
    if not visible:
        return None
    collapsed = " ".join(visible.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _from_request(message: ModelRequest) -> list[AgentMessageV1]:
    out: list[AgentMessageV1] = []
    for part in message.parts:
        # Whitelist of request-part kinds. RetryPromptPart, InstructionPart and
        # any future kind fall through and are dropped.
        if isinstance(part, UserPromptPart):
            content = (
                part.content if isinstance(part.content, str) else str(part.content)
            )
            out.append(
                AgentMessageV1(
                    role="user",
                    parts=(AgentPartV1(kind="text", text=content),),
                )
            )
        elif isinstance(part, SystemPromptPart):
            out.append(
                AgentMessageV1(
                    role="system",
                    parts=(AgentPartV1(kind="text", text=part.content),),
                )
            )
        elif isinstance(part, ToolReturnPart):
            out.append(
                AgentMessageV1(
                    role="tool_result",
                    parts=(
                        AgentPartV1(
                            kind="tool_result",
                            text=str(part.content),
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id,
                        ),
                    ),
                )
            )
    return out


def _from_response(message: ModelResponse) -> AgentMessageV1:
    parts: list[AgentPartV1] = []
    for part in message.parts:
        # Whitelist. ThinkingPart is not named here and therefore never survives
        # — and neither does any future reasoning-bearing part kind.
        if isinstance(part, TextPart):
            parts.append(AgentPartV1(kind="text", text=part.content))
        elif isinstance(part, ToolCallPart):
            parts.append(
                AgentPartV1(
                    kind="tool_call",
                    tool_name=part.tool_name,
                    tool_call_id=part.tool_call_id,
                    tool_args_json=part.args_as_json_str(),
                )
            )
    return AgentMessageV1(role="assistant", parts=tuple(parts))
