"""NFR27-bound evaluation report generation."""
from __future__ import annotations

import json
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from agent.runtime import PydanticAIAgentRuntime
from application.contracts.agent_runtime import AgentTurnRequestV1
from evals.cases import GoldenCase
from evals.cases import load_cases
from evals.doubles import build_model_double
from evals.evaluators import EvalVerdict, ToolRoutingEvaluator
from scripts.evidence_binding import REPO_ROOT, resolve_bindings


@dataclass(frozen=True)
class CaseEvaluation:
    case: GoldenCase
    verdict: EvalVerdict


@dataclass(frozen=True)
class _ScenarioSpec:
    fixture_id: str
    version: str


DEMONSTRATION_BINDINGS: dict[str, str] = {
    "evaluator": "ToolRoutingEvaluator v1 (exact tool name and JSON arguments)",
    "model": "case-driven PydanticAI FunctionModel deterministic double",
    "prompt": "versioned prompts in backend/evals/golden/**/*.json",
    "tool": "shiftmind_demonstration from the Story 2.1 AgentRuntime adapter",
    "policy": "AD-5 risk tags; only double-sourced verdicts are authoritative",
    "application": "ShiftMind Story 2.2 deterministic evaluation harness",
    "solver": "not applicable — demonstration tool invokes no solver",
}


def write_evaluation_report(
    output_path: Path,
    *,
    evaluations: Sequence[CaseEvaluation],
    declared_bindings: Mapping[str, object],
    dataset_files: Iterable[Path],
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Resolve every binding first, then atomically create the report path.

    A missing binding or dirty tree raises before the output directory or file
    is created, so an incomplete report can never be mistaken for evidence.
    """
    dataset_paths = tuple(Path(path) for path in dataset_files)
    bindings = resolve_bindings(
        declared_bindings,
        repo_root=repo_root,
        fixtures=_scenario_specs(evaluations),
        dataset_files=dataset_paths,
        allow_dirty=allow_dirty,
    )
    report = build_evaluation_report(evaluations, bindings=bindings)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def generate_demonstration_report(
    output_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, object]:
    """Run the committed golden cases deterministically and persist evidence."""
    golden_dir = repo_root / "backend" / "evals" / "golden"
    cases = load_cases(golden_dir)
    evaluations: list[CaseEvaluation] = []
    for case in cases:
        runtime = PydanticAIAgentRuntime(model=build_model_double(case))
        outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
        verdict = ToolRoutingEvaluator(run_source="double").evaluate(case, outcome)
        evaluations.append(CaseEvaluation(case=case, verdict=verdict))
    return write_evaluation_report(
        output_path,
        evaluations=evaluations,
        declared_bindings=DEMONSTRATION_BINDINGS,
        dataset_files=sorted(golden_dir.rglob("*.json")),
        repo_root=repo_root,
    )


def build_evaluation_report(
    evaluations: Sequence[CaseEvaluation], *, bindings: Mapping[str, object]
) -> dict[str, object]:
    authoritative = tuple(item for item in evaluations if item.verdict.authoritative)
    passed = sum(item.verdict.passed for item in authoritative)
    protected = tuple(
        item
        for item in authoritative
        if item.case.risk_class in ("consequential", "prohibited")
    )
    protected_passed = sum(item.verdict.passed for item in protected)

    return {
        "report_type": "evaluation-harness-demonstration",
        "report_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Demonstrates the Story 2.2 evaluation machinery; it does not claim "
            "or pad toward NFR28's 50-case Gate B aggregate floor."
        ),
        "release_gate_eligible": bool(authoritative) and passed == len(authoritative),
        "metrics": {
            "authoritative_case_count": len(authoritative),
            "passed": passed,
            "failed": len(authoritative) - passed,
            "live_results_excluded": len(evaluations) - len(authoritative),
            "tool_routing_percentage": _percentage(passed, len(authoritative)),
            "consequential_prohibited_case_count": len(protected),
            "consequential_prohibited_passed": protected_passed,
            "consequential_prohibited_tool_routing_percentage": _percentage(
                protected_passed, len(protected)
            ),
        },
        "results": [
            {
                "case_id": item.case.case_id,
                "case_version": item.case.case_version,
                "capability": item.case.capability,
                "risk_class": item.case.risk_class,
                "passed": item.verdict.passed,
                "reason": item.verdict.reason,
                "run_source": item.verdict.run_source,
                "authoritative": item.verdict.authoritative,
            }
            for item in evaluations
        ],
        "version_bindings": dict(bindings),
    }


def _scenario_specs(evaluations: Sequence[CaseEvaluation]) -> tuple[_ScenarioSpec, ...]:
    identities = sorted(
        {
            identity
            for item in evaluations
            for identity in item.case.scenario_fixtures
        }
    )
    specs: list[_ScenarioSpec] = []
    for identity in identities:
        fixture_id, separator, version = identity.partition(":")
        if not separator or not fixture_id or not version:
            raise ValueError(
                f"scenario fixture {identity!r} must use fixture_id:version"
            )
        specs.append(_ScenarioSpec(fixture_id=fixture_id, version=version))
    return tuple(specs)


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate_demonstration_report(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CaseEvaluation",
    "DEMONSTRATION_BINDINGS",
    "build_evaluation_report",
    "generate_demonstration_report",
    "write_evaluation_report",
]
