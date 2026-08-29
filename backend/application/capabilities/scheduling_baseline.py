"""Consequential baseline-promotion request that always suspends before effect."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityApprovalRequired, CapabilityError, CapabilityManifestV1

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_baseline"
SCHEDULING_BASELINE_POLICY = "scheduling_baseline_enabled"
ERROR_CODES = ("baseline_request_failed", "approval_required", "invalid_query")
EVALUATION_FIXTURES = ("evals/golden/scheduling_baseline/approval-required.json",)
SCOPE_CONTROLS: Mapping[str, str] = {
    "promotion": "NOT COVERED: promotion:owned_by_story_4_3",
    "decision": "NOT COVERED: decision:owned_by_story_4_2",
}


class SchedulingBaselineError(CapabilityError):
    code = "baseline_request_failed"


class SchedulingBaselineInvalidRequest(SchedulingBaselineError):
    code = "invalid_query"


class SchedulingBaselineApprovalRequired(SchedulingBaselineError, CapabilityApprovalRequired):
    code = "approval_required"


@dataclass(frozen=True)
class SchedulingBaselineRequestV1:
    schedule_run_id: UUID
    expected_baseline_schedule_version: str | None
    schema_version: str = SCHEMA_VERSION


def scheduling_baseline_manifest() -> CapabilityManifestV1:
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME, capability_version=SCHEMA_VERSION,
        input_schema_ref="application.capabilities.scheduling_baseline.SchedulingBaselineRequestV1",
        output_schema_ref="application.contracts.approval_binding.ApprovalBindingV1",
        risk_class="consequential", permission="site_baseline:promote",
        scope="current_actor/current_site/exact_schedule_run", version_semantics="pins candidate and baseline at TX1",
        idempotency_semantics="tool effects are keyed by (agent_run_id, tool_call_id)",
        budget_limit=1, timeout_seconds=5.0, approval_policy="exact_action",
        audit_mapping="approval requested audit envelope", evidence_mapping="exact candidate and baseline binding",
        errors=ERROR_CODES, evaluation_fixtures=EVALUATION_FIXTURES,
    )


def scheduling_baseline(deps: AgentDepsV1, request: SchedulingBaselineRequestV1, manifest: CapabilityManifestV1) -> None:
    del manifest
    if deps.remaining_budget.tool_calls_limit is not None and deps.remaining_budget.tool_calls_limit <= 0:
        raise SchedulingBaselineError("no tool-call budget remains for this run")
    if request.schedule_run_id.int == 0:
        raise SchedulingBaselineInvalidRequest("schedule_run_id must identify a run")
    # Story 4.3 owns the approved re-invocation and promotion body. This story
    # deliberately suspends on every call, before any candidate lookup or effect.
    raise SchedulingBaselineApprovalRequired("baseline promotion requires exact approval")


def scheduling_baseline_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_baseline_manifest(), handler=scheduling_baseline,
        request_type=SchedulingBaselineRequestV1, error_type=SchedulingBaselineError,
        retryable_error_codes=frozenset({"invalid_query"}), required_role="planner",
        required_feature_policy=SCHEDULING_BASELINE_POLICY, model_facing_view=lambda result: result,
    )


__all__ = ["SchedulingBaselineApprovalRequired", "SchedulingBaselineError", "SchedulingBaselineRequestV1", "scheduling_baseline", "scheduling_baseline_manifest", "scheduling_baseline_module"]
