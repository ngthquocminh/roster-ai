"""Governed production of exact schedule metrics and their evidence locators."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Mapping
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import (
    ClaimArgumentsV1,
    GroundingUnitV1,
    MetricV1,
)
from application.grounding.calculators import (
    CalculationArgumentsError,
    CalculationError,
    CalculationLimitError,
    CalculationScenarioNotFoundError,
    CalculationSiteMismatchError,
    CalculationVersionMismatchError,
    calculate_metric,
)

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_compute"
SCHEDULING_COMPUTE_POLICY = "scheduling_compute_enabled"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_compute/supported.json",
    "evals/golden/scheduling_compute/version-mismatch.json",
    "evals/golden/scheduling_compute/missing-evidence.json",
    "evals/golden/scheduling_compute/argument-mismatch.json",
)

SCOPE_CONTROLS: Mapping[str, str] = {
    "site:trusted_dependencies": (
        "AUTHORITATIVE. Every page must equal the server-owned site pin. "
        "NOT COVERED: construction of the site-scoped database connection."
    ),
    "version:immutable_pin": (
        "AUTHORITATIVE. Overview and every page must equal the selected immutable version. "
        "NOT COVERED: schedule/run versions, which do not exist until Epic 3."
    ),
    "paging:bounded_exhaustion": (
        "AUTHORITATIVE. matching_count is drained under an explicit row bound or the call fails. "
        "NOT COVERED: datasets larger than the configured bound; they fail closed."
    ),
}


class SchedulingComputeError(CapabilityError):
    code = "calculation_failed"


class ScenarioNotFoundError(SchedulingComputeError):
    code = "scenario_not_found"


class VersionMismatchError(SchedulingComputeError):
    code = "version_mismatch"


class SiteMismatchError(SchedulingComputeError):
    code = "site_mismatch"


class InvalidQueryError(SchedulingComputeError):
    code = "invalid_query"


class CalculationFailedError(SchedulingComputeError):
    code = "calculation_failed"


class BudgetExhaustedError(SchedulingComputeError):
    code = "budget_exhausted"


ERROR_CODES = (
    "scenario_not_found", "version_mismatch", "site_mismatch",
    "invalid_query", "calculation_failed", "budget_exhausted",
)


@dataclass(frozen=True)
class SchedulingComputeRequestV1:
    metric: MetricV1
    arguments: ClaimArgumentsV1
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingComputeResultV1:
    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID
    result_id: str
    schema_version: str = SCHEMA_VERSION


def derive_result_id(
    metric: MetricV1, arguments: ClaimArgumentsV1, scenario_version_id: UUID
) -> str:
    """RFC-8785 canonical SHA-256 for this restricted string/int/null shape."""
    payload = {
        "arguments": asdict(arguments),
        "metric": metric,
        "scenario_version_id": str(scenario_version_id),
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def scheduling_compute_manifest() -> CapabilityManifestV1:
    from settings import default_settings

    settings = default_settings()
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref="application.capabilities.scheduling_compute.SchedulingComputeRequestV1",
        output_schema_ref="application.capabilities.scheduling_compute.SchedulingComputeResultV1",
        risk_class="inspect",
        permission="scenario:inspect",
        scope="current_site/current_scenario_version",
        version_semantics="result and every evidence locator are pinned to the selected scenario version",
        idempotency_semantics="content-addressed and repeatable for an immutable version",
        budget_limit=settings.scheduling_inspect_row_limit,
        timeout_seconds=settings.scheduling_inspect_timeout_seconds,
        approval_policy="none",
        audit_mapping="agent run + tool call + deterministic result identifier; no hidden reasoning",
        evidence_mapping="exact consumed records, fields/ranges, checksum, and scenario version",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def scheduling_compute(
    deps: AgentDepsV1,
    request: SchedulingComputeRequestV1,
    manifest: CapabilityManifestV1 | None = None,
) -> SchedulingComputeResultV1:
    resolved = manifest or scheduling_compute_manifest()
    if deps.remaining_budget.tool_calls_limit is not None and deps.remaining_budget.tool_calls_limit <= 0:
        raise BudgetExhaustedError("no tool-call budget remains for this run")
    started_at = deps.clock()
    try:
        calculated = calculate_metric(
            deps.projection_reader, deps.connection,
            scenario_id=deps.scenario_id,
            scenario_version_id=deps.scenario_version_id,
            site_id=deps.site_id,
            metric=request.metric,
            arguments=request.arguments,
            page_size=min(50, resolved.budget_limit),
            max_rows=resolved.budget_limit,
        )
    except CalculationArgumentsError as exc:
        raise InvalidQueryError(str(exc)) from exc
    except CalculationScenarioNotFoundError as exc:
        raise ScenarioNotFoundError(str(exc)) from exc
    except CalculationVersionMismatchError as exc:
        raise VersionMismatchError(str(exc)) from exc
    except CalculationSiteMismatchError as exc:
        raise SiteMismatchError(str(exc)) from exc
    except (CalculationLimitError, CalculationError) as exc:
        raise CalculationFailedError(str(exc)) from exc
    elapsed = (deps.clock() - started_at).total_seconds()
    if elapsed > resolved.timeout_seconds:
        raise CalculationFailedError(
            f"calculation exceeded the {resolved.timeout_seconds}s budget ({elapsed:.2f}s)"
        )
    return SchedulingComputeResultV1(
        metric=calculated.metric,
        arguments=calculated.arguments,
        value=calculated.value,
        unit=calculated.unit,
        evidence_refs=calculated.evidence_refs,
        scenario_version_id=calculated.scenario_version_id,
        result_id=derive_result_id(
            calculated.metric, calculated.arguments, calculated.scenario_version_id
        ),
    )


def scheduling_compute_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_compute_manifest(), handler=scheduling_compute,
        request_type=SchedulingComputeRequestV1,
        error_type=SchedulingComputeError,
        retryable_error_codes=frozenset({"invalid_query"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_COMPUTE_POLICY,
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "EVALUATION_FIXTURES", "SCHEDULING_COMPUTE_POLICY",
    "SCOPE_CONTROLS", "BudgetExhaustedError", "CalculationFailedError",
    "InvalidQueryError", "ScenarioNotFoundError", "SchedulingComputeError",
    "SchedulingComputeRequestV1", "SchedulingComputeResultV1", "SiteMismatchError",
    "VersionMismatchError", "derive_result_id", "scheduling_compute",
    "scheduling_compute_manifest", "scheduling_compute_module",
]
