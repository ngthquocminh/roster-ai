"""Validate an explicit, bounded optimization command without performing writes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from application.contracts.agent_runtime import AgentBudgetV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_optimize"
SCHEDULING_OPTIMIZE_POLICY = "scheduling_optimize_enabled"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_optimize/valid.json",
    "evals/golden/scheduling_optimize/replay.json",
    "evals/golden/scheduling_optimize/version-bound.json",
    "evals/golden/scheduling_optimize/key-boundary.json",
)

SCOPE_CONTROLS: Mapping[str, str] = {
    "authority:trusted_transport": (
        "COVERS actor, site, policy, compute risk, and explicit-run authority from trusted "
        "application dependencies and grant context. NOT COVERED: audit:owned_by_epic_4"
    ),
    "versions:proposal_and_baseline": (
        "COVERS the proposal resource-version input and delegates immutable snapshot checks to "
        "enqueue_compute. NOT COVERED: versions:baseline_schedule_version_unsupplied_until_epic_4"
    ),
    "progress:acknowledgement_only": (
        "COVERS validation of one durable-run request. NOT COVERED: "
        "progress:run_progress_surface_owned_by_story_3_7"
    ),
    "persistence:application_orchestrator": (
        "COVERS a validated trusted result only. NOT COVERED: writes; the route-owned "
        "application transaction invokes enqueue_compute."
    ),
}


class SchedulingOptimizeError(CapabilityError):
    code = "optimize_failed"


class InvalidRunRequestError(SchedulingOptimizeError):
    code = "invalid_query"


class BudgetExhaustedError(SchedulingOptimizeError):
    code = "budget_exhausted"


ERROR_CODES = ("optimize_failed", "invalid_query", "budget_exhausted")


@dataclass(frozen=True)
class SchedulingOptimizeRequestV1:
    proposal_id: UUID
    expected_resource_version: int
    idempotency_key: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingOptimizeDepsV1:
    actor_id: UUID
    site_id: UUID
    remaining_budget: AgentBudgetV1


@dataclass(frozen=True)
class SchedulingOptimizeResultV1:
    proposal_id: UUID
    expected_resource_version: int
    idempotency_key: str
    actor_id: UUID
    site_id: UUID
    capability_version: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingOptimizeModelViewV1:
    proposal_id: UUID
    expected_resource_version: int
    schema_version: str = SCHEMA_VERSION


def _model_view(result: SchedulingOptimizeResultV1) -> SchedulingOptimizeModelViewV1:
    return SchedulingOptimizeModelViewV1(
        proposal_id=result.proposal_id,
        expected_resource_version=result.expected_resource_version,
    )


def scheduling_optimize_manifest() -> CapabilityManifestV1:
    from settings import default_settings

    settings = default_settings()
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref=(
            "application.capabilities.scheduling_optimize.SchedulingOptimizeRequestV1"
        ),
        output_schema_ref=(
            "application.capabilities.scheduling_optimize.SchedulingOptimizeResultV1"
        ),
        risk_class="compute",
        permission="schedule_run:create",
        scope="current_actor/current_site/exact_proposal_version",
        version_semantics="the command pins one proposal resource version before snapshotting",
        idempotency_semantics=(
            "replay is scoped by actor, site, enqueue-compute operation, key, and canonical body"
        ),
        budget_limit=settings.site_max_concurrent_runs,
        timeout_seconds=settings.solver_wall_time_limit_seconds,
        approval_policy="none",
        audit_mapping=(
            "future audit envelope: actor, site, proposal/version, capability version, and run id"
        ),
        evidence_mapping="immutable proposal version and run snapshot version bindings",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def scheduling_optimize(
    deps: SchedulingOptimizeDepsV1,
    request: SchedulingOptimizeRequestV1,
    manifest: CapabilityManifestV1 | None = None,
) -> SchedulingOptimizeResultV1:
    resolved_manifest = manifest or scheduling_optimize_manifest()
    if (
        deps.remaining_budget.tool_calls_limit is not None
        and deps.remaining_budget.tool_calls_limit <= 0
    ):
        raise BudgetExhaustedError("no tool-call budget remains for this run")
    if request.proposal_id.int == 0:
        raise InvalidRunRequestError("proposal_id must identify a proposal")
    if request.expected_resource_version < 1:
        raise InvalidRunRequestError("expected_resource_version must be positive")
    if not request.idempotency_key or len(request.idempotency_key) > 40:
        raise InvalidRunRequestError("idempotency_key must contain 1 to 40 characters")
    return SchedulingOptimizeResultV1(
        proposal_id=request.proposal_id,
        expected_resource_version=request.expected_resource_version,
        idempotency_key=request.idempotency_key,
        actor_id=deps.actor_id,
        site_id=deps.site_id,
        capability_version=resolved_manifest.capability_version,
    )


def scheduling_optimize_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_optimize_manifest(),
        handler=scheduling_optimize,
        request_type=SchedulingOptimizeRequestV1,
        error_type=SchedulingOptimizeError,
        retryable_error_codes=frozenset({"invalid_query"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_OPTIMIZE_POLICY,
        model_facing_view=_model_view,
    )


__all__ = [
    "BudgetExhaustedError",
    "InvalidRunRequestError",
    "SchedulingOptimizeRequestV1",
    "SchedulingOptimizeDepsV1",
    "SchedulingOptimizeResultV1",
    "scheduling_optimize",
    "scheduling_optimize_manifest",
    "scheduling_optimize_module",
]
