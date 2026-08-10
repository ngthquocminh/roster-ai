"""AgentRuntime and capability-module adapters (AR26's structural seed).

This package is the ONLY place in the backend allowed to import `pydantic_ai`.
It implements `application/ports/agent_runtime.py` over PydanticAI and translates
at the edge in both directions, so no framework message, deferred call, tool
object, checkpoint, or event type reaches domain, application, persistence,
browser, or audit surfaces (AD-19).

Dependency direction is one-way: `agent` may import `application` and `domain`;
neither may import `agent`. `backend/tests/architecture/` enforces this.
"""
from agent.runtime import PydanticAIAgentRuntime, create_agent_runtime

__all__ = ["PydanticAIAgentRuntime", "create_agent_runtime"]
