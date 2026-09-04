"""Trusted, server-owned dependencies supplied to an agent run."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

from application.contracts.agent_runtime import AgentBudgetV1
from application.ports.scenario_projection import ScenarioProjectionReader
from application.ports.telemetry import TelemetrySink

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
    # TWO MEANINGS, ONE NAME -- do not unify them (Decision 6).
    #
    # This is the capability-GRANT policy stamp: the `POLICY_GENERATION` string
    # ("one-user-mvp-v1"), byte-pinned into Story 2.2's golden fixtures
    # (`evals/report.py` hardcodes it). It is NOT the approval rulebook.
    #
    # `ApprovalBindingV1.policy_version` is the DERIVED consequential-policy
    # version, `f"{POLICY_GENERATION}+{sha256(...)[:12]}"` over `PolicyInputsV1`
    # (`capabilities/registry.py` -- `derive_policy_version`). Only the binding
    # carries the derived value. Changing this field to the derived one would
    # silently invalidate every pinned eval fixture.
    policy_version: str
    clock: Callable[[], datetime]
    projection_reader: ScenarioProjectionReader
    connection: Any
    remaining_budget: AgentBudgetV1
    # Per-tool-call approval state, translated from the framework's run context
    # by the adapter so a handler can check authority BEFORE acting without
    # importing a framework type. Defaults to False: unapproved unless proven.
    tool_call_approved: bool = False
    # Captures trusted raw handler results for the post-run grounding gate.
    # The model sees only the separately rendered representation.
    tool_result_sink: Callable[[object], None] | None = None
    telemetry: TelemetrySink | None = None
    schema_version: str = SCHEMA_VERSION


__all__ = ["AgentDepsV1", "SCHEMA_VERSION"]
