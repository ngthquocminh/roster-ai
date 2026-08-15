"""Governed production of exact schedule metrics and their evidence locators."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal, Mapping
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
    CalculationDimensionError,
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
    "filters:task_and_family_only": (
        "AUTHORITATIVE. task_id and family are pushed into the query so the row bound is "
        "tested against the matching subset. "
        "NOT COVERED: the time window, which the adapter can only express as containment "
        "(start_minute_gte/end_minute_lte) and not as overlap; pushing it down would drop "
        "partially-overlapping rows and yield a wrong number carrying a valid locator."
    ),
    "units:no_volume_to_minutes_conversion": (
        "AUTHORITATIVE. headcount demand yields minutes and volume demand yields units; the "
        "two are never multiplied together or reported under one unit. "
        "NOT COVERED: converting volume to minutes, which needs a rate. The only rate in the "
        "projection is QualificationRefV1.rate -- per worker, per task -- so the conversion "
        "depends on an assignment and belongs to Epic 3's solver, not to a read model."
    ),
    "volume:uniform_within_interval": (
        "COVERS restricting a volume demand row to a requested window by pro-rating it across "
        "the row's own interval. "
        "NOT COVERED: any non-uniform intra-interval distribution; the source states one "
        "quantity per interval and carries no shape within it."
    ),
    "dimension:fail_closed_on_unit_miss": (
        "AUTHORITATIVE. When demand rows exist for the task and window but none carry the unit "
        "the metric reports, the call FAILS rather than returning a zero. Without this a "
        "dimension miss is indistinguishable from a proven-empty set and renders as a supported "
        "zero carrying no locator -- a wrong answer wearing valid grounding. "
        "NOT COVERED: judging whether the planner's question was reasonable. Asking about "
        "staffing on an outbound task is valid and is answered from assignments; only the "
        "demand-side metric is dimension-bound."
    ),
    "evidence:consumed_rows_only": (
        "AUTHORITATIVE. Every locator names a row folded into the value, and consumed_row_count "
        "reports how many were. "
        "NOT COVERED: an empty match set carries no locator -- EvidenceRefV1 addresses records, "
        "and absence has no record_id. The gate reads consumed_row_count to tell a correct zero "
        "from a calculator fault."
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


class MetricDimensionMismatchError(SchedulingComputeError):
    """Demand exists here but not in the unit this metric reports.

    RETRYABLE on purpose, unlike every other terminal failure in this module.
    The arguments are not malformed and nothing is broken -- the model picked a
    metric whose dimension the data cannot answer, and the message names the one
    that can. That is precisely the "fix your arguments and reissue" case
    `invalid_query` exists for, and re-issuing is cheap because the rows are
    already drained. Contrast the timeout, which Task 8 made non-retryable
    because reissuing it burns the very budget it was protecting.
    """

    code = "metric_dimension_mismatch"


ERROR_CODES = (
    "scenario_not_found", "version_mismatch", "site_mismatch",
    "invalid_query", "metric_dimension_mismatch", "calculation_failed",
    "budget_exhausted",
)


@dataclass(frozen=True)
class SchedulingComputeRequestV1:
    metric: MetricV1
    arguments: ClaimArgumentsV1
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingComputeResultV1:
    """TRUSTED result. Reaches the grounding gate whole; the model sees only
    `SchedulingComputeModelViewV1`.

    `consumed_row_count` is the completeness proof: the number of rows the
    calculator folded into `value`. Without it the gate cannot tell a
    legitimately empty match set from a calculator that consumed rows and
    emitted no locator -- one is a correct zero, the other is an application
    fault, and they must not share a failure state.
    """

    metric: MetricV1
    arguments: ClaimArgumentsV1
    value: int | float
    unit: GroundingUnitV1
    evidence_refs: tuple[EvidenceRefV1, ...]
    scenario_version_id: UUID
    result_id: str
    consumed_row_count: int = 0
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingComputeModelViewV1:
    """What the MODEL sees when this capability returns.

    It carries no quantity -- no value, no row count, no evidence refs. The
    model's only jobs are to pick a metric, pass arguments, and cite
    `result_id`; the displayed number travels the trusted path (handler ->
    `tool_result_sink` -> gate -> claim) and never passes through the model.

    `matched` is deliberately qualitative -- a count is a quantity, and "there
    are 8 demand rows" is itself an unlocated numerical claim.

    This narrows what THIS capability reveals; it does not establish a repo-wide
    "the model never sees a number" invariant. `scheduling_inspect` hands the
    model rows and counts by design, and rehydrated history carries prior claim
    values. Grounding rests on the gate refusing to render an unverified number,
    not on the model's ignorance.
    """

    result_id: str
    metric: MetricV1
    unit: GroundingUnitV1
    matched: Literal["none", "some"]
    schema_version: str = SCHEMA_VERSION


def _model_view(result: SchedulingComputeResultV1) -> SchedulingComputeModelViewV1:
    return SchedulingComputeModelViewV1(
        result_id=result.result_id,
        metric=result.metric,
        unit=result.unit,
        matched="some" if result.consumed_row_count else "none",
    )


def derive_result_id(
    metric: MetricV1, arguments: ClaimArgumentsV1, scenario_version_id: UUID
) -> str:
    """RFC 8785 (JCS) canonical SHA-256, valid for this restricted shape only.

    JCS conformance here rests on three properties and one restriction, stated
    so a later reader can check rather than trust:

    * key ordering -- `sort_keys=True` orders by Unicode code point, which
      equals JCS's UTF-16 code-unit ordering for every key below U+10000. All
      keys are ASCII field names.
    * literals/whitespace -- `separators=(",", ":")` gives JCS's compact form.
    * encoding -- `ensure_ascii=False` plus UTF-8 is JCS's serialization.
    * RESTRICTION -- JCS number serialization (ECMAScript `Number::toString`)
      is NOT implemented, so the payload must contain no float. Asserted below
      rather than assumed: this identifier binds a model citation to trusted
      evidence, and a silent shape change here would silently change identity.
    """
    payload = {
        "arguments": asdict(arguments),
        "metric": metric,
        "scenario_version_id": str(scenario_version_id),
    }
    if _contains_float(payload):
        raise InvalidQueryError(
            "result_id payload must contain no float; JCS number form is not implemented"
        )
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(item) for item in value)
    return False


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
        budget_limit=settings.scheduling_compute_row_limit,
        timeout_seconds=settings.scheduling_compute_timeout_seconds,
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
    except CalculationDimensionError as exc:
        raise MetricDimensionMismatchError(str(exc)) from exc
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
        consumed_row_count=calculated.consumed_row_count,
    )


def scheduling_compute_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_compute_manifest(), handler=scheduling_compute,
        request_type=SchedulingComputeRequestV1,
        error_type=SchedulingComputeError,
        retryable_error_codes=frozenset({"invalid_query", "metric_dimension_mismatch"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_COMPUTE_POLICY,
        # The model gets a receipt, never the number. See
        # SchedulingComputeModelViewV1 for why `matched` is qualitative.
        model_facing_view=_model_view,
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "EVALUATION_FIXTURES", "SCHEDULING_COMPUTE_POLICY",
    "SCOPE_CONTROLS", "BudgetExhaustedError", "CalculationFailedError",
    "InvalidQueryError", "MetricDimensionMismatchError", "ScenarioNotFoundError",
    "SchedulingComputeError",
    "SchedulingComputeModelViewV1",
    "SchedulingComputeRequestV1", "SchedulingComputeResultV1", "SiteMismatchError",
    "VersionMismatchError", "derive_result_id", "scheduling_compute",
    "scheduling_compute_manifest", "scheduling_compute_module",
]
