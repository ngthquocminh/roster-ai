"""Deterministic evaluation harness tests.

The default suite is intentionally unmarked and model requests are disabled at
module scope. Story 2.2 grows this file task by task; every assertion at the
runtime seam is on ShiftMind-owned outcomes.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic_ai import models

from agent.runtime import PydanticAIAgentRuntime, create_agent_runtime
from application.contracts.agent_runtime import AgentRunOutcomeV1, AgentTurnRequestV1
from evals.cases import (
    ExpectedToolCall,
    GoldenCase,
    case_from_mapping,
    load_case,
    load_cases,
)
from evals.doubles import build_model_double
from evals.evaluators import Evaluator, ToolRoutingEvaluator
from evals.report import CaseEvaluation, write_evaluation_report
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
    runtime = PydanticAIAgentRuntime(model=build_model_double(case))

    outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))

    assert isinstance(outcome, AgentRunOutcomeV1)
    assert outcome.status == "completed"
    assert outcome.output_text == "tool said alpha"
    assert outcome.tool_results[0].tool_name == "shiftmind_demonstration"


def _run_case(case: GoldenCase) -> AgentRunOutcomeV1:
    runtime = PydanticAIAgentRuntime(model=build_model_double(case))
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
    assert len(cases) == 2, "Story 2.2 seeds only the two schema-proof cases"
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
    assert {case.capability for case in cases} == {"demonstration"}


def test_every_golden_file_validates_and_malformed_contribution_fails(tmp_path) -> None:
    assert len(load_cases(GOLDEN_DIR)) == len(tuple(GOLDEN_DIR.rglob("*.json")))
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
    assert "secrets" in readme.lower() and "PII" in readme


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
