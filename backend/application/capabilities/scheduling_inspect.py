"""Governed inspection of normalized scenario facts.

"Saved metrics" means the persisted counts/checksum metadata on
``ScenarioOverviewV1``. This capability never computes a metric.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from application.capabilities.deps import AgentDepsV1
from application.capabilities.vocabulary import RiskClassV1
from application.ports.scenario_projection import GroupQueryV1
from application.use_cases.read_scenario_facts import (
    ScenarioFactGroupV1,
    read_scenario_facts,
)
from settings import default_settings

SCHEMA_VERSION = "1"
CAPABILITY_NAME = "scheduling_inspect"
EVALUATION_FIXTURES = (
    "evals/golden/scheduling_inspect/wednesday-demand.json",
    "evals/golden/scheduling_inspect/wednesday-assignments.json",
    "evals/golden/scheduling_inspect/wednesday-workers.json",
    "evals/golden/scheduling_inspect/wednesday-constraints.json",
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


@dataclass(frozen=True)
class InspectCapabilityManifest:
    capability_name: str
    capability_version: str
    input_schema_ref: str
    output_schema_ref: str
    risk_class: RiskClassV1
    permission: str
    scope: str
    version_semantics: str
    idempotency_semantics: str
    budget_limit: int
    timeout_seconds: float
    approval_policy: str
    audit_mapping: str
    evidence_mapping: str
    errors: tuple[str, ...]
    evaluation_fixtures: tuple[str, ...]


def scheduling_inspect_manifest() -> InspectCapabilityManifest:
    settings = default_settings()
    return InspectCapabilityManifest(
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
        errors=("scenario_not_found", "version_mismatch", "invalid_query"),
        evaluation_fixtures=EVALUATION_FIXTURES,
    )


def scheduling_inspect(
    deps: AgentDepsV1, request: SchedulingInspectRequestV1
) -> SchedulingInspectResultV1:
    query = GroupQueryV1(
        cursor=request.cursor,
        limit=min(request.limit, scheduling_inspect_manifest().budget_limit),
        sort=request.sort,
        order=request.order,
        filters=request.filters,
    )
    value = read_scenario_facts(
        deps.projection_reader,
        deps.connection,
        scenario_id=deps.scenario_id,
        group=request.group,
        query=query,
    )
    if value is None:
        raise LookupError("scenario_not_found")
    if value.scenario_version_id != deps.scenario_version_id:
        raise ValueError("version_mismatch")
    if request.group == "overview":
        item = asdict(value)
        return SchedulingInspectResultV1(
            group=request.group,
            scenario_id=str(value.scenario_id),
            scenario_version_id=str(value.scenario_version_id),
            site_id=str(value.site_id),
            items=(item,),
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


__all__ = [
    "CAPABILITY_NAME", "InspectCapabilityManifest", "SchedulingInspectRequestV1",
    "SchedulingInspectResultV1", "scheduling_inspect", "scheduling_inspect_manifest",
]
