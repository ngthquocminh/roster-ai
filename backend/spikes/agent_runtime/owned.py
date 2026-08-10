"""A ShiftMind-owned message shape — the whole point of capability 4.

AD-19: framework "messages, deferred calls, tool objects, checkpoints, and
framework event types never become domain, persistence, browser, or audit
contracts."

PydanticAI ships `ModelMessagesTypeAdapter` and `to_jsonable_python`, and its own
docs teach `to_jsonable_python(result.all_messages())` as *the* way to persist a
conversation. That JSON **is** a PydanticAI contract. Persisting it makes the
framework a persisted product contract by definition — which is exactly what
AD-19 prohibits. Capability 4 is not "can we serialize?" (obviously yes); it is
"can we translate into a shape we own and version, and rehydrate from it?"

So the round-trip proved here is:

    ModelMessage[] -> OwnedTurnV1 -> JSON -> OwnedTurnV1 -> ModelMessage[]

with no framework type anywhere in the JSON.

This module is a throwaway spike proof. The real contracts live in
backend/application/contracts/agent_runtime.py; this exists only to demonstrate
the translation is *possible* before the dependency is locked.

Translation is a WHITELIST. We name the part kinds we understand and drop the
rest. At 2.27.0 `ModelResponse.parts` can already carry TextPart, ThinkingPart,
ToolCallPart, FilePart, NativeToolCallPart, NativeToolReturnPart,
ToolSearchCallPart, ToolSearchReturnPart, LoadCapabilityCallPart,
LoadCapabilityReturnPart, CompactionPart and more. A blacklist that skips the one
class named ThinkingPart would silently admit whatever reasoning-bearing part the
framework introduces next.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

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

OwnedRole = Literal["user", "system", "assistant", "tool_result"]


@dataclass(frozen=True)
class OwnedPartV1:
    """One planner-visible unit of a turn. Deliberately not a framework part."""

    schema_version: str
    kind: Literal["text", "tool_call", "tool_result"]
    text: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args_json: str | None = None


@dataclass(frozen=True)
class OwnedMessageV1:
    schema_version: str
    role: OwnedRole
    parts: tuple[OwnedPartV1, ...] = ()


@dataclass(frozen=True)
class OwnedTurnV1:
    schema_version: str
    messages: tuple[OwnedMessageV1, ...] = ()

    # --- translation in -------------------------------------------------

    @classmethod
    def from_framework(cls, messages: list[ModelMessage]) -> "OwnedTurnV1":
        owned: list[OwnedMessageV1] = []
        for message in messages:
            if isinstance(message, ModelRequest):
                owned.extend(_translate_request(message))
            elif isinstance(message, ModelResponse):
                owned.append(_translate_response(message))
            # Any future top-level message kind is dropped, not guessed at.
        return cls(schema_version="1", messages=tuple(owned))

    # --- translation out ------------------------------------------------

    def to_framework(self) -> list[ModelMessage]:
        rebuilt: list[ModelMessage] = []
        for message in self.messages:
            if message.role == "user":
                rebuilt.append(
                    ModelRequest(
                        parts=[
                            UserPromptPart(content=p.text or "") for p in message.parts
                        ]
                    )
                )
            elif message.role == "system":
                rebuilt.append(
                    ModelRequest(
                        parts=[
                            SystemPromptPart(content=p.text or "") for p in message.parts
                        ]
                    )
                )
            elif message.role == "tool_result":
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
                rebuilt.append(ModelResponse(parts=parts))
        return rebuilt

    # --- durable form (ours, not the framework's) -----------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "OwnedTurnV1":
        data = json.loads(raw)
        return cls(
            schema_version=data["schema_version"],
            messages=tuple(
                OwnedMessageV1(
                    schema_version=m["schema_version"],
                    role=m["role"],
                    parts=tuple(OwnedPartV1(**p) for p in m["parts"]),
                )
                for m in data["messages"]
            ),
        )

    def visible_text(self) -> str:
        return "\n".join(
            p.text or ""
            for m in self.messages
            if m.role == "assistant"
            for p in m.parts
            if p.kind == "text"
        )


def _translate_request(message: ModelRequest) -> list[OwnedMessageV1]:
    out: list[OwnedMessageV1] = []
    for part in message.parts:
        # Whitelist: only the request-part kinds we understand.
        if isinstance(part, UserPromptPart):
            content = part.content if isinstance(part.content, str) else str(part.content)
            out.append(
                OwnedMessageV1(
                    schema_version="1",
                    role="user",
                    parts=(OwnedPartV1(schema_version="1", kind="text", text=content),),
                )
            )
        elif isinstance(part, SystemPromptPart):
            out.append(
                OwnedMessageV1(
                    schema_version="1",
                    role="system",
                    parts=(
                        OwnedPartV1(schema_version="1", kind="text", text=part.content),
                    ),
                )
            )
        elif isinstance(part, ToolReturnPart):
            out.append(
                OwnedMessageV1(
                    schema_version="1",
                    role="tool_result",
                    parts=(
                        OwnedPartV1(
                            schema_version="1",
                            kind="tool_result",
                            text=str(part.content),
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id,
                        ),
                    ),
                )
            )
        # RetryPromptPart / InstructionPart / future kinds: dropped.
    return out


def _translate_response(message: ModelResponse) -> OwnedMessageV1:
    parts: list[OwnedPartV1] = []
    for part in message.parts:
        # Whitelist. ThinkingPart is not listed, so it is discarded — and so is
        # every future reasoning-bearing part kind, without needing to name it.
        if isinstance(part, TextPart):
            parts.append(OwnedPartV1(schema_version="1", kind="text", text=part.content))
        elif isinstance(part, ToolCallPart):
            parts.append(
                OwnedPartV1(
                    schema_version="1",
                    kind="tool_call",
                    tool_name=part.tool_name,
                    tool_call_id=part.tool_call_id,
                    tool_args_json=part.args_as_json_str(),
                )
            )
    return OwnedMessageV1(
        schema_version="1", role="assistant", parts=tuple(parts)
    )
