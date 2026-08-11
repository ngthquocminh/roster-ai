"""Governed, deliberately non-product demonstration capability.

SCOPE_CONTROLS records the current evidence/audit reduction honestly: mappings
are declared and conformance-checked, but emission is NOT COVERED until Story
2.7 and Epic 4 provide their governing mechanisms.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import (
    CapabilityApprovalRequired,
    CapabilityError,
    CapabilityManifestV1,
)

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "shiftmind_demonstration"
ERROR_CODES = ("approval_required", "budget_exhausted", "invalid_repeat")
EVALUATION_FIXTURES = (
    "evals/golden/demonstration/repeat-once.json",
    "evals/golden/demonstration/repeat-with-approval.json",
)

SCOPE_CONTROLS: Mapping[str, str] = {
    "budget": "Reads the trusted remaining tool-call budget. NOT COVERED: durable budget accounting.",
    "audit": "Declares safe identifiers in the manifest. NOT COVERED: audit envelope emission (Epic 4).",
    "evidence": "Declares output mapping in the manifest. NOT COVERED: EvidenceRefV1 emission (Story 2.7).",
}


class DemonstrationError(CapabilityError):
    code = "invalid_repeat"


class DemonstrationApprovalRequired(DemonstrationError, CapabilityApprovalRequired):
    code = "approval_required"


class DemonstrationBudgetExhausted(DemonstrationError):
    code = "budget_exhausted"


@dataclass(frozen=True)
class DemonstrationRequestV1:
    label: str
    repeat: int = 1


@dataclass(frozen=True)
class DemonstrationResultV1:
    text: str
    schema_version: str = SCHEMA_VERSION


def demonstration_manifest() -> CapabilityManifestV1:
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref="application.capabilities.demonstration.DemonstrationRequestV1",
        output_schema_ref="application.capabilities.demonstration.DemonstrationResultV1",
        risk_class="consequential",
        permission="demonstration:execute",
        scope="current_site/current_conversation",
        version_semantics="request and result use schema version 1",
        idempotency_semantics=(
            "pure over arguments; tool effects are keyed by (agent_run_id, tool_call_id) per AD-8"
        ),
        budget_limit=1,
        timeout_seconds=1.0,
        approval_policy="exact_action",
        audit_mapping="agent run and tool call identifiers; no prompt content",
        evidence_mapping="declared result text and capability version",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def demonstrate(
    deps: AgentDepsV1,
    payload: DemonstrationRequestV1,
    manifest: CapabilityManifestV1,
) -> DemonstrationResultV1:
    del manifest
    remaining = deps.remaining_budget.tool_calls_limit
    if remaining is not None and remaining <= 0:
        raise DemonstrationBudgetExhausted("no tool-call budget remains for this run")
    if payload.repeat < 1:
        raise DemonstrationError("repeat must be at least 1")
    if payload.repeat > 1:
        raise DemonstrationApprovalRequired(
            "repetition requires exact-action approval",
            DemonstrationResultV1(text="|".join([payload.label] * payload.repeat)),
        )
    return DemonstrationResultV1(text=payload.label)


def demonstration_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=demonstration_manifest(),
        handler=demonstrate,
        request_type=DemonstrationRequestV1,
        error_type=DemonstrationError,
        retryable_error_codes=frozenset({"invalid_repeat"}),
        required_role="planner",
        required_feature_policy="demonstration_enabled",
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "SCOPE_CONTROLS",
    "DemonstrationApprovalRequired", "DemonstrationBudgetExhausted",
    "DemonstrationError", "DemonstrationRequestV1", "DemonstrationResultV1",
    "demonstrate", "demonstration_manifest", "demonstration_module",
]
