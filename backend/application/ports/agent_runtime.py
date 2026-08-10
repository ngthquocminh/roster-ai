"""Application port for the ShiftMind-owned agent runtime.

AD-19 introduces a ShiftMind-owned `AgentRuntime` port for multi-step
orchestration. This module is that port. It imports no framework: an
implementation may be the PydanticAI adapter in `backend/agent/`, or a fake, and
application code cannot tell which from the types alone.

This is deliberately NOT the existing `LLMProvider` seam. `backend/llm/`'s
provider-neutral constraint-parsing and cached-insight operations stay behind
their own port until deliberately migrated (AD-19, AC2). The two seams may share
a provider client *inside adapters*, but they do not share a port, an error type,
or a configuration key.

Shape mirrors `application/ports/scenario_projection.py`: frozen dataclass DTOs
in `application/contracts/`, a `typing.Protocol` for the port itself, absolute
imports from the backend root.
"""
from __future__ import annotations

from typing import Protocol

from application.contracts.agent_runtime import (
    AgentRunOutcomeV1,
    AgentTurnRequestV1,
)


class AgentRuntimeError(RuntimeError):
    """Raised when an agent runtime call fails.

    Provider- and framework-neutral, so no PydanticAI or vendor exception type
    ever crosses this seam. Mirrors the established pattern of
    `llm/base.py:LLMProviderError` — but is a SEPARATE type on purpose: one seam's
    failure must not be catchable as the other's.

    Implementations must preserve the original cause (`raise ... from exc`) so a
    swallowed root cause never becomes the only record of a failure.
    """


class AgentRuntime(Protocol):
    """Run one bounded agent turn and return an owned outcome.

    Contract obligations on any implementation:

    * Accept only the trusted, server-owned inputs in `AgentTurnRequestV1`. A
      model-supplied capability name, a browser value, or an authority flag must
      not reach an authority decision (AD-2, AD-15).
    * Never raise a framework or vendor exception. Translate to
      `AgentRuntimeError`, cause preserved.
    * Never return a framework object, and never let provider hidden reasoning
      reach `AgentRunOutcomeV1` (AD-15).
    * Take budgets, limits, and timeouts from `request.budget` — application
      configuration — never from the model, and never from an env var read
      inside the adapter (AD-7).
    * Distinguish wall-clock expiry (`timed_out`) from other budget exhaustion
      (`failed` + `budget_exhausted`).
    """

    def run_turn(self, request: AgentTurnRequestV1) -> AgentRunOutcomeV1: ...

    @property
    def name(self) -> str: ...
