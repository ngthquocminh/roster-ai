"""NFR27-bound evaluation report generation."""
from __future__ import annotations

import json
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from uuid import UUID

from pydantic_ai import models

# Evaluation infrastructure is deterministic by default. Live diagnostics and
# the marked live test opt in with a narrow scoped override around provider use.
models.ALLOW_MODEL_REQUESTS = False

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.installed import installed_modules
from application.capabilities.module import CapabilityModuleV1
from application.contracts.agent_runtime import AgentBudgetV1, AgentRunOutcomeV1, AgentTurnRequestV1
from application.contracts.grounding import GroundedAnswerV1
from evals.fixture_projection import FIXTURE_IDENTITY, FixtureProjectionReader

# Golden cases tag themselves with an evaluation `capability` label, which is not
# always the registered tool name. Declared once, here, rather than branched on
# at each construction site.
EVAL_TAG_TO_CAPABILITY = {"demonstration": "shiftmind_demonstration"}
from evals.cases import GoldenCase
from evals.cases import load_cases
from evals.doubles import build_model_double
from evals.evaluators import (
    EvalVerdict,
    GroundingEvaluator,
    PolicyOutcomeEvaluator,
    ToolRoutingEvaluator,
)
from application.use_cases.execute_turn import resolve_draft_citation
from evals.grounding import ground_case_outcome
from application.use_cases.execute_turn import failed_outcome_for_exception, outcome_visible_text
from scripts.evidence_binding import REPO_ROOT, resolve_bindings


@dataclass(frozen=True)
class CaseEvaluation:
    case: GoldenCase
    verdict: EvalVerdict
    outcome: AgentRunOutcomeV1


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
    golden_dir: Path | None = None,
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Run a committed golden subset deterministically and persist evidence.

    The default remains the complete corpus. Historical evidence artifacts can
    pass their original subset explicitly, so regenerating one cannot silently
    widen its dataset binding as the corpus grows.
    """
    selected_golden_dir = (
        Path(golden_dir)
        if golden_dir is not None
        else repo_root / "backend" / "evals" / "golden"
    )
    cases = load_cases(selected_golden_dir)
    evaluations: list[CaseEvaluation] = []
    # The installed set itself, never a second hand-maintained list: a module
    # installed but missing here would silently drop out of the NFR27 binding.
    # This is only the SEARCH POOL `_runtime_for_case` matches each case's
    # capability tag against -- not what a case's runtime actually grants (see
    # `exercised_modules` below, which the "tool" binding is scoped to).
    installed = installed_modules()
    # Scoped to what each case's runtime was actually constructed with, never
    # the full installed set -- otherwise regenerating a `golden_dir` subset
    # would falsely claim every installed module was exercised, contradicting
    # this function's own "cannot silently widen its dataset binding" promise.
    exercised_modules: dict[str, CapabilityModuleV1] = {}
    for case in cases:
        results: list[object] = []
        runtime = _runtime_for_case(case, installed, results)
        outcome = _run_runtime_case(runtime, case)
        verdict, outcome = _evaluate_case(
            case, runtime, outcome, results, run_source="double"
        )
        evaluations.append(CaseEvaluation(case=case, verdict=verdict, outcome=outcome))
        for module in getattr(runtime, "_granted", ()):
            exercised_modules[module.manifest.capability_name] = module
    return write_evaluation_report(
        output_path,
        evaluations=evaluations,
        declared_bindings={
            **DEMONSTRATION_BINDINGS,
            "tool": ", ".join(
                f"{module.manifest.capability_name}@{module.manifest.capability_version}"
                for module in sorted(
                    exercised_modules.values(), key=lambda m: m.manifest.capability_name
                )
            ),
        },
        dataset_files=sorted(selected_golden_dir.rglob("*.json")),
        repo_root=repo_root,
        # Only ever True from a test writing to a temporary path: committed
        # evidence still requires a clean tree.
        allow_dirty=allow_dirty,
    )


def generate_live_diagnostics(
    output_path: Path,
    *,
    model: object,
    cases: Sequence[GoldenCase],
    model_name: str = "configured-live-model",
) -> None:
    """Append and flush a non-authoritative verdict immediately per live case."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        with models.override_allow_model_requests(True):
            for case in cases:
                if not case.live_eligible:
                    continue
                results: list[object] = []
                try:
                    runtime = _runtime_for_case(case, installed_modules(), results, model=model)
                    outcome = _run_runtime_case(runtime, case)
                    verdict, _outcome = _evaluate_case(
                        case, runtime, outcome, results, run_source="live"
                    )
                    record = {
                        "case_id": case.case_id,
                        "case_version": case.case_version,
                        "model": model_name,
                        "passed": verdict.passed,
                        "reason": verdict.reason,
                        "run_source": verdict.run_source,
                        "tool_calls": [
                            {
                                "name": part.tool_name,
                                "arguments": json.loads(part.tool_args_json or "null"),
                            }
                            for message in outcome.turn.messages
                            if message.role == "assistant"
                            for part in message.parts
                            if part.kind == "tool_call"
                        ],
                        "tool_results": [
                            {"name": result.tool_name, "content": result.content}
                            for result in outcome.tool_results
                        ],
                    }
                except Exception as exc:  # diagnostic evidence must survive a bad case
                    record = {
                        "case_id": case.case_id,
                        "case_version": case.case_version,
                        "model": model_name,
                        "passed": False,
                        "reason": f"diagnostic exception: {type(exc).__name__}: {str(exc)[:200]}",
                        "run_source": "live",
                        "tool_calls": [],
                        "tool_results": [],
                    }
                try:
                    stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")
                except Exception as exc:  # one record must never abort diagnostics for later cases
                    fallback = {
                        "case_id": case.case_id,
                        "case_version": case.case_version,
                        "model": model_name,
                        "passed": False,
                        "reason": (
                            f"diagnostic record could not be serialized: "
                            f"{type(exc).__name__}: {str(exc)[:200]}"
                        ),
                        "run_source": "live",
                        "tool_calls": [],
                        "tool_results": [],
                    }
                    stream.write(json.dumps(fallback, sort_keys=True) + "\n")
                stream.flush()


def _evaluate_case(
    case: GoldenCase,
    runtime: PydanticAIAgentRuntime,
    outcome: AgentRunOutcomeV1,
    results: list[object],
    *,
    run_source: str,
) -> tuple[EvalVerdict, AgentRunOutcomeV1]:
    """Score one case's outcome, routing + grounding + policy, for any run source.

    Extracted from `generate_demonstration_report`'s loop so a live run scores a
    case by the exact same rule an authoritative double run does -- only
    `run_source` (and therefore `EvalVerdict.authoritative`) differs. Returns the
    resolved outcome alongside the verdict because a draft case's citation
    binding mutates it before grounding can see the real text.
    """
    routing = ToolRoutingEvaluator(run_source=run_source).evaluate(case, outcome)
    # A draft case cites a trusted result rather than authoring one, so the
    # dataset has to drive the same citation binding the request path uses.
    # Without this the case would assert an empty visible text and prove
    # nothing about DraftProposalV1 or outcome_visible_text's draft branch.
    if outcome.draft is not None:
        outcome = resolve_draft_citation(
            outcome,
            {
                value.result_id: value
                for value in results
                if isinstance(getattr(value, "result_id", None), str)
            },
        )
    if case.expected_grounding_outcome:
        outcome = ground_case_outcome(
            case, outcome, runtime._deps, tuple(results), run_source=run_source
        )
        grounding = GroundingEvaluator(run_source=run_source).evaluate(case, outcome)
        verdict = EvalVerdict(
            passed=routing.passed and grounding.passed,
            reason=f"routing: {routing.reason}; grounding: {grounding.reason}",
            run_source=run_source,
        )
    else:
        verdict = routing
    policy = PolicyOutcomeEvaluator(runtime=runtime, run_source=run_source).evaluate(
        case, outcome
    )
    verdict = EvalVerdict(
        passed=verdict.passed and policy.passed,
        reason=f"{verdict.reason}; policy: {policy.reason}",
        run_source=run_source,
    )
    return verdict, outcome


def _report_deps(sink: list | None = None) -> AgentDepsV1:
    """Trusted deps for a deterministic, offline report run.

    The projection carries REAL rows (`evals/fixture_projection.py`) so a
    grounded case exercises the actual calculator; `sink` captures each raw
    capability result on the same trusted path the request route uses.
    """
    identity = FIXTURE_IDENTITY
    return AgentDepsV1(
        actor_id=UUID(int=2), site_id=identity,
        membership_id=UUID(int=3), request_id=UUID(int=4),
        agent_run_id=UUID(int=5), conversation_id=UUID(int=6),
        scenario_id=identity, scenario_version_id=identity,
        policy_version="one-user-mvp-v1",
        clock=lambda: datetime.now(timezone.utc),
        projection_reader=FixtureProjectionReader(),
        connection=object(), remaining_budget=AgentBudgetV1(),
        tool_result_sink=(sink.append if sink is not None else None),
    )


def runtime_for_modules(
    case: GoldenCase,
    modules: tuple[CapabilityModuleV1, ...],
    sink: list | None = None,
    *,
    model: object | None = None,
) -> PydanticAIAgentRuntime:
    """Build a runtime granting EXACTLY `modules` -- no tag filtering.

    Kept separate from `_runtime_for_case` so a caller composing its own granted
    set (a removed-world proof, for instance) gets that set rendered verbatim
    rather than re-filtered behind its back.

    `model` defaults to the case's deterministic double; passing one (a real
    provider model) is how a live run reuses this same capability/deps/
    answer_type wiring instead of duplicating it.
    """
    return PydanticAIAgentRuntime(
        model=model if model is not None else build_model_double(case),
        capabilities=modules, deps=_report_deps(sink),
        answer_type=GroundedAnswerV1 if _needs_named_output_tools(case) else None,
    )


def _needs_named_output_tools(case: GoldenCase) -> bool:
    """Whether this case's agent must register the named `ToolOutput` variants.

    Passing `answer_type=None` gives the runtime `[str, DeferredToolRequests]`
    and therefore NO named output tools at all, so a case scripting one gets an
    `UnexpectedModelBehavior` and a failed run rather than a readable verdict.

    The last clause is what made the `draft` output tool reachable. Deriving the
    need from `expected_outcome` alone covered `clarify` and `refuse` but never
    `allow`, and a draft case is an ALLOW case that still selects a named output
    tool -- so `DraftProposalV1`, `DRAFT_OUTPUT_TOOL` and execute_turn's citation
    binding could not be exercised by any golden case that existed. Derived from
    the script rather than re-declared, so a fifth variant needs no edit here.
    """
    if case.expected_grounding_outcome:
        return True
    if case.expected_outcome in {"clarify", "refuse"}:
        return True
    return any(turn.response_data is not None for turn in case.scripted_turns)


def _runtime_for_case(
    case: GoldenCase,
    modules: tuple[CapabilityModuleV1, ...],
    sink: list | None = None,
    *,
    model: object | None = None,
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
    return runtime_for_modules(case, selected, sink, model=model)


def _run_runtime_case(
    runtime: PydanticAIAgentRuntime, case: GoldenCase
) -> AgentRunOutcomeV1:
    try:
        return runtime.run_turn(AgentTurnRequestV1(prompt=case.prompt))
    except Exception as exc:  # the production route has the same finalization rule
        return failed_outcome_for_exception(exc)


def build_evaluation_report(
    evaluations: Sequence[CaseEvaluation], *, bindings: Mapping[str, object]
) -> dict[str, object]:
    authoritative = tuple(item for item in evaluations if item.verdict.authoritative)
    judged = tuple((item, *_visible_judgement(item)) for item in authoritative)
    passed = sum(passed for _item, passed, _reason in judged)
    protected = tuple(
        item
        for item in authoritative
        if item.case.risk_class in ("consequential", "prohibited")
    )
    protected_passed = sum(
        passed
        for item, passed, _reason in judged
        if item.case.risk_class in ("consequential", "prohibited")
    )

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
                "passed": item.verdict.passed and visible_passed,
                "reason": f"{item.verdict.reason}; visible: {visible_reason}",
                "run_source": item.verdict.run_source,
                "authoritative": item.verdict.authoritative,
            }
            for item in evaluations
            for visible_passed, visible_reason in [_visible_judgement(item)]
        ],
        "version_bindings": dict(bindings),
    }


def _visible_judgement(item: CaseEvaluation) -> tuple[bool, str]:
    actual_text = outcome_visible_text(item.outcome)
    state_matches = item.outcome.status == item.case.expected_visible_state
    text_matches = actual_text == item.case.expected_visible_text
    return (
        item.verdict.passed and state_matches and text_matches,
        (
            f"state expected {item.case.expected_visible_state}, actual {item.outcome.status}; "
            f"text expected {item.case.expected_visible_text!r}, actual {actual_text!r}"
        ),
    )


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
    "generate_live_diagnostics",
    "write_evaluation_report",
]
