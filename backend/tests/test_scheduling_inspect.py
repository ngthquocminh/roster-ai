from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

from pydantic_ai import models

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.registry import (
    CapabilityGrantContextV1,
    PLANNER_ROLE,
    SCHEDULING_INSPECT_POLICY,
    compose_granted_capabilities,
    resolve_granted_capability,
)
from application.capabilities.scheduling_inspect import (
    SchedulingInspectRequestV1,
    scheduling_inspect,
    scheduling_inspect_manifest,
)
from application.capabilities.vocabulary import RiskClassV1
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.scenario_projection import DemandIntervalV1
from application.ports.scenario_projection import DemandIntervalPageV1
from evals.cases import RISK_CLASSES, case_from_mapping
from evals.doubles import build_model_double
from settings import default_settings

models.ALLOW_MODEL_REQUESTS = False


class ProjectionStub:
    def __init__(self, identity):
        self.identity = identity
        self.queries = []

    def get_demand(self, _connection, scenario_id, query):
        self.queries.append((scenario_id, query))
        return DemandIntervalPageV1(
            scenario_id=self.identity, scenario_version_id=self.identity,
            site_id=self.identity,
            items=(DemandIntervalV1("d1", "outbound", "t1", None, 2880, 2940, 4, "headcount"),),
            next_cursor=1, total_count=3, matching_count=3,
        )


def _deps(reader=None):
    identity = uuid4()
    return AgentDepsV1(
        actor_id=identity, site_id=identity, membership_id=identity,
        request_id=identity, agent_run_id=identity, conversation_id=identity,
        scenario_id=identity, scenario_version_id=identity,
        policy_version="one-user-mvp-v1", clock=lambda: datetime.now(timezone.utc),
        projection_reader=reader or ProjectionStub(identity), connection=object(),
        remaining_budget=AgentBudgetV1(tool_calls_limit=3),
    )


def test_authoritative_risk_vocabulary_drives_eval_tags():
    assert get_args(RiskClassV1) == ("inspect", "draft", "compute", "consequential", "prohibited")
    assert RISK_CLASSES == get_args(RiskClassV1)


def test_agent_deps_contains_every_trusted_server_value():
    deps = _deps()
    for name in ("actor_id", "site_id", "membership_id", "request_id", "agent_run_id", "conversation_id", "scenario_id", "scenario_version_id", "policy_version", "clock", "projection_reader", "connection", "remaining_budget"):
        assert getattr(deps, name) is not None
    assert set(AgentTurnRequestV1.__dataclass_fields__) == {"prompt", "history", "budget", "approvals", "schema_version"}


def test_manifest_is_complete_configured_and_fixture_backed():
    manifest = scheduling_inspect_manifest()
    assert manifest.risk_class == "inspect" and manifest.approval_policy == "none"
    assert manifest.budget_limit == default_settings().scheduling_inspect_row_limit
    assert manifest.timeout_seconds == default_settings().scheduling_inspect_timeout_seconds
    backend = Path(__file__).resolve().parents[1]
    assert all((backend / path).is_file() for path in manifest.evaluation_fixtures)
    assert all(getattr(manifest, name) for name in manifest.__dataclass_fields__)


def test_registry_grants_by_trusted_context_and_unknown_names_are_absent():
    identity = uuid4()
    allowed = CapabilityGrantContextV1(PLANNER_ROLE, identity, frozenset({SCHEDULING_INSPECT_POLICY}), uuid4(), identity)
    granted = compose_granted_capabilities(allowed)
    assert [item.capability_name for item in granted] == ["scheduling_inspect"]
    assert resolve_granted_capability(granted, "model_installed_shell") is None
    denied = CapabilityGrantContextV1("viewer", identity, frozenset({SCHEDULING_INSPECT_POLICY}), uuid4(), identity)
    assert compose_granted_capabilities(denied) == ()


def test_handler_delegates_query_and_preserves_scope_and_truncation():
    deps = _deps()
    result = scheduling_inspect(deps, SchedulingInspectRequestV1(group="demand", filters=(("family", "outbound"),)))
    assert result.site_id == str(deps.site_id)
    assert result.scenario_version_id == str(deps.scenario_version_id)
    assert result.truncated is True and result.total_count == 3 and result.returned_count == 1
    assert deps.projection_reader.queries[0][1].filters == (("family", "outbound"),)
    tree = ast.parse(Path(__file__).resolve().parents[1].joinpath("application/capabilities/scheduling_inspect.py").read_text())
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not imports.intersection({"sqlalchemy", "adapters"})


def test_runtime_registers_only_application_granted_capabilities_and_executes_tool():
    deps = _deps()
    payload = {
        "case_id":"inspect-runtime", "case_version":"1", "capability":"scheduling_inspect", "risk_class":"inspect",
        "prompt":"inspect demand", "scripted_turns":[{"tool_name":"scheduling_inspect","arguments":{"request":{"group":"demand"}},"tool_call_id":"i1"},{"response_text":"done"}],
        "expected_outcome":"allow", "expected_tool_calls":[{"tool_name":"scheduling_inspect","arguments":{"request":{"group":"demand"}}}],
        "expected_evidence_refs":[], "expected_visible_state":"completed", "expected_visible_text":"done", "scenario_fixtures":["sample_tiny_input:v1"],
    }
    case = case_from_mapping(payload)
    runtime = PydanticAIAgentRuntime(model=build_model_double(case), capabilities=(scheduling_inspect_manifest(),), deps=deps)
    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
    assert runtime.registered_capability_names == ("scheduling_inspect",)
    assert outcome.status == "completed" and outcome.tool_results[0].tool_name == "scheduling_inspect"
    ungranted = PydanticAIAgentRuntime(model=build_model_double(case), deps=deps)
    assert ungranted.registered_capability_names == ()


def test_composed_registry_never_exposes_prohibited_capability_classes():
    identity = uuid4()
    contexts = (
        CapabilityGrantContextV1(PLANNER_ROLE, identity, frozenset({SCHEDULING_INSPECT_POLICY}), uuid4(), identity),
        CapabilityGrantContextV1("viewer", identity, frozenset(), uuid4(), identity),
    )
    actual = {manifest.capability_name for context in contexts for manifest in compose_granted_capabilities(context)}
    declared_allow_list = {scheduling_inspect_manifest().capability_name}
    assert actual <= declared_allow_list
    assert not actual.intersection({"sql", "shell", "credentials", "network", "identity_admin", "runtime_install"})
