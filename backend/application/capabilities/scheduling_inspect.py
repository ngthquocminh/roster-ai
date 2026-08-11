"""Governed inspection of normalized scenario facts.

"Saved metrics" means the persisted counts/checksum metadata on
``ScenarioOverviewV1``. This capability never computes a metric.

Scope enforcement, stated as data rather than prose — see ``SCOPE_CONTROLS``.
The connection is the authoritative site control (it is opened site-scoped by
``api/deps.site_context``); the site check here is defence-in-depth and cannot
detect an unscoped connection, only a page that disagrees with the trusted pin.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Mapping

from application.capabilities.deps import AgentDepsV1
from application.capabilities.module import CapabilityModuleV1
from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1
from application.ports.scenario_projection import GroupQueryV1
from application.use_cases.read_scenario_facts import (
    ScenarioFactGroupV1,
    read_scenario_facts,
)

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_inspect"
SCHEDULING_INSPECT_POLICY = "scheduling_inspect_enabled"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_inspect/wednesday-demand.json",
    "evals/golden/scheduling_inspect/wednesday-assignments.json",
    "evals/golden/scheduling_inspect/wednesday-workers.json",
    "evals/golden/scheduling_inspect/wednesday-constraints.json",
    "evals/golden/scheduling_inspect/wednesday-locks.json",
)

# What each scope control does and does NOT cover. Scope as data (the
# ALLOWED_LEAKS pattern), so a claim cannot quietly outlive its enforcement.
SCOPE_CONTROLS: Mapping[str, str] = {
    "site:connection": (
        "AUTHORITATIVE. The connection is opened site-scoped by "
        "api/deps.site_context; every read inherits that bound. NOT COVERED: "
        "this module cannot verify the connection it was handed is scoped."
    ),
    "site:page_check": (
        "DEFENCE-IN-DEPTH. Raises site_mismatch when a returned page disagrees "
        "with the trusted deps pin. NOT COVERED: a uniformly wrong-but-"
        "consistent site, which only the connection control can prevent."
    ),
    "version:page_check": (
        "AUTHORITATIVE. Raises version_mismatch rather than silently "
        "retargeting (AR11). NOT COVERED: nothing — the pin is re-resolved "
        "server-side and every page carries its own version."
    ),
    "query:allow_list": (
        "AUTHORITATIVE. Sort/filter keys are allow-listed against the "
        "adapter's own published tables via get_query_keys, so the allow-list "
        "cannot drift from the interpretation. NOT COVERED: filter VALUE "
        "types, which the adapter compares natively."
    ),
}


class SchedulingInspectError(CapabilityError):
    """Typed capability failure. `code` is the manifest's error vocabulary."""

    code = "invalid_query"


class ScenarioNotFoundError(SchedulingInspectError):
    code = "scenario_not_found"


class VersionMismatchError(SchedulingInspectError):
    code = "version_mismatch"


class SiteMismatchError(SchedulingInspectError):
    code = "site_mismatch"


class InvalidQueryError(SchedulingInspectError):
    code = "invalid_query"


class BudgetExhaustedError(SchedulingInspectError):
    code = "budget_exhausted"


ERROR_CODES = (
    "scenario_not_found",
    "version_mismatch",
    "site_mismatch",
    "invalid_query",
    "budget_exhausted",
)


@dataclass(frozen=True)
class SchedulingInspectRequestV1:
    group: ScenarioFactGroupV1
    cursor: int = 0
    limit: int = 50
    sort: str | None = None
    order: Literal["asc", "desc"] = "asc"
    filters: tuple[tuple[str, str | int], ...] = ()
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SchedulingInspectResultV1:
    group: ScenarioFactGroupV1
    scenario_id: str
    scenario_version_id: str
    site_id: str
    items: tuple[dict[str, object], ...]
    returned_count: int
    total_count: int
    matching_count: int
    next_cursor: int | None
    truncated: bool
    schema_version: str = SCHEMA_VERSION


def scheduling_inspect_manifest() -> CapabilityManifestV1:
    # Imported here, not at module scope: `application/**` must not depend on
    # process configuration to be importable, and the registry composes the
    # manifest once per run rather than once per tool call.
    from settings import default_settings

    settings = default_settings()
    return CapabilityManifestV1(
        capability_name=CAPABILITY_NAME,
        capability_version=SCHEMA_VERSION,
        input_schema_ref="application.capabilities.scheduling_inspect.SchedulingInspectRequestV1",
        output_schema_ref="application.capabilities.scheduling_inspect.SchedulingInspectResultV1",
        risk_class="inspect",
        permission="scenario:inspect",
        scope="current_site/current_scenario_version",
        version_semantics="result is pinned to the selected scenario version",
        idempotency_semantics="read-only and repeatable for an immutable version",
        budget_limit=settings.scheduling_inspect_row_limit,
        timeout_seconds=settings.scheduling_inspect_timeout_seconds,
        approval_policy="none",
        audit_mapping="agent run + tool call identifiers; no fact content",
        evidence_mapping="group/record fields and scenario version",
        errors=ERROR_CODES,
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def _validated_query(
    deps: AgentDepsV1,
    request: SchedulingInspectRequestV1,
    manifest: CapabilityManifestV1,
) -> GroupQueryV1:
    """Allow-list untrusted, model-supplied query input (AD-2).

    The legal keys come from the adapter's own published tables, so this guard
    can never become a second interpretation of source data (AD-4 / Trap 4).
    """
    keys = deps.projection_reader.get_query_keys(request.group)
    if request.sort is not None and request.sort not in keys.sort_keys:
        raise InvalidQueryError(
            f"sort {request.sort!r} is not valid for group {request.group!r}; "
            f"valid: {', '.join(keys.sort_keys) or 'none'}"
        )
    for name, _value in request.filters:
        if name not in keys.filter_keys:
            raise InvalidQueryError(
                f"filter {name!r} is not valid for group {request.group!r}; "
                f"valid: {', '.join(keys.filter_keys) or 'none'}"
            )
    if request.order not in ("asc", "desc"):
        raise InvalidQueryError(f"order must be 'asc' or 'desc', got {request.order!r}")
    if request.cursor < 0:
        raise InvalidQueryError(f"cursor must be >= 0, got {request.cursor}")
    if request.limit < 1:
        raise InvalidQueryError(f"limit must be >= 1, got {request.limit}")
    return GroupQueryV1(
        cursor=request.cursor,
        limit=min(request.limit, max(manifest.budget_limit, 1)),
        sort=request.sort,
        order=request.order,
        filters=request.filters,
    )


def scheduling_inspect(
    deps: AgentDepsV1,
    request: SchedulingInspectRequestV1,
    manifest: CapabilityManifestV1 | None = None,
) -> SchedulingInspectResultV1:
    resolved = manifest or scheduling_inspect_manifest()

    tool_calls_left = deps.remaining_budget.tool_calls_limit
    if tool_calls_left is not None and tool_calls_left <= 0:
        raise BudgetExhaustedError("no tool-call budget remains for this run")

    if request.group == "overview":
        if request.sort is not None or request.filters:
            raise InvalidQueryError("group 'overview' accepts no sort or filters")
        query = None
    else:
        query = _validated_query(deps, request, resolved)

    started_at = deps.clock()
    value = read_scenario_facts(
        deps.projection_reader,
        deps.connection,
        scenario_id=deps.scenario_id,
        group=request.group,
        query=query,
    )
    if value is None:
        raise ScenarioNotFoundError(f"scenario {deps.scenario_id} has no projection")

    # Detect-not-interrupt: a synchronous projection read is not cancellable, so
    # the declared timeout is enforced as an overrun error rather than a hard
    # cut. Recorded in SCOPE_CONTROLS' spirit; the run-level deadline in
    # AgentBudgetV1 remains the interrupting control.
    elapsed = (deps.clock() - started_at).total_seconds()
    if elapsed > resolved.timeout_seconds:
        raise SchedulingInspectError(
            f"inspection exceeded the {resolved.timeout_seconds}s budget "
            f"({elapsed:.2f}s)"
        )

    if value.scenario_version_id != deps.scenario_version_id:
        raise VersionMismatchError(
            f"page version {value.scenario_version_id} does not match the "
            f"pinned {deps.scenario_version_id}"
        )
    if value.site_id != deps.site_id:
        raise SiteMismatchError(
            f"page site {value.site_id} does not match the trusted "
            f"{deps.site_id}"
        )

    if request.group == "overview":
        return SchedulingInspectResultV1(
            group=request.group,
            scenario_id=str(value.scenario_id),
            scenario_version_id=str(value.scenario_version_id),
            site_id=str(value.site_id),
            items=(asdict(value),),
            returned_count=1,
            total_count=1,
            matching_count=1,
            next_cursor=None,
            truncated=False,
        )
    items = tuple(asdict(item) for item in value.items)
    return SchedulingInspectResultV1(
        group=request.group,
        scenario_id=str(value.scenario_id),
        scenario_version_id=str(value.scenario_version_id),
        site_id=str(value.site_id),
        items=items,
        returned_count=len(items),
        total_count=value.total_count,
        matching_count=value.matching_count,
        next_cursor=value.next_cursor,
        truncated=value.next_cursor is not None or len(items) < value.matching_count,
    )


def scheduling_inspect_module() -> CapabilityModuleV1:
    return CapabilityModuleV1(
        manifest=scheduling_inspect_manifest(),
        handler=scheduling_inspect,
        request_type=SchedulingInspectRequestV1,
        error_type=SchedulingInspectError,
        retryable_error_codes=frozenset({"invalid_query"}),
        required_role="planner",
        required_feature_policy=SCHEDULING_INSPECT_POLICY,
    )


__all__ = [
    "CAPABILITY_NAME", "ERROR_CODES", "SCHEDULING_INSPECT_POLICY",
    "InvalidQueryError", "BudgetExhaustedError", "SCOPE_CONTROLS",
    "ScenarioNotFoundError", "SchedulingInspectError",
    "SchedulingInspectRequestV1", "SchedulingInspectResultV1",
    "SiteMismatchError", "VersionMismatchError",
    "scheduling_inspect", "scheduling_inspect_manifest", "scheduling_inspect_module",
]
