"""NFR27-bound evaluation report generation."""
from __future__ import annotations

import json
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from uuid import UUID

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.installed import installed_modules
from application.capabilities.module import CapabilityModuleV1
from application.contracts.agent_runtime import AgentBudgetV1, AgentTurnRequestV1
from application.contracts.grounding import GroundedAnswerV1
from application.contracts.evidence_ref import DemandIntervalResolutionV1
from application.contracts.scenario_projection import DemandIntervalV1
from application.ports.scenario_projection import GroupQueryKeysV1

# Golden cases tag themselves with an evaluation `capability` label, which is not
# always the registered tool name. Declared once, here, rather than branched on
# at each construction site.
EVAL_TAG_TO_CAPABILITY = {"demonstration": "shiftmind_demonstration"}
from evals.cases import GoldenCase
from evals.cases import load_cases
from evals.doubles import build_model_double
from evals.evaluators import EvalVerdict, GroundingEvaluator, ToolRoutingEvaluator
from evals.grounding import ground_case_outcome
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
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Run the committed golden cases deterministically and persist evidence."""
    golden_dir = repo_root / "backend" / "evals" / "golden"
    cases = load_cases(golden_dir)
    evaluations: list[CaseEvaluation] = []
    # The installed set itself, never a second hand-maintained list: a module
    # installed but missing here would silently drop out of the NFR27 binding.
    granted_modules = installed_modules()
    for case in cases:
        runtime = _runtime_for_case(case, granted_modules)
        outcome = runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
        routing = ToolRoutingEvaluator(run_source="double").evaluate(case, outcome)
        if case.expected_grounding_outcome:
            outcome = ground_case_outcome(case, outcome, runtime._deps)
            grounding = GroundingEvaluator(run_source="double").evaluate(case, outcome)
            verdict = EvalVerdict(
                passed=routing.passed and grounding.passed,
                reason=f"routing: {routing.reason}; grounding: {grounding.reason}",
                run_source="double",
            )
        else:
            verdict = routing
        evaluations.append(CaseEvaluation(case=case, verdict=verdict))
    return write_evaluation_report(
        output_path,
        evaluations=evaluations,
        declared_bindings={
            **DEMONSTRATION_BINDINGS,
            "tool": ", ".join(
                f"{module.manifest.capability_name}@{module.manifest.capability_version}"
                for module in granted_modules
            ),
        },
        dataset_files=sorted(golden_dir.rglob("*.json")),
        repo_root=repo_root,
        # Only ever True from a test writing to a temporary path: committed
        # evidence still requires a clean tree.
        allow_dirty=allow_dirty,
    )


def _report_deps() -> AgentDepsV1:
    """Trusted deps for a deterministic, offline report run."""
    identity = UUID(int=1)

    class ProjectionReader:
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
            from types import SimpleNamespace
            return SimpleNamespace(
                scenario_id=identity, scenario_version_id=identity, site_id=identity,
                items=(), next_cursor=None, total_count=0, matching_count=0,
            )

        get_demand = lambda self, *_args: self._page()
        get_baseline_assignments = lambda self, *_args: self._page()
        get_workers = lambda self, *_args: self._page()
        get_locks = lambda self, *_args: self._page()
        get_constraints = lambda self, *_args: self._page()
        get_overview = lambda self, *_args: self._page()

        def resolve_demand_interval(
            self, _connection, scenario_id, scenario_version_id, record_id
        ):
            return DemandIntervalResolutionV1(
                outcome="resolved",
                scenario_id=scenario_id,
                current_scenario_version_id=scenario_version_id,
                item=DemandIntervalV1(
                    record_id, "outbound", "pick", None, 2880, 4320, 1, "headcount"
                ),
            )

    return AgentDepsV1(
        actor_id=UUID(int=2), site_id=identity,
        membership_id=UUID(int=3), request_id=UUID(int=4),
        agent_run_id=UUID(int=5), conversation_id=UUID(int=6),
        scenario_id=identity, scenario_version_id=identity, policy_version="one-user-mvp-v1",
        clock=lambda: datetime.now(timezone.utc), projection_reader=ProjectionReader(),
        connection=object(), remaining_budget=AgentBudgetV1(),
    )


def runtime_for_modules(
    case: GoldenCase, modules: tuple[CapabilityModuleV1, ...]
) -> PydanticAIAgentRuntime:
    """Build a runtime granting EXACTLY `modules` -- no tag filtering.

    Kept separate from `_runtime_for_case` so a caller composing its own granted
    set (a removed-world proof, for instance) gets that set rendered verbatim
    rather than re-filtered behind its back.
    """
    return PydanticAIAgentRuntime(
        model=build_model_double(case), capabilities=modules, deps=_report_deps(),
        answer_type=(GroundedAnswerV1 if case.expected_grounding_outcome else None),
    )


def _runtime_for_case(
    case: GoldenCase, modules: tuple[CapabilityModuleV1, ...]
) -> PydanticAIAgentRuntime:
    """Grant a case exactly the module its `capability` tag names."""
    wanted = EVAL_TAG_TO_CAPABILITY.get(case.capability, case.capability)
    selected = tuple(
        module for module in modules if module.manifest.capability_name == wanted
    )
    if not selected:
        # Silently registering no tool would let the case "pass" without ever
        # routing anything, which is the hole this generator was fixed for.
        raise ValueError(
            f"case {case.case_id!r} names capability {case.capability!r}, "
            f"which no supplied module provides"
        )
    return runtime_for_modules(case, selected)


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
        # This report type proves the harness machinery only. Gate B evaluates
        # the later stories' aggregate dataset; two passing seed cases must not
        # be promoted into a release claim.
        "release_gate_eligible": False,
        "release_gate_status": (
            "demonstration only — NFR28 aggregate thresholds are not evaluated"
        ),
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


def _percentage(numerator: int, denominator: int) -> float | None:
    """``None`` for an empty denominator — "not measured", never "0% routed".

    NFR28 reads the protected-class percentage against a 100% threshold, so a
    report with no consequential/prohibited cases must not encode that absence
    as a total routing failure.
    """
    return round((numerator / denominator) * 100, 2) if denominator else None


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
