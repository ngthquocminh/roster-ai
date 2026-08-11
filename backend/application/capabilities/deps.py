"""Trusted, server-owned dependencies supplied to an agent run."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

from application.contracts.agent_runtime import AgentBudgetV1
from application.ports.scenario_projection import ScenarioProjectionReader

SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class AgentDepsV1:
    actor_id: UUID
    site_id: UUID
    membership_id: UUID
    request_id: UUID
    agent_run_id: UUID
    conversation_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    policy_version: str
    clock: Callable[[], datetime]
    projection_reader: ScenarioProjectionReader
    connection: Any
    remaining_budget: AgentBudgetV1
    schema_version: str = SCHEMA_VERSION


__all__ = ["AgentDepsV1", "SCHEMA_VERSION"]
