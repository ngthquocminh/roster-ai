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
# Distinct from SCHEMA_VERSION: the request/result SHAPES are unchanged, but
# the model-visible error vocabulary changed in Story 2.7 (a timeout overrun
# stopped being a retryable `invalid_query`), and a consumer that cannot see
# that change cannot react to it.
CAPABILITY_VERSION = "2"
CAPABILITY_NAME = "shiftmind_demonstration"
ERROR_CODES = (
    "demonstration_failed", "approval_required", "budget_exhausted", "invalid_repeat"
)
EVALUATION_FIXTURES = (
    "evals/golden/demonstration/repeat-once.json",
    "evals/golden/demonstration/repeat-with-approval.json",
)

# An upper bound on model-supplied repetition. Distinct from the manifest's
# `budget_limit`, which counts tool calls, not characters: without this a
# model-supplied `repeat=10**9` would allocate unboundedly inside the handler.
MAX_REPEAT = 64

SCOPE_CONTROLS: Mapping[str, str] = {
    "budget": "Reads the trusted remaining tool-call budget. NOT COVERED: durable budget accounting.",
    "audit": "Declares safe identifiers in the manifest. NOT COVERED: audit envelope emission (Epic 4).",
    "evidence": "Declares output mapping in the manifest. NOT COVERED: EvidenceRefV1 emission (Story 2.7).",
    "approval": (
        "Refuses before computing when exact-action approval is absent, so an unapproved call "
        "performs no work. NOT COVERED: durable one-time approval state (AD-10, Epic 4)."
    ),
}


class DemonstrationError(CapabilityError):
    code = "demonstration_failed"


class DemonstrationInvalidRepeat(DemonstrationError):
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
        capability_version=CAPABILITY_VERSION,
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
        raise DemonstrationInvalidRepeat("repeat must be at least 1")
    if payload.repeat > MAX_REPEAT:
        raise DemonstrationInvalidRepeat(f"repeat must not exceed {MAX_REPEAT}")
    # Authority BEFORE effect: nothing is computed on an unapproved call, and
    # the approved call executes exactly once. Raising after building the result
    # would mean "act, then ask" -- and then act a second time on resume.
    if payload.repeat > 1 and not deps.tool_call_approved:
        raise DemonstrationApprovalRequired("repetition requires exact-action approval")
    return DemonstrationResultV1(text="|".join([payload.label] * payload.repeat))


def demonstration_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=demonstration_manifest(),
        handler=demonstrate,
        request_type=DemonstrationRequestV1,
        error_type=DemonstrationError,
        retryable_error_codes=frozenset({"invalid_repeat"}),
        required_role="planner",
        required_feature_policy="demonstration_enabled",
        request_argument="payload",
        # The result IS this string. Projecting the whole record instead would
        # change the transcript and therefore the bytes of Story 2.2's seven
        # frozen golden cases and the sha256-pinned demonstration evidence.
        model_facing_view=lambda result: result.text,
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "MAX_REPEAT", "SCOPE_CONTROLS",
    "DemonstrationApprovalRequired", "DemonstrationBudgetExhausted",
    "DemonstrationError", "DemonstrationInvalidRepeat", "DemonstrationRequestV1", "DemonstrationResultV1",
    "demonstrate", "demonstration_manifest", "demonstration_module",
]
