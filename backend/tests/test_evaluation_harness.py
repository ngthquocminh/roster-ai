"""Deterministic evaluation harness tests.

The default suite is intentionally unmarked and model requests are disabled at
module scope. Story 2.2 grows this file task by task; every assertion at the
runtime seam is on ShiftMind-owned outcomes.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic_ai import models

from agent.runtime import PydanticAIAgentRuntime, create_agent_runtime
from application.contracts.agent_runtime import AgentBudgetV1, AgentRunOutcomeV1, AgentTurnRequestV1
from application.capabilities.deps import AgentDepsV1
from application.capabilities.demonstration import demonstration_module
from application.capabilities.installed import installed_modules
from application.capabilities.scheduling_compute import scheduling_compute_module
from application.capabilities.scheduling_inspect import scheduling_inspect_module
from application.contracts.grounding import GroundedAnswerV1
from application.ports.scenario_projection import GroupQueryKeysV1
from evals.cases import (
    ExpectedToolCall,
    GoldenCase,
    case_from_mapping,
    load_case,
    load_cases,
)
from evals.doubles import build_model_double
from evals.evaluators import Evaluator, ToolRoutingEvaluator
from evals.report import (
    CaseEvaluation,
    _runtime_for_case,
    generate_demonstration_report,
    write_evaluation_report,
)
from scripts.evidence_binding import audit_evidence_file, resolve_bindings

models.ALLOW_MODEL_REQUESTS = False

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "evals" / "golden"
_HAS_LIVE_AGENT = bool(os.environ.get("AGENT_RUNTIME_API_KEY")) and os.environ.get(
    "AGENT_RUNTIME_MODEL", "test"
) != "test"


def _case_payload(*, risk_class: str = "inspect") -> dict[str, object]:
    return {
        "case_id": "schema-roundtrip",
        "case_version": "1",
        "capability": "demonstration",
        "risk_class": risk_class,
        "prompt": "Demonstrate alpha once.",
        "scripted_turns": [
            {
                "tool_name": "shiftmind_demonstration",
                "arguments": {"payload": {"label": "alpha", "repeat": 1}},
                "tool_call_id": "demo-1",
            },
            {"response_text": "tool said alpha"},
        ],
        "expected_outcome": "allow",
        "expected_tool_calls": [
            {
                "tool_name": "shiftmind_demonstration",
                "arguments": {"payload": {"label": "alpha", "repeat": 1}},
            }
        ],
        "expected_evidence_refs": [],
        "expected_visible_state": "completed",
        "expected_visible_text": "tool said alpha",
        "scenario_fixtures": [],
    }


def test_case_loader_round_trips_a_hand_written_json_file(tmp_path) -> None:
    path = tmp_path / "schema-roundtrip.json"
    path.write_text(json.dumps(_case_payload()), encoding="utf-8")

    case = load_case(path)

    assert isinstance(case, GoldenCase)
    assert case.case_id == "schema-roundtrip"
    assert case.risk_class == "inspect"
    assert case.scripted_turns[0].arguments["payload"]["repeat"] == 1
    assert case.expected_evidence_refs == ()


def test_case_loader_rejects_out_of_vocabulary_risk_class(tmp_path) -> None:
    path = tmp_path / "invalid-risk.json"
    path.write_text(
        json.dumps(_case_payload(risk_class="dangerous")), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="risk_class.*dangerous"):
        load_case(path)


def test_generated_double_runs_case_through_real_owned_runtime() -> None:
    case = case_from_mapping(_case_payload())
    outcome = _run_case(case)

    assert isinstance(outcome, AgentRunOutcomeV1)
    assert outcome.status == "completed"
    assert outcome.output_text == "tool said alpha"
    assert outcome.tool_results[0].tool_name == "shiftmind_demonstration"


def _run_case(case: GoldenCase) -> AgentRunOutcomeV1:
    identity = UUID("00000000-0000-0000-0000-000000000001")

    class ProjectionReader:
            # Mirrors the adapter's published keys for the groups these cases
            # use, so the capability's allow-list is exercised rather than
            # bypassed.
        _KEYS = {
                "demand": (("start_minute",), ("family", "task_id")),
                "assignments": (("start_minute",), ("worker_id", "task_id")),
                "workers": (("contact_id",), ("contact_id",)),
                "locks": (("scope",), ("scope",)),
                "constraints": (("constraint_type",), ("constraint_type",)),
        }

        def get_query_keys(self, group):
            sorts, filters = self._KEYS.get(group, ((), ()))
            return GroupQueryKeysV1(group=group, sort_keys=sorts, filter_keys=filters)

        def _page(self):
            return SimpleNamespace(
                scenario_id=identity, scenario_version_id=identity,
                site_id=identity, items=(), next_cursor=None,
                total_count=0, matching_count=0,
            )
        get_demand = lambda self, *_args: self._page()
        get_baseline_assignments = lambda self, *_args: self._page()
        get_workers = lambda self, *_args: self._page()
        get_locks = lambda self, *_args: self._page()
        get_constraints = lambda self, *_args: self._page()
        get_overview = lambda self, *_args: self._page()

    modules = {
        "scheduling_compute": (scheduling_compute_module(),),
        "scheduling_inspect": (scheduling_inspect_module(),),
    }.get(case.capability, (demonstration_module(),))
    kwargs = {
        "capabilities": modules,
        "deps": AgentDepsV1(
            actor_id=UUID(int=1), site_id=identity, membership_id=UUID(int=3),
            request_id=UUID(int=4), agent_run_id=UUID(int=5), conversation_id=UUID(int=6),
            scenario_id=UUID(int=7), scenario_version_id=identity,
            policy_version="one-user-mvp-v1", clock=lambda: datetime.now(timezone.utc),
            projection_reader=ProjectionReader(), connection=object(),
            remaining_budget=AgentBudgetV1(),
        ),
    }
    runtime = PydanticAIAgentRuntime(
        model=build_model_double(case),
        answer_type=(GroundedAnswerV1 if case.expected_grounding_outcome else None),
        **kwargs,
    )
    return runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))


def test_tool_routing_evaluator_passes_correct_route() -> None:
    case = case_from_mapping(_case_payload())
    evaluator: Evaluator = ToolRoutingEvaluator()

    verdict = evaluator.evaluate(case, _run_case(case))

    assert verdict.passed is True
    assert "matched" in verdict.reason


def test_tool_routing_evaluator_names_wrong_tool() -> None:
    executed = case_from_mapping(_case_payload())
    expected = replace(
        executed,
        expected_tool_calls=(
            ExpectedToolCall(
                tool_name="different_tool",
                arguments=executed.expected_tool_calls[0].arguments,
            ),
        ),
    )

    verdict = ToolRoutingEvaluator().evaluate(expected, _run_case(executed))

    assert verdict.passed is False
    assert "tool name" in verdict.reason
    assert "different_tool" in verdict.reason


def test_tool_routing_evaluator_names_wrong_arguments() -> None:
    executed = case_from_mapping(_case_payload())
    expected = replace(
        executed,
        expected_tool_calls=(
            ExpectedToolCall(
                tool_name="shiftmind_demonstration",
                arguments={"payload": {"label": "beta", "repeat": 1}},
            ),
        ),
    )

    verdict = ToolRoutingEvaluator().evaluate(expected, _run_case(executed))

    assert verdict.passed is False
    assert "arguments" in verdict.reason
    assert "beta" in verdict.reason


def _refusal_payload(*, outcome: str = "refuse") -> dict[str, object]:
    """A case whose model answers in text and routes no tool at all."""
    payload = _case_payload()
    payload.update(
        {
            "case_id": f"schema-{outcome}",
            "risk_class": "prohibited" if outcome == "refuse" else "inspect",
            "prompt": "Do something this capability must not do.",
            "scripted_turns": [{"response_text": "I cannot help with that."}],
            "expected_outcome": outcome,
            "expected_tool_calls": [],
            "expected_visible_text": "I cannot help with that.",
        }
    )
    return payload


@pytest.mark.parametrize("outcome", ["refuse", "clarify"])
def test_tool_routing_evaluator_passes_when_no_tool_is_routed(outcome: str) -> None:
    case = case_from_mapping(_refusal_payload(outcome=outcome))

    verdict = ToolRoutingEvaluator().evaluate(case, _run_case(case))

    assert verdict.passed is True
    assert outcome in verdict.reason
    assert "no tool call" in verdict.reason


@pytest.mark.parametrize("outcome", ["refuse", "clarify"])
def test_tool_routing_evaluator_fails_when_a_forbidden_tool_is_routed(
    outcome: str,
) -> None:
    """NFR28's 100% protected-class rule depends on this branch biting."""
    executed = case_from_mapping(_case_payload(risk_class="prohibited"))
    expected = replace(
        case_from_mapping(_refusal_payload(outcome=outcome)),
        expected_tool_calls=(),
    )

    verdict = ToolRoutingEvaluator().evaluate(expected, _run_case(executed))

    assert verdict.passed is False
    assert outcome in verdict.reason
    assert "shiftmind_demonstration" in verdict.reason


def test_case_loader_rejects_an_unknown_field() -> None:
    payload = _case_payload()
    payload["scenario_fixture"] = ["sample_tiny_input:v1"]

    with pytest.raises(ValueError, match="unknown field.*scenario_fixture"):
        case_from_mapping(payload)


def test_case_loader_requires_scenario_fixtures_rather_than_defaulting_it() -> None:
    payload = _case_payload()
    del payload["scenario_fixtures"]

    with pytest.raises(ValueError, match="scenario_fixtures"):
        case_from_mapping(payload)


def test_all_version_controlled_golden_cases_pass_deterministically() -> None:
    """Normal CI path: every committed case, real adapter, zero network."""
    for case in load_cases(GOLDEN_DIR):
        outcome = _run_case(case)
        verdict = ToolRoutingEvaluator(run_source="double").evaluate(
            case, outcome
        )
        assert verdict.passed, f"{case.case_id}: {verdict.reason}"
        assert verdict.authoritative is True
        assert outcome.status == case.expected_visible_state
        assert (outcome.output_text or "") == case.expected_visible_text


def test_seed_cases_cover_allow_and_consequential_approval() -> None:
    cases = load_cases(GOLDEN_DIR)
    # Lower bound, not an equality: this dataset is designed to grow. Stories
    # 2.9, 3.10-3.12 and 4.5-4.6 contribute their own cases to this same
    # directory (see backend/evals/README.md), so an exact count would turn the
    # first real contribution red. The coverage assertions below carry the
    # intent that matters — Story 2.2 seeds these two permanent historical
    # cases even though module installation remains removable by composition.
    assert len(cases) >= 2, "Story 2.2's two schema-proof cases must remain"
    assert any(
        case.expected_outcome == "allow" and case.risk_class == "inspect"
        for case in cases
    )
    assert any(
        case.expected_outcome == "allow"
        and case.risk_class == "consequential"
        and case.expected_visible_state == "suspended"
        for case in cases
    )
    assert "demonstration" in {case.capability for case in cases}


# NFR28's floor reads on ALLOWED PRODUCT capabilities (prd.md:191-202 lists the
# six-capability MVP catalogue). Capabilities present in the dataset that are not
# product capabilities are exempt — but the exemption is declared here with its
# reason, never inferred from a name at the point of use.
MVP_PRODUCT_CAPABILITIES = {"scheduling_compute", "scheduling_inspect"}
NON_PRODUCT_CAPABILITIES = {
    # A harness-proof module, not a product capability: Story 2.2 seeded exactly
    # two schema cases and epics.md:1527 forbids padding a dataset to clear a
    # threshold. Its installation is removable by composition; the cases are not.
    "demonstration",
}


def test_every_capability_meets_the_nfr28_four_case_floor() -> None:
    """NFR28: at least four golden cases per allowed product capability.

    Without this, three of the four scheduling_inspect cases could be deleted
    silently. The floor must also keep reading on capabilities that do not exist
    yet, so an unclassified capability fails rather than slipping past.
    """
    cases = load_cases(GOLDEN_DIR)
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.capability] = counts.get(case.capability, 0) + 1

    # The exemption is asserted, not assumed: a capability cannot be both a
    # product capability and exempt from the floor that governs product ones.
    assert MVP_PRODUCT_CAPABILITIES.isdisjoint(NON_PRODUCT_CAPABILITIES)

    # A new capability contributing cases must be classified as product or
    # non-product. Without this the floor would silently ignore it entirely.
    unclassified = set(counts) - MVP_PRODUCT_CAPABILITIES - NON_PRODUCT_CAPABILITIES
    assert not unclassified, (
        f"classify these capabilities as product or non-product: {sorted(unclassified)}"
    )

    below_floor = {
        name: count
        for name, count in counts.items()
        if name in MVP_PRODUCT_CAPABILITIES and count < 4
    }
    assert not below_floor, below_floor


def test_every_golden_file_validates_and_malformed_contribution_fails(tmp_path) -> None:
    # Enumerate and read the files independently of the loader, then compare
    # identities. Counting the loader's own rglob against the same rglob can
    # never fail, so it would prove nothing about files being skipped.
    files = sorted(GOLDEN_DIR.rglob("*.json"))
    assert files, "the golden dataset must not be empty"
    on_disk = {
        json.loads(path.read_text(encoding="utf-8"))["case_id"] for path in files
    }
    assert {case.case_id for case in load_cases(GOLDEN_DIR)} == on_disk
    malformed = tmp_path / "future-contribution.json"
    malformed.write_text(
        json.dumps(_case_payload(risk_class="dangerous")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="dangerous"):
        load_cases(tmp_path)


def test_readme_documents_exact_contribution_shape_and_owners() -> None:
    readme = (GOLDEN_DIR.parent / "README.md").read_text(encoding="utf-8")
    assert "expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state" in readme
    assert "Stories 2.9, 3.10–3.12, and 4.5–4.6" in readme
    assert "Story 2.5 contributes scheduling_inspect" in readme
    assert "Story 2.7 contributes exactly four scheduling_compute cases" in readme
    assert "secrets" in readme.lower() and "PII" in readme


def test_grounding_cases_have_literal_result_ids_nonempty_refs_and_oracles() -> None:
    cases = [case for case in load_cases(GOLDEN_DIR) if case.capability == "scheduling_compute"]
    assert len(cases) == 4
    assert {case.expected_grounding_outcome for case in cases} == {
        "supported", "version_mismatch", "missing_evidence", "argument_mismatch"
    }
    assert all(case.expected_evidence_refs for case in cases)
    for case in cases:
        final = case.scripted_turns[-1].response_data
        claim = next(segment for segment in final["segments"] if segment["kind"] == "claim")
        assert len(claim["result_id"]) == 64


def test_live_verdict_is_non_authoritative_by_data_shape() -> None:
    verdict = ToolRoutingEvaluator(run_source="live").evaluate(
        case_from_mapping(_case_payload()),
        _run_case(case_from_mapping(_case_payload())),
    )
    assert verdict.run_source == "live"
    assert verdict.authoritative is False


@pytest.mark.live
@pytest.mark.skipif(
    not _HAS_LIVE_AGENT,
    reason="AGENT_RUNTIME_API_KEY/model not set — live evaluation requires both",
)
def test_golden_cases_against_live_agent_are_non_authoritative() -> None:
    from settings import default_settings

    runtime = create_agent_runtime(settings=default_settings())
    for case in load_cases(GOLDEN_DIR):
        outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
        verdict = ToolRoutingEvaluator(run_source="live").evaluate(case, outcome)
        assert verdict.authoritative is False


def _declared_bindings() -> dict[str, str]:
    return {
        "evaluator": "tool routing evaluator v1",
        "model": "case-driven FunctionModel double",
        "prompt": "versioned golden-case prompts",
        "tool": "shiftmind_demonstration from the Story 2.1 runtime",
        "policy": "AD-5 risk tags; deterministic results authoritative",
        "application": "ShiftMind evaluation harness Story 2.2",
        "solver": "not applicable — no solver run",
    }


def test_eval_dataset_binding_is_independent_from_scenario(tmp_path) -> None:
    dataset = tmp_path / "case.json"
    dataset.write_text(json.dumps(_case_payload()), encoding="utf-8")
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "root.py").write_text(
        'revision: str = "root0001"\ndown_revision = None\n', encoding="utf-8"
    )

    bindings = resolve_bindings(
        _declared_bindings(),
        dataset_files=[dataset],
        fixtures=[],
        migrations_dir=versions,
        code_binding={"git_commit": "unit-test", "working_tree_dirty": False},
    )

    assert bindings["dataset"]["case_count"] == 1
    assert bindings["dataset"]["risk_class_distribution"] == {"inspect": 1}
    assert bindings["dataset"]["files"]["case.json"]["sha256"]
    assert bindings["scenario"].startswith("not applicable")
    assert bindings["dataset"] != bindings["scenario"]


def _dataset_binding(dataset: Path, tmp_path: Path) -> dict:
    versions = tmp_path / "versions"
    if not versions.exists():
        versions.mkdir()
        (versions / "root.py").write_text(
            'revision: str = "root0001"\ndown_revision = None\n', encoding="utf-8"
        )
    return resolve_bindings(
        _declared_bindings(),
        dataset_files=[dataset],
        fixtures=[],
        migrations_dir=versions,
        code_binding={"git_commit": "unit-test", "working_tree_dirty": False},
    )["dataset"]


def test_dataset_digest_is_independent_of_line_endings(tmp_path) -> None:
    """`core.autocrlf` must not be able to move a dataset binding.

    The working tree holds CRLF on Windows while the committed blob holds LF,
    so a raw-byte digest would change on checkout with no content change —
    pinning the platform instead of the dataset.
    """
    body = json.dumps(_case_payload(), indent=2)
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    assert lf.read_bytes() != crlf.read_bytes()

    lf_digest = _dataset_binding(lf, tmp_path)["files"]["lf.json"]["sha256"]
    crlf_digest = _dataset_binding(crlf, tmp_path)["files"]["crlf.json"]["sha256"]

    assert lf_digest == crlf_digest


def test_incomplete_report_binding_raises_and_writes_no_file(tmp_path) -> None:
    output = tmp_path / "must-not-exist.json"
    case = case_from_mapping(_case_payload())
    evaluation = CaseEvaluation(
        case=case,
        verdict=ToolRoutingEvaluator().evaluate(case, _run_case(case)),
    )

    with pytest.raises(ValueError, match="solver"):
        write_evaluation_report(
            output,
            evaluations=[evaluation],
            declared_bindings={
                key: value
                for key, value in _declared_bindings().items()
                if key != "solver"
            },
            dataset_files=[],
        )

    assert not output.exists()


def test_complete_report_is_accepted_by_repo_wide_evidence_audit(
    tmp_path, monkeypatch
) -> None:
    dataset = tmp_path / "case.json"
    dataset.write_text(json.dumps(_case_payload()), encoding="utf-8")
    case = case_from_mapping(_case_payload())
    evaluation = CaseEvaluation(
        case=case,
        verdict=ToolRoutingEvaluator().evaluate(case, _run_case(case)),
    )
    output = tmp_path / "evaluation-report.json"
    repo_root = Path(__file__).resolve().parents[2]
    code_commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "backend/agent/runtime.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    monkeypatch.setattr(
        "scripts.evidence_binding.resolve_code_binding",
        lambda repo_root, allow_dirty=False: (
            {"git_commit": code_commit, "working_tree_dirty": False},
            False,
        ),
    )
    report = write_evaluation_report(
        output,
        evaluations=[evaluation],
        declared_bindings=_declared_bindings(),
        dataset_files=[dataset],
        repo_root=repo_root,
    )

    assert output.exists()
    assert report["release_gate_eligible"] is False
    assert "50-case" in report["purpose"]
    assert audit_evidence_file(output, repo_root=repo_root) == ()


def test_report_generator_routes_every_golden_case_to_a_registered_tool(tmp_path) -> None:
    """AC4's "the Story 2.2 harness runs the conformance and regression suites"
    covers the report generator too, not pytest alone. It had no test caller,
    which is exactly why a case routing to a tool that did not exist on its
    agent stayed green.
    """
    report = generate_demonstration_report(tmp_path / "report.json", allow_dirty=True)

    metrics = report["metrics"]
    assert metrics["authoritative_case_count"] == len(load_cases(GOLDEN_DIR))
    # Every case must actually route to a registered tool. Before this generator
    # composed per-case grants, the scheduling cases addressed a tool that did
    # not exist on their agent and nothing went red.
    assert metrics["failed"] == 0, report["results"]
    assert metrics["tool_routing_percentage"] == 100.0
    # NFR27: the tool binding names the capabilities that were actually granted,
    # derived from their manifests rather than a hardcoded string.
    tool_binding = report["version_bindings"]["tool"]
    for module in installed_modules():
        assert module.manifest.capability_name in tool_binding


def test_report_generator_refuses_a_case_naming_an_uninstalled_capability() -> None:
    """A case whose capability matches no module used to register zero tools and
    still count as a result."""
    orphan = replace(case_from_mapping(_case_payload()), capability="not_installed")

    with pytest.raises(ValueError, match="no supplied module provides"):
        _runtime_for_case(orphan, installed_modules())
