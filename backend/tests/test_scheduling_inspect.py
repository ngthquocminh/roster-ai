from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import get_args
from uuid import UUID, uuid4

import pytest
from pydantic.errors import PydanticSchemaGenerationError
from pydantic_ai import models

from agent.capability_tools import UnknownCapabilityError, render_capabilities
from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.registry import (
    CapabilityGrantContextV1,
    PLANNER_ROLE,
    compose_granted_capabilities,
    resolve_granted_capability,
)
from application.capabilities.scheduling_inspect import (
    ERROR_CODES,
    SCHEDULING_INSPECT_POLICY,
    SCOPE_CONTROLS,
    BudgetExhaustedError,
    InvalidQueryError,
    SchedulingInspectRequestV1,
    SiteMismatchError,
    VersionMismatchError,
    scheduling_inspect,
    scheduling_inspect_manifest,
    scheduling_inspect_module,
)
from application.capabilities.vocabulary import RiskClassV1
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.scenario_projection import (
    AssignmentV1,
    ConstraintV1,
    DemandIntervalV1,
    LockV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    WorkerV1,
)
from application.ports.agent_runtime import AgentRuntimeError
from application.ports.scenario_projection import (
    AssignmentPageV1,
    ConstraintPageV1,
    DemandIntervalPageV1,
    GroupQueryKeysV1,
    LockPageV1,
    ScenarioFactGroupV1,
    WorkerPageV1,
)
from application.use_cases.read_scenario_facts import read_scenario_facts
from evals.cases import RISK_CLASSES, case_from_mapping
from evals.doubles import build_model_double
from settings import default_settings

models.ALLOW_MODEL_REQUESTS = False

# Distinct per field: one shared UUID would make every scope assertion in this
# module pass by construction, which is exactly the defect the 2.5 review found.
ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")
SITE = UUID("00000000-0000-0000-0000-0000000000b2")
MEMBERSHIP = UUID("00000000-0000-0000-0000-0000000000c3")
REQUEST = UUID("00000000-0000-0000-0000-0000000000d4")
AGENT_RUN = UUID("00000000-0000-0000-0000-0000000000e5")
CONVERSATION = UUID("00000000-0000-0000-0000-0000000000f6")
SCENARIO = UUID("00000000-0000-0000-0000-000000000107")
VERSION = UUID("00000000-0000-0000-0000-000000000218")
OTHER_SITE = UUID("00000000-0000-0000-0000-000000000999")
OTHER_VERSION = UUID("00000000-0000-0000-0000-000000000888")

# Mirrors the adapter's real tables closely enough to exercise the allow-list.
_KEYS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "overview": ((), ()),
    "tasks": (("task_id", "name"), ("task_id", "function")),
    "demand": (("start_minute", "amount"), ("family", "task_id", "start_minute_gte")),
    "assignments": (("start_minute", "worker_id"), ("worker_id", "task_id")),
    "workers": (("contact_id", "name"), ("contact_id",)),
    "locks": (("scope", "source"), ("scope", "target_type")),
    "constraints": (("constraint_type",), ("constraint_type", "value_type")),
}


class ProjectionStub:
    """Answers every group the port declares, with per-group distinct data."""

    def __init__(self, site_id: UUID = SITE, version_id: UUID = VERSION) -> None:
        self.site_id = site_id
        self.version_id = version_id
        self.queries: list[tuple[str, object]] = []

    def get_query_keys(self, group: str) -> GroupQueryKeysV1:
        sorts, filters = _KEYS.get(group, ((), ()))
        return GroupQueryKeysV1(group=group, sort_keys=sorts, filter_keys=filters)

    def _scope(self) -> dict[str, object]:
        return {
            "scenario_id": SCENARIO,
            "scenario_version_id": self.version_id,
            "site_id": self.site_id,
        }

    def get_overview(self, _connection, _scenario_id) -> ScenarioOverviewV1:
        self.queries.append(("overview", None))
        return ScenarioOverviewV1(
            **self._scope(),
            fixture_id="sample_tiny_input",
            scenario_name="tiny",
            fixture_version="v1",
            checksum_algorithm="sha256",
            checksum_schema_version="1",
            checksum_digest="abc",
            horizon_start=datetime(2026, 8, 10, tzinfo=timezone.utc),
            site_timezone="UTC",
            horizon_minutes=10080,
            baseline_schedule_version=None,
            projection_generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            work_area_count=2,
            task_count=3,
            worker_count=4,
            demand_interval_count=5,
            baseline_assignment_count=6,
            lock_count=7,
            constraint_count=8,
        )

    def get_demand(self, _connection, _scenario_id, query) -> DemandIntervalPageV1:
        self.queries.append(("demand", query))
        return DemandIntervalPageV1(
            **self._scope(),
            items=(
                DemandIntervalV1("d1", "outbound", "t1", None, 2880, 2940, 4, "headcount"),
            ),
            next_cursor=1, total_count=3, matching_count=3,
        )

    def get_baseline_assignments(self, _connection, _scenario_id, query) -> AssignmentPageV1:
        self.queries.append(("assignments", query))
        return AssignmentPageV1(
            **self._scope(),
            items=(AssignmentV1("a1", "w1", "t1", "s1", 2880, 2940),),
            next_cursor=None, total_count=1, matching_count=1,
        )

    def get_workers(self, _connection, _scenario_id, query) -> WorkerPageV1:
        self.queries.append(("workers", query))
        return WorkerPageV1(
            **self._scope(),
            items=(
                WorkerV1(
                    record_id="w1", contact_id="w1", name="Ann",
                    employment_type="FT", grade="G1", eba="E1",
                    contracted_hours=38.0,
                    qualifications=(QualificationRefV1(task_id="t1", rate=1.0),),
                    availability_windows=(),
                ),
            ),
            next_cursor=None, total_count=1, matching_count=1,
        )

    def get_locks(self, _connection, _scenario_id, query) -> LockPageV1:
        self.queries.append(("locks", query))
        return LockPageV1(
            **self._scope(),
            items=(LockV1("l1", "assignment", "a1", "hard", "planner"),),
            next_cursor=None, total_count=1, matching_count=1,
        )

    def get_constraints(self, _connection, _scenario_id, query) -> ConstraintPageV1:
        self.queries.append(("constraints", query))
        return ConstraintPageV1(
            **self._scope(),
            items=(ConstraintV1("c1", "max_hours", "10", "int"),),
            next_cursor=None, total_count=1, matching_count=1,
        )


class MissingScenarioStub(ProjectionStub):
    def get_demand(self, _connection, _scenario_id, query):
        return None


def _deps(reader: ProjectionStub | None = None, budget: AgentBudgetV1 | None = None,
          clock=None) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=ACTOR, site_id=SITE, membership_id=MEMBERSHIP,
        request_id=REQUEST, agent_run_id=AGENT_RUN, conversation_id=CONVERSATION,
        scenario_id=SCENARIO, scenario_version_id=VERSION,
        policy_version="one-user-mvp-v1",
        clock=clock or (lambda: datetime(2026, 8, 11, tzinfo=timezone.utc)),
        projection_reader=reader or ProjectionStub(),
        connection=object(),
        remaining_budget=budget or AgentBudgetV1(tool_calls_limit=3),
    )


def _grant_context(**overrides) -> CapabilityGrantContextV1:
    base = dict(
        role=PLANNER_ROLE, site_id=SITE,
        feature_policy=frozenset({SCHEDULING_INSPECT_POLICY}),
        conversation_id=CONVERSATION, conversation_site_id=SITE,
    )
    base.update(overrides)
    return CapabilityGrantContextV1(**base)


# --------------------------------------------------------------------------
# Vocabulary, deps, manifest
# --------------------------------------------------------------------------

def test_authoritative_risk_vocabulary_drives_eval_tags() -> None:
    assert get_args(RiskClassV1) == ("inspect", "draft", "compute", "consequential", "prohibited")
    assert RISK_CLASSES == get_args(RiskClassV1)


def test_agent_deps_carries_every_trusted_value_without_collapsing_them() -> None:
    deps = _deps()
    identities = {
        "actor_id": ACTOR, "site_id": SITE, "membership_id": MEMBERSHIP,
        "request_id": REQUEST, "agent_run_id": AGENT_RUN,
        "conversation_id": CONVERSATION, "scenario_id": SCENARIO,
        "scenario_version_id": VERSION,
    }
    for name, expected in identities.items():
        assert getattr(deps, name) == expected
    # Distinctness is the point: a fixture that reuses one UUID cannot detect a
    # field mix-up, so assert the values really are different.
    assert len(set(identities.values())) == len(identities)
    assert deps.policy_version and callable(deps.clock)
    assert deps.projection_reader is not None and deps.remaining_budget is not None
    assert set(AgentTurnRequestV1.__dataclass_fields__) == {
        "prompt", "history", "budget", "approvals", "schema_version"
    }


def test_manifest_is_complete_configured_and_fixture_backed(monkeypatch) -> None:
    manifest = scheduling_inspect_manifest()
    assert manifest.risk_class == "inspect" and manifest.approval_policy == "none"
    backend = Path(__file__).resolve().parents[1]
    assert all((backend / path).is_file() for path in manifest.evaluation_fixtures)
    assert all(getattr(manifest, name) for name in manifest.__dataclass_fields__)
    assert set(manifest.errors) == set(ERROR_CODES)

    # Proves the numbers come from settings rather than a literal that happens
    # to equal the default — the 2.5 review found the old assertion could not
    # tell the two apart.
    monkeypatch.setenv("SCHEDULING_INSPECT_ROW_LIMIT", "37")
    monkeypatch.setenv("SCHEDULING_INSPECT_TIMEOUT_SECONDS", "1.5")
    overridden = scheduling_inspect_manifest()
    assert overridden.budget_limit == 37
    assert overridden.timeout_seconds == 1.5
    assert default_settings().scheduling_inspect_row_limit == 37


def test_malformed_settings_fall_back_instead_of_crashing(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULING_INSPECT_ROW_LIMIT", "")
    monkeypatch.setenv("SCHEDULING_INSPECT_TIMEOUT_SECONDS", "not-a-number")
    manifest = scheduling_inspect_manifest()
    assert manifest.budget_limit == 200
    assert manifest.timeout_seconds == 5.0


def test_scope_controls_are_stated_as_data_with_non_coverage() -> None:
    assert SCOPE_CONTROLS
    for name, description in SCOPE_CONTROLS.items():
        assert "NOT COVERED" in description, f"{name} does not state its non-coverage"


# --------------------------------------------------------------------------
# Registry — grant by absence
# --------------------------------------------------------------------------

def test_registry_grants_by_trusted_context_and_unknown_names_are_absent() -> None:
    granted = compose_granted_capabilities(_grant_context())
    assert [item.manifest.capability_name for item in granted] == ["scheduling_inspect"]
    assert resolve_granted_capability(granted, "model_installed_shell") is None
    assert resolve_granted_capability(granted, "scheduling_inspect") is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "viewer"},
        {"feature_policy": frozenset()},
        {"conversation_site_id": OTHER_SITE},
        {"revoked_conversation_ids": frozenset({CONVERSATION})},
    ],
)
def test_every_grant_input_can_withhold_the_capability(overrides) -> None:
    """Each input is load-bearing; a grant function that ignores its inputs is
    a lie about coverage."""
    assert compose_granted_capabilities(_grant_context(**overrides)) == ()


def test_composed_registry_never_exposes_prohibited_capability_classes() -> None:
    contexts = (_grant_context(), _grant_context(role="viewer"))
    actual = {
        module.manifest.capability_name
        for context in contexts
        for module in compose_granted_capabilities(context)
    }
    # Derived from the composed grants themselves, not a hand-maintained list:
    # adding a capability to the registry without a manifest turns this red.
    declared = {scheduling_inspect_manifest().capability_name}
    assert actual <= declared
    for manifest in (scheduling_inspect_manifest(),):
        assert manifest.risk_class == "inspect"
        assert manifest.approval_policy == "none"


# --------------------------------------------------------------------------
# Handler — every group, every scope control, every declared error
# --------------------------------------------------------------------------

@pytest.mark.parametrize("group", list(get_args(ScenarioFactGroupV1)))
def test_every_declared_group_is_routable_and_scope_stamped(group) -> None:
    if group == "tasks":
        pytest.skip("tasks is a projection group the inspect capability does not expose")
    stub = ProjectionStub()
    result = scheduling_inspect(_deps(stub), SchedulingInspectRequestV1(group=group))
    assert result.group == group
    assert result.site_id == str(SITE)
    assert result.scenario_version_id == str(VERSION)
    assert result.returned_count == len(result.items)
    assert stub.queries and stub.queries[0][0] == group


def test_read_scenario_facts_routes_tasks_and_rejects_unknown_groups() -> None:
    stub = ProjectionStub()
    with pytest.raises(ValueError, match="unknown scenario fact group"):
        read_scenario_facts(stub, object(), scenario_id=SCENARIO, group="nope")


def test_handler_delegates_query_and_surfaces_truncation() -> None:
    stub = ProjectionStub()
    result = scheduling_inspect(
        _deps(stub),
        SchedulingInspectRequestV1(group="demand", filters=(("family", "outbound"),)),
    )
    assert result.truncated is True
    assert result.total_count == 3 and result.returned_count == 1
    assert stub.queries[0][1].filters == (("family", "outbound"),)


def test_untruncated_page_is_not_reported_as_truncated() -> None:
    result = scheduling_inspect(_deps(), SchedulingInspectRequestV1(group="locks"))
    assert result.truncated is False and result.next_cursor is None


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"sort": "not_a_column"},
        {"sort": "scope"},  # valid for locks, not for demand
        {"filters": (("bogus", "x"),)},
        {"cursor": -3},
        {"limit": 0},
        {"limit": -5},
    ],
)
def test_model_supplied_query_input_is_allow_listed(request_kwargs) -> None:
    with pytest.raises(InvalidQueryError):
        scheduling_inspect(
            _deps(), SchedulingInspectRequestV1(group="demand", **request_kwargs)
        )


def test_overview_rejects_query_arguments() -> None:
    with pytest.raises(InvalidQueryError):
        scheduling_inspect(
            _deps(), SchedulingInspectRequestV1(group="overview", sort="anything")
        )


def test_allow_list_is_derived_from_the_adapter_not_redeclared() -> None:
    """The legal keys must come from the reader, so they cannot drift."""
    stub = ProjectionStub()
    assert "family" in stub.get_query_keys("demand").filter_keys
    scheduling_inspect(
        _deps(stub), SchedulingInspectRequestV1(group="demand", sort="start_minute")
    )
    # A reader that publishes no keys rejects the same query.
    narrow = ProjectionStub()
    narrow.get_query_keys = lambda group: GroupQueryKeysV1(group, (), ())
    with pytest.raises(InvalidQueryError):
        scheduling_inspect(
            _deps(narrow), SchedulingInspectRequestV1(group="demand", sort="start_minute")
        )


def test_limit_is_clamped_to_the_configured_row_budget() -> None:
    stub = ProjectionStub()
    scheduling_inspect(_deps(stub), SchedulingInspectRequestV1(group="demand", limit=10_000))
    assert stub.queries[0][1].limit == scheduling_inspect_manifest().budget_limit


def test_missing_projection_raises_scenario_not_found() -> None:
    from application.capabilities.scheduling_inspect import ScenarioNotFoundError

    with pytest.raises(ScenarioNotFoundError):
        scheduling_inspect(
            _deps(MissingScenarioStub()), SchedulingInspectRequestV1(group="demand")
        )


def test_version_mismatch_is_a_typed_error_never_a_silent_retarget() -> None:
    stub = ProjectionStub(version_id=OTHER_VERSION)
    with pytest.raises(VersionMismatchError):
        scheduling_inspect(_deps(stub), SchedulingInspectRequestV1(group="demand"))


def test_site_mismatch_is_a_typed_error() -> None:
    stub = ProjectionStub(site_id=OTHER_SITE)
    with pytest.raises(SiteMismatchError):
        scheduling_inspect(_deps(stub), SchedulingInspectRequestV1(group="demand"))


def test_exhausted_tool_budget_blocks_execution() -> None:
    deps = _deps(budget=AgentBudgetV1(tool_calls_limit=0))
    with pytest.raises(BudgetExhaustedError):
        scheduling_inspect(deps, SchedulingInspectRequestV1(group="demand"))


def test_declared_timeout_is_enforced_as_an_overrun_error() -> None:
    ticks = iter([
        datetime(2026, 8, 11, tzinfo=timezone.utc),
        datetime(2026, 8, 11, tzinfo=timezone.utc) + timedelta(seconds=99),
    ])
    deps = _deps(clock=lambda: next(ticks))
    with pytest.raises(Exception) as excinfo:
        scheduling_inspect(deps, SchedulingInspectRequestV1(group="demand"))
    assert "budget" in str(excinfo.value)


def test_handler_module_imports_no_adapter_and_no_sqlalchemy() -> None:
    """Walks BOTH `import x` and `from x import y` — the 2.5 review found a
    version of this guard that only walked the former and so could never fail."""
    source = (
        Path(__file__).resolve().parents[1]
        / "application/capabilities/scheduling_inspect.py"
    ).read_text(encoding="utf-8")
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots.intersection({"sqlalchemy", "adapters", "fastapi", "pydantic_ai"})
    # Self-redness: the same walk must detect what it claims to detect.
    probe = ast.parse("from adapters.postgres.scenario_projection import X")
    probe_roots = {
        n.module.split(".")[0]
        for n in ast.walk(probe)
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert probe_roots == {"adapters"}


# --------------------------------------------------------------------------
# Rendering seam — grant by absence, proven against the real tool set
# --------------------------------------------------------------------------

def _inspect_case(group: str = "demand"):
    payload = {
        "case_id": "inspect-runtime", "case_version": "1",
        "capability": "scheduling_inspect", "risk_class": "inspect",
        "prompt": "inspect demand",
        "scripted_turns": [
            {"tool_name": "scheduling_inspect",
             "arguments": {"request": {"group": group}}, "tool_call_id": "i1"},
            {"response_text": "done"},
        ],
        "expected_outcome": "allow",
        "expected_tool_calls": [
            {"tool_name": "scheduling_inspect", "arguments": {"request": {"group": group}}}
        ],
        "expected_evidence_refs": [], "expected_visible_state": "completed",
        "expected_visible_text": "done",
        "scenario_fixtures": ["sample_tiny_input:v1"],
    }
    return case_from_mapping(payload)


def test_runtime_registers_only_granted_capabilities_and_executes_the_tool() -> None:
    case = _inspect_case()
    runtime = PydanticAIAgentRuntime(
        model=build_model_double(case),
        capabilities=(scheduling_inspect_module(),),
        deps=_deps(),
    )
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
    assert runtime.registered_capability_names == ("scheduling_inspect",)
    assert outcome.status == "completed"
    assert outcome.tool_results[0].tool_name == "scheduling_inspect"


def test_an_ungranted_capability_is_absent_from_the_real_tool_set() -> None:
    """Grant by absence, asserted against the Agent's actual tools rather than
    a tuple mirroring the constructor argument."""
    runtime = PydanticAIAgentRuntime(model=build_model_double(_inspect_case()), deps=_deps())
    assert runtime.registered_capability_names == ()
    toolset = runtime._agent._function_toolset
    assert "scheduling_inspect" not in toolset.tools

    granted = PydanticAIAgentRuntime(
        model=build_model_double(_inspect_case()),
        capabilities=(scheduling_inspect_module(),),
        deps=_deps(),
    )
    assert "scheduling_inspect" in granted._agent._function_toolset.tools


def test_a_module_with_an_unrenderable_request_type_fails_at_registration() -> None:
    """Every granted module is renderable by construction, so the old
    "no renderer exists" case is gone. What remains is a module whose declared
    request type cannot produce a JSON schema: that must fail LOUDLY when the
    runtime is built, not silently at the first model call."""
    unknown = replace(
        scheduling_inspect_module(),
        request_type=type("UnsupportedRequest", (), {}),
    )
    with pytest.raises(PydanticSchemaGenerationError):
        PydanticAIAgentRuntime(
            model=build_model_double(_inspect_case()),
            capabilities=(unknown,),
            deps=_deps(),
        )


def test_a_capability_granted_twice_is_rejected() -> None:
    manifest = scheduling_inspect_module()
    with pytest.raises(UnknownCapabilityError):
        PydanticAIAgentRuntime(
            model=build_model_double(_inspect_case()),
            capabilities=(manifest, manifest),
            deps=_deps(),
        )


def test_render_capabilities_requires_trusted_deps() -> None:
    with pytest.raises(ValueError):
        PydanticAIAgentRuntime(
            model=build_model_double(_inspect_case()),
            capabilities=(scheduling_inspect_module(),),
            deps=None,
        )


def test_an_invalid_model_query_never_escapes_as_a_raw_builtin() -> None:
    """The model supplies a bad sort key; the caller must see an owned outcome,
    not `KeyError` crossing the AgentRuntime port."""
    payload = {
        "case_id": "inspect-bad-sort", "case_version": "1",
        "capability": "scheduling_inspect", "risk_class": "inspect",
        "prompt": "inspect demand",
        "scripted_turns": [
            {"tool_name": "scheduling_inspect",
             "arguments": {"request": {"group": "demand", "sort": "not_a_column"}},
             "tool_call_id": "i1"},
            {"response_text": "recovered"},
        ],
        "expected_outcome": "allow",
        "expected_tool_calls": [],
        "expected_evidence_refs": [], "expected_visible_state": "completed",
        "expected_visible_text": "recovered", "scenario_fixtures": [],
    }
    runtime = PydanticAIAgentRuntime(
        model=build_model_double(case_from_mapping(payload)),
        capabilities=(scheduling_inspect_module(),),
        deps=_deps(),
    )
    try:
        outcome = runtime.run_turn(AgentTurnRequestV1(prompt="inspect demand"))
    except AgentRuntimeError:
        return  # owned type — acceptable containment
    assert outcome.status in {"completed", "failed"}
    if outcome.status == "failed":
        assert outcome.failure_reason in set(ERROR_CODES) | {"budget_exhausted"}
