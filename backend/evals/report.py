"""NFR27-bound evaluation report generation."""
from __future__ import annotations

import json
import argparse
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from pydantic_ai import models

# Evaluation infrastructure is deterministic by default. Live diagnostics and
# the marked live test opt in with a narrow scoped override around provider use.
models.ALLOW_MODEL_REQUESTS = False

from agent.runtime import PydanticAIAgentRuntime
from application.capabilities.deps import AgentDepsV1
from application.capabilities.installed import installed_modules
from application.capabilities.module import CapabilityModuleV1
from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    PlannerMessageActivityV1,
)
from application.contracts.agent_runtime import (
    AgentBudgetV1,
    AgentMessageV1,
    AgentPartV1,
    AgentRunOutcomeV1,
    AgentToolResultV1,
    AgentTurnRequestV1,
    AgentTurnV1,
    AgentUsageV1,
)
from application.contracts.grounding import GroundedAnswerV1, GroundedProseSegmentV1, GroundedResponseV1
from evals.fixture_projection import FIXTURE_IDENTITY, FixtureProjectionReader

# Golden cases tag themselves with an evaluation `capability` label, which is not
# always the registered tool name. Declared once, here, rather than branched on
# at each construction site.
EVAL_TAG_TO_CAPABILITY = {"demonstration": "shiftmind_demonstration"}
from evals.cases import GoldenCase, GoldenTurn, MultiTurnGoldenCase
from evals.cases import load_cases, load_multi_turn_cases
from evals.doubles import build_model_double, build_multi_turn_double, history_response_offset_for
from evals.evaluators import (
    EvalVerdict,
    GroundingEvaluator,
    PolicyOutcomeEvaluator,
    ToolRoutingEvaluator,
)
from application.use_cases import execute_turn as execute_turn_module
from application.use_cases.execute_turn import execute_turn, rehydrate_history, resolve_draft_citation
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


# Closed vocabulary a raw evaluator `reason` string collapses to before it may
# be persisted (Decision 6 / AC6). `ToolRoutingEvaluator`/`GroundingEvaluator`
# reasons legitimately embed literal expected/actual tool ARGUMENTS -- exactly
# the raw content AC6 forbids in a report -- so the free-text reason itself
# must never reach a diagnostics file. Matched by substring against the known,
# stable phrasings those evaluators emit; an unrecognized phrasing classifies
# as "other" rather than falling through unredacted.
#: Checked BEFORE `"matched"`. A multi-turn `_evaluate_turn` reason is a
#: COMPOUND string ("routing: matched ...; policy: matched ...; visible:
#: state expected completed, actual failed; ...") -- the word "matched" can
#: legitimately appear in an early, passing segment while a LATER segment is
#: the actual failure. Checking failure needles first, and "matched" only as
#: the final fallback, is what keeps a genuinely failed verdict from
#: classifying as "matched" merely because routing happened to succeed.
_REASON_CLASSIFICATIONS: tuple[tuple[str, str], ...] = (
    ("tool-call count differed", "tool_call_count_mismatch"),
    ("tool name differed", "tool_name_mismatch"),
    ("tool arguments differed", "tool_arguments_mismatch"),
    ("oracle differed", "grounding_oracle_mismatch"),
    ("evidence differed", "grounding_evidence_mismatch"),
    ("policy outcome differed", "policy_outcome_mismatch"),
    ("unregistered capability", "unauthorized_capability_result"),
    ("did not reach completed state", "policy_outcome_mismatch"),
    ("invoked consequential capability", "policy_outcome_mismatch"),
    ("tool results differed", "tool_result_mismatch"),
    ("visible differed", "visible_mismatch"),
    # Deliberately NOT a bare `"expected"` needle: `ToolRoutingEvaluator`'s own
    # PASSING reason ("matched N EXPECTED tool route(s)") contains that word
    # too, so a generic needle there misclassified every passing single-turn
    # case. These two phrases are unique to `ToolRoutingEvaluator`'s and
    # `PolicyOutcomeEvaluator`'s own FAILURE messages.
    ("but routed to", "unexpected_tool_call"),
    ("without reaching a policy decision", "policy_outcome_mismatch"),
    ("terminated as", "terminated_before_policy_decision"),
    ("matched", "matched"),
)


def _classify_reason(reason: str) -> str:
    lowered = reason.lower()
    for needle, label in _REASON_CLASSIFICATIONS:
        if needle in lowered:
            return label
    return "other"


def _safe_diagnostic_record(
    *,
    case_id: str,
    case_version: str,
    model_name: str,
    passed: bool,
    reason_classification: str,
    run_source: str,
    tool_call_names: Sequence[str] = (),
    tool_result_names: Sequence[str] = (),
) -> dict[str, object]:
    """The ONLY shape a diagnostics record may take.

    Story 5.6 Decision 6: the prior shape persisted raw tool arguments
    (`part.tool_args_json`) and raw `AgentToolResultV1.content` verbatim,
    violating AC6/AD-15. This carries only ordered NAMES and COUNTS -- never a
    value a prompt, a tool argument, or a tool result body could have produced
    -- plus a closed-vocabulary outcome classification instead of the raw
    evaluator reason string.
    """
    return {
        "case_id": case_id,
        "case_version": case_version,
        "model": model_name,
        "passed": passed,
        "reason_classification": reason_classification,
        "run_source": run_source,
        "tool_call_names": list(tool_call_names),
        "tool_call_count": len(tool_call_names),
        "tool_result_names": list(tool_result_names),
        "tool_result_count": len(tool_result_names),
    }


def generate_live_diagnostics(
    output_path: Path,
    *,
    model: object,
    cases: Sequence[GoldenCase],
    model_name: str = "configured-live-model",
) -> None:
    """Append and flush a non-authoritative, REDACTED verdict per live case.

    A write/serialization failure for one case's record must never erase the
    diagnostics already flushed for earlier cases -- each record is written
    and flushed independently, and the fallback branch below is exercised by
    Task 4's mutation table.
    """
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
                    record = _safe_diagnostic_record(
                        case_id=case.case_id,
                        case_version=case.case_version,
                        model_name=model_name,
                        passed=verdict.passed,
                        reason_classification=_classify_reason(verdict.reason),
                        run_source=verdict.run_source,
                        tool_call_names=[
                            part.tool_name
                            for message in outcome.turn.messages
                            if message.role == "assistant"
                            for part in message.parts
                            if part.kind == "tool_call"
                        ],
                        tool_result_names=[
                            result.tool_name for result in outcome.tool_results
                        ],
                    )
                except Exception as exc:  # diagnostic evidence must survive a bad case
                    record = _safe_diagnostic_record(
                        case_id=case.case_id,
                        case_version=case.case_version,
                        model_name=model_name,
                        passed=False,
                        reason_classification="diagnostic_exception",
                        run_source="live",
                    )
                try:
                    stream.write(json.dumps(record, sort_keys=True, default=str) + "\n")
                except Exception:  # one record must never abort diagnostics for later cases
                    fallback = _safe_diagnostic_record(
                        case_id=case.case_id,
                        case_version=case.case_version,
                        model_name=model_name,
                        passed=False,
                        reason_classification="diagnostic_record_unserializable",
                        run_source="live",
                    )
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


# ---------------------------------------------------------------------------
# Story 5.6: versioned multi-turn history and tool-continuity evaluation.
#
# Deliberately a SECOND, parallel set of functions rather than a branch inside
# the Story 2.2 single-turn ones above: `GoldenTurn`/`MultiTurnGoldenCase`
# duck-type onto `ToolRoutingEvaluator`/`PolicyOutcomeEvaluator` (Decision 1),
# but the RUNNER differs in a way the single-turn one cannot absorb by
# branching -- it drives `execute_turn` across N turns, carrying each turn's
# outcome into the next one's history, which `_run_runtime_case` (a single
# `runtime.run_turn` call) has no notion of at all.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnEvaluation:
    turn_index: int
    turn: GoldenTurn
    verdict: EvalVerdict
    outcome: AgentRunOutcomeV1


@dataclass(frozen=True)
class MultiTurnCaseEvaluation:
    case: MultiTurnGoldenCase
    turn_evaluations: tuple[TurnEvaluation, ...]

    @property
    def passed(self) -> bool:
        return all(item.verdict.passed for item in self.turn_evaluations)

    @property
    def authoritative(self) -> bool:
        """Only meaningful in aggregate: ANY live turn makes the whole case
        non-authoritative, matching `EvalVerdict.authoritative`'s single-turn
        rule that a live result can never contribute release evidence.
        """
        return all(item.verdict.authoritative for item in self.turn_evaluations)


def _history_for_turn(
    turn: GoldenTurn,
    prior_turns: Sequence[GoldenTurn],
    prior_outcomes: Sequence[AgentRunOutcomeV1],
    deps: AgentDepsV1,
) -> tuple[ActivityItemV1, ...] | AgentTurnV1:
    """Build exactly the `history` shape `execute_turn` already accepts.

    Never a third mechanism: `"raw_turn"` is the identical owned-resume-
    transcript branch `api/routers/approvals.py` uses today (an already-owned
    `AgentTurnV1`), and `"rehydrated_activities"` feeds real
    `tuple[ActivityItemV1, ...]` through `execute_turn`'s own
    `rehydrate_history()` call -- the ordinary conversational path every other
    multi-turn production request takes.
    """
    if turn.history_mode == "independent":
        return ()
    if turn.history_mode == "raw_turn":
        if not prior_outcomes:
            raise ValueError("raw_turn history_mode requires a previous turn")
        previous = prior_outcomes[-1].turn
        # Synthetic filler pushes the real antecedent out of
        # `HISTORY_MESSAGE_BOUND` once `execute_turn` slices `[-100:]` -- the
        # truncated-antecedent fault case's only mechanism. It never bypasses
        # the bound; it proves the bound is actually enforced on this branch.
        padding = tuple(
            AgentMessageV1(
                role="user" if index % 2 == 0 else "assistant",
                parts=(AgentPartV1(kind="text", text=f"filler message {index}"),),
            )
            for index in range(turn.raw_turn_padding)
        )
        return AgentTurnV1(messages=previous.messages + padding)
    # "rehydrated_activities"
    now = deps.clock()
    activities: list[ActivityItemV1] = [
        PlannerMessageActivityV1(
            activity_id=uuid4(), activity_type="planner_message",
            conversation_id=deps.conversation_id, conversation_resource_version=index + 1,
            scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
            occurred_at=now, message_id=uuid4(), text=f"filler activity {index}",
        )
        for index in range(turn.filler_activity_count)
    ]
    for prior_turn, prior_outcome in zip(prior_turns, prior_outcomes):
        activities.append(
            PlannerMessageActivityV1(
                activity_id=uuid4(), activity_type="planner_message",
                conversation_id=deps.conversation_id, conversation_resource_version=len(activities) + 1,
                scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
                occurred_at=now, message_id=uuid4(), text=prior_turn.prompt,
            )
        )
        activities.append(
            AgentResponseActivityV1(
                activity_id=uuid4(), activity_type="agent_response",
                conversation_id=deps.conversation_id, conversation_resource_version=len(activities) + 1,
                scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
                occurred_at=now,
                response=GroundedResponseV1(
                    scenario_version_id=deps.scenario_version_id,
                    segments=(
                        GroundedProseSegmentV1(text=outcome_visible_text(prior_outcome)),
                    ),
                ),
            )
        )
    return tuple(activities)


def _trim_outcome_to_current_turn(
    outcome: AgentRunOutcomeV1, injected_message_count: int
) -> AgentRunOutcomeV1:
    """Scope one `execute_turn` outcome to only the messages THIS turn added.

    `PydanticAIAgentRuntime.run_turn` builds `turn`/`tool_results` from
    `result.all_messages()`, which -- by design, per `AgentTurnV1`'s own
    docstring -- includes whatever was passed in as `message_history` too.
    For a `raw_turn`-continued case that is every earlier turn's messages,
    unmodified. Slicing the injected prefix off before evaluation keeps
    `ToolRoutingEvaluator`/`PolicyOutcomeEvaluator` judging what THIS turn
    did, not the whole accumulated conversation.
    """
    if injected_message_count <= 0:
        return outcome
    trimmed_messages = outcome.turn.messages[injected_message_count:]
    trimmed_turn = replace(outcome.turn, messages=trimmed_messages)
    trimmed_tool_results = tuple(
        AgentToolResultV1(
            tool_call_id=part.tool_call_id or "",
            tool_name=part.tool_name or "",
            content=part.text or "",
        )
        for message in trimmed_messages
        if message.role == "tool_result"
        for part in message.parts
    )
    return replace(outcome, turn=trimmed_turn, tool_results=trimmed_tool_results)


def _evaluate_turn(
    turn: GoldenTurn, runtime: PydanticAIAgentRuntime, outcome: AgentRunOutcomeV1, *, run_source: str
) -> EvalVerdict:
    """Judge one turn with the UNCHANGED Story 2.2/2.9 evaluators (Decision 1).

    `ToolRoutingEvaluator`/`PolicyOutcomeEvaluator` are typed for `GoldenCase`
    but read only `expected_tool_calls`, `expected_outcome`, and their
    `live_expected_*` counterparts -- fields `GoldenTurn` declares under the
    identical names on purpose, so this is duck typing by design, not a type
    violation silently tolerated.
    """
    routing = ToolRoutingEvaluator(run_source=run_source).evaluate(turn, outcome)  # type: ignore[arg-type]
    policy = PolicyOutcomeEvaluator(runtime=runtime, run_source=run_source).evaluate(turn, outcome)  # type: ignore[arg-type]
    actual_text = outcome_visible_text(outcome)
    state_matches = outcome.status == turn.expected_visible_state
    text_matches = actual_text == turn.expected_visible_text
    # "differed"/"matched" phrasing mirrors the existing single-turn
    # evaluators' own style (`evals/evaluators.py`) deliberately: `_classify_reason`
    # substring-matches this compound string, and consistent phrasing is what
    # keeps that classification from mistaking a PASSING segment's wording for
    # a failing one (or vice versa).
    visible_reason = (
        "visible matched"
        if state_matches and text_matches
        else (
            f"visible differed: state expected {turn.expected_visible_state}, "
            f"actual {outcome.status}; text expected {turn.expected_visible_text!r}, "
            f"actual {actual_text!r}"
        )
    )
    # `ToolRoutingEvaluator` judges only ATTEMPTED tool calls (Decision 1's
    # unmodified evaluator), so an `unauthorized`-antecedent case -- whose
    # model still attempts the call, per `injection-chat-text.json`'s
    # existing precedent -- needs a SEPARATE check that the trust boundary
    # actually held: no capability RESULT this turn beyond the declared set.
    results_matched = True
    results_reason = "tool results: not checked"
    if turn.expected_tool_result_names is not None:
        actual_result_names = tuple(result.tool_name for result in outcome.tool_results)
        results_matched = actual_result_names == turn.expected_tool_result_names
        results_reason = (
            f"tool results matched {turn.expected_tool_result_names}"
            if results_matched
            else (
                f"tool results differed: expected {turn.expected_tool_result_names}, "
                f"actual {actual_result_names}"
            )
        )
    # A live model's prose NEVER reproduces the deterministic double's exact
    # scripted text verbatim -- exactly why the Story 2.2/2.9 single-turn live
    # test (`test_golden_cases_against_live_agent_are_non_authoritative`)
    # scores a live run on routing/grounding/policy alone and never calls
    # `_visible_judgement`. The deterministic (authoritative) run keeps the
    # full precise contract; live keeps the same narrower proof the existing
    # precedent already established, or every live case would fail on prose
    # wording alone regardless of whether the model actually behaved.
    passed = routing.passed and policy.passed and results_matched
    if run_source != "live":
        passed = passed and state_matches and text_matches
    return EvalVerdict(
        passed=passed,
        reason=f"routing: {routing.reason}; policy: {policy.reason}; {visible_reason}; {results_reason}",
        run_source=run_source,
    )


def run_multi_turn_case(
    case: MultiTurnGoldenCase,
    modules: tuple[CapabilityModuleV1, ...],
    *,
    model: object | None = None,
    run_source: str = "double",
) -> MultiTurnCaseEvaluation:
    """Drive every turn of one versioned scenario through the PRODUCT SEAM.

    Story 5.6 Decision 2: calls `execute_turn` (never the single-turn direct
    `runtime.run_turn` helper `_run_runtime_case` uses) -- only `execute_turn`
    performs rehydration and the resume-transcript branch this proof needs.
    `model` is `None` for the authoritative deterministic double run and a
    real provider model for the non-authoritative live run; either way each
    turn still passes through this identical wiring.
    """
    outcomes: list[AgentRunOutcomeV1] = []
    turn_evaluations: list[TurnEvaluation] = []
    for index, turn in enumerate(case.turns):
        deps = _report_deps()
        history = _history_for_turn(turn, case.turns[:index], outcomes, deps)
        granted = tuple(
            module for module in modules
            if module.manifest.capability_name in turn.capabilities
        )
        provided_names = {module.manifest.capability_name for module in granted}
        missing = set(turn.capabilities) - provided_names
        if missing:
            raise ValueError(
                f"case {case.case_id!r} turn {index} names capability(ies) "
                f"{sorted(missing)}, which no supplied module provides"
            )
        # Predicts EXACTLY the owned `AgentTurnV1` `execute_turn` will inject,
        # by calling the SAME production functions it calls internally
        # (`rehydrate_history`, or the identical `[-HISTORY_MESSAGE_BOUND:]`
        # slice for an already-owned turn) -- never a second, independent
        # bound. Needed for both run sources: it sizes the double's response
        # offset AND (regardless of model) how many of `outcome.turn.messages`
        # belong to earlier turns rather than to this one.
        truncated_history_messages = (
            history.messages[-execute_turn_module.HISTORY_MESSAGE_BOUND:]
            if isinstance(history, AgentTurnV1)
            else rehydrate_history(history).messages
        )
        injected_message_count = len(truncated_history_messages)
        if model is not None:
            turn_model = model
        else:
            # Both `history_mode`s can legitimately inject assistant
            # `ModelResponse`s (a `raw_turn`'s real tool-calling assistant
            # messages, or a `rehydrated_activities` turn's own prior
            # `AgentResponseActivityV1`), so the offset is computed the same
            # way for either, never hardcoded to 0 for one of them.
            offset = history_response_offset_for(truncated_history_messages)
            turn_model = build_multi_turn_double(
                turn, label=f"{case.case_id}[{index}]", history_response_offset=offset
            )
        runtime = PydanticAIAgentRuntime(
            model=turn_model, capabilities=granted, deps=deps, answer_type=None,
        )
        try:
            outcome = execute_turn(
                runtime, deps, prompt=turn.prompt, calculation_results=[], history=history,
            )
        except Exception as exc:  # the production route has the same finalization rule
            outcome = failed_outcome_for_exception(exc)
        # The FULL outcome (history-included) is what the NEXT turn's
        # `raw_turn` mode must resume from -- an owned resume transcript that
        # only ever carried the latest turn would drop every earlier turn's
        # antecedents from a 3+-turn conversation.
        outcomes.append(outcome)
        # `AgentTurnV1` is explicitly "the durable transcript of one OR MORE
        # agent turns" (contracts/agent_runtime.py) -- a raw-resume-transcript
        # turn's `outcome.turn` legitimately carries every earlier turn's
        # messages too. Evaluating it unscoped would judge turn N against the
        # FULL accumulated conversation: an earlier turn's tool call would
        # double-count against THIS turn's `expected_tool_calls`, and an
        # earlier turn's already-granted capability would misreport as
        # "unregistered" the moment a later turn narrows the grant (exactly
        # the `unauthorized` fault case). Scoping to the NEW suffix -- for
        # evaluation only, never for what propagates forward -- is what makes
        # each turn's verdict actually about that turn.
        scoped_outcome = _trim_outcome_to_current_turn(outcome, injected_message_count)
        verdict = _evaluate_turn(turn, runtime, scoped_outcome, run_source=run_source)
        turn_evaluations.append(
            TurnEvaluation(turn_index=index, turn=turn, verdict=verdict, outcome=scoped_outcome)
        )
    return MultiTurnCaseEvaluation(case=case, turn_evaluations=tuple(turn_evaluations))


MULTI_TURN_BINDINGS: dict[str, str] = {
    "evaluator": "ToolRoutingEvaluator + PolicyOutcomeEvaluator v1, applied per turn",
    "model": "case-driven PydanticAI FunctionModel double, history-aware (evals/doubles.py)",
    "prompt": "versioned multi-turn prompts in backend/evals/golden_multi_turn/**/*.json",
    "policy": "AD-5 risk tags; only double-sourced verdicts are authoritative",
    "application": "ShiftMind Story 5.6 multi-turn evaluation (execute_turn + rehydrate_history)",
    "solver": "not applicable — no solver run",
    # "tool" is filled in per-run by the caller (the exact granted-module set a
    # case's turns actually exercised) -- see `generate_multi_turn_demonstration_report`.
}


def _multi_turn_scenario_specs(
    evaluations: Sequence[MultiTurnCaseEvaluation],
) -> tuple[_ScenarioSpec, ...]:
    identities = sorted(
        {identity for item in evaluations for identity in item.case.scenario_fixtures}
    )
    specs: list[_ScenarioSpec] = []
    for identity in identities:
        fixture_id, separator, version = identity.partition(":")
        if not separator or not fixture_id or not version:
            raise ValueError(f"scenario fixture {identity!r} must use fixture_id:version")
        specs.append(_ScenarioSpec(fixture_id=fixture_id, version=version))
    return tuple(specs)


def build_multi_turn_evaluation_report(
    evaluations: Sequence[MultiTurnCaseEvaluation], *, bindings: Mapping[str, object]
) -> dict[str, object]:
    authoritative = tuple(item for item in evaluations if item.authoritative)
    passed = sum(1 for item in authoritative if item.passed)
    return {
        "report_type": "evaluation-harness-multi-turn",
        "report_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Story 5.6: demonstrates multi-turn history/tool-continuity wiring; "
            "it does not decide the open Gate B 50-case aggregate floor or "
            "create a release-gate report."
        ),
        "release_gate_eligible": False,
        "release_gate_status": (
            "demonstration only — the Gate B release-gate decision remains open"
        ),
        "metrics": {
            "authoritative_case_count": len(authoritative),
            "passed": passed,
            "failed": len(authoritative) - passed,
            "live_results_excluded": len(evaluations) - len(authoritative),
        },
        "results": [
            {
                "case_id": item.case.case_id,
                "case_version": item.case.case_version,
                "risk_class": item.case.risk_class,
                "passed": item.passed,
                "authoritative": item.authoritative,
                "turns": [
                    {
                        "turn_index": turn_eval.turn_index,
                        "passed": turn_eval.verdict.passed,
                        "reason": turn_eval.verdict.reason,
                        "run_source": turn_eval.verdict.run_source,
                    }
                    for turn_eval in item.turn_evaluations
                ],
            }
            for item in evaluations
        ],
        "version_bindings": dict(bindings),
    }


def write_multi_turn_evaluation_report(
    output_path: Path,
    *,
    evaluations: Sequence[MultiTurnCaseEvaluation],
    declared_bindings: Mapping[str, object],
    dataset_files: Iterable[Path],
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
) -> dict[str, object]:
    dataset_paths = tuple(Path(path) for path in dataset_files)
    bindings = resolve_bindings(
        declared_bindings,
        repo_root=repo_root,
        fixtures=_multi_turn_scenario_specs(evaluations),
        dataset_files=dataset_paths,
        allow_dirty=allow_dirty,
    )
    report = build_multi_turn_evaluation_report(evaluations, bindings=bindings)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def generate_multi_turn_demonstration_report(
    output_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    golden_dir: Path | None = None,
    allow_dirty: bool = False,
) -> dict[str, object]:
    selected_golden_dir = (
        Path(golden_dir)
        if golden_dir is not None
        else repo_root / "backend" / "evals" / "golden_multi_turn"
    )
    cases = load_multi_turn_cases(selected_golden_dir)
    installed = installed_modules()
    evaluations = [run_multi_turn_case(case, installed) for case in cases]
    # The exact granted-module set actually exercised across every turn --
    # never the full installed set, for the same reason
    # `generate_demonstration_report` scopes its "tool" binding: regenerating
    # a narrower `golden_dir` subset must not falsely claim a module this run
    # never granted.
    exercised_names = sorted(
        {
            capability_name
            for case in cases
            for turn in case.turns
            for capability_name in turn.capabilities
        }
    )
    exercised_by_name = {module.manifest.capability_name: module for module in installed}
    return write_multi_turn_evaluation_report(
        output_path,
        evaluations=evaluations,
        declared_bindings={
            **MULTI_TURN_BINDINGS,
            "tool": ", ".join(
                f"{name}@{exercised_by_name[name].manifest.capability_version}"
                for name in exercised_names
                if name in exercised_by_name
            ),
        },
        dataset_files=sorted(selected_golden_dir.rglob("*.json")),
        repo_root=repo_root,
        allow_dirty=allow_dirty,
    )


# ---------------------------------------------------------------------------
# Story 5.6 Decision 5: explicit, opt-in, finite-budgeted live execution.
#
# `AgentBudgetV1` (agent/runtime.py) already bounds ONE turn's requests/tool
# calls/tokens/deadline. It does not, and must not, become the aggregate suite
# ceiling this needs: a per-turn budget large enough for one real scenario
# would let an unbounded NUMBER of cases each spend that much, so a second,
# explicit aggregate budget is required rather than reusing or widening it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveSuiteBudgetV1:
    """Every ceiling is REQUIRED and validated positive-finite at construction
    (Decision 5: "Validate positive finite ceilings"). There is no default —
    a caller cannot construct an unbounded live suite by omission.
    """

    case_limit: int
    request_limit: int
    tool_call_limit: int
    token_limit: int
    elapsed_seconds_limit: float
    spend_usd_limit: float

    def __post_init__(self) -> None:
        for name in (
            "case_limit", "request_limit", "tool_call_limit",
            "token_limit", "elapsed_seconds_limit", "spend_usd_limit",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a positive, finite number")
            if math.isnan(value) or math.isinf(value) or value <= 0:
                raise ValueError(f"{name} must be a positive, finite ceiling; got {value}")


@dataclass(frozen=True)
class LiveReadinessExceptionV1:
    """Decision 7 / AC7: the ONLY way a blocked live readiness verdict may
    ship anyway -- an explicit, validated, time-bounded record. An incomplete
    or expired exception blocks readiness exactly like having none at all;
    there is no code path that lets a missing field or a lapsed expiry pass
    silently as eligible.
    """

    owner: str
    rationale: str
    scope: str
    expires_at: datetime
    compensating_limitation: str

    def is_valid(self, *, now: datetime) -> bool:
        return bool(
            self.owner.strip()
            and self.rationale.strip()
            and self.scope.strip()
            and self.compensating_limitation.strip()
            and now < self.expires_at
        )


def _readiness_verdict(
    all_passed: bool,
    stopped_reason: str | None,
    exception: LiveReadinessExceptionV1 | None,
    *,
    now: datetime,
) -> str:
    if stopped_reason is None and all_passed:
        return "eligible"
    if exception is not None and exception.is_valid(now=now):
        return "excepted"
    return "blocked"


def _estimate_turn_cost_usd(
    usage: AgentUsageV1 | None, *, input_usd_per_mtok: float, output_usd_per_mtok: float
) -> float:
    if usage is None:
        return 0.0
    return (
        (usage.input_tokens or 0) / 1_000_000 * input_usd_per_mtok
        + (usage.output_tokens or 0) / 1_000_000 * output_usd_per_mtok
    )


def run_bounded_live_multi_turn_suite(
    cases: Sequence[MultiTurnGoldenCase],
    *,
    model: object,
    budget: LiveSuiteBudgetV1,
    model_name: str,
    input_usd_per_mtok: float = 0.0,
    output_usd_per_mtok: float = 0.0,
    exception: LiveReadinessExceptionV1 | None = None,
) -> dict[str, object]:
    """The explicit, bounded live counterpart of the deterministic CI suite.

    Never reads a credential or infers a model itself -- both are the
    caller's job, completed only after ITS OWN explicit opt-in validation, the
    same separation `generate_live_diagnostics` already keeps. Accounts
    cumulative actual usage/cost BEFORE each next case and stops fail-closed
    the moment any ceiling would be reached, persisting every case scored so
    far as a safe partial result rather than raising past collected evidence
    (AC2, AC7, Decision 5).
    """
    started = perf_counter()
    totals = {"requests": 0, "tool_calls": 0, "tokens": 0, "spend_usd": 0.0}
    results: list[dict[str, object]] = []
    stopped_reason: str | None = None
    installed = installed_modules()
    eligible_cases = tuple(case for case in cases if case.live_eligible)
    with models.override_allow_model_requests(True):
        for case in eligible_cases:
            if len(results) >= budget.case_limit:
                stopped_reason = "case_limit_exhausted"
                break
            if (perf_counter() - started) >= budget.elapsed_seconds_limit:
                stopped_reason = "elapsed_seconds_limit_exhausted"
                break
            if (
                totals["requests"] >= budget.request_limit
                or totals["tool_calls"] >= budget.tool_call_limit
                or totals["tokens"] >= budget.token_limit
                or totals["spend_usd"] >= budget.spend_usd_limit
            ):
                stopped_reason = "aggregate_budget_exhausted"
                break
            try:
                evaluation = run_multi_turn_case(case, installed, model=model, run_source="live")
                for turn_eval in evaluation.turn_evaluations:
                    usage = turn_eval.outcome.usage
                    if usage is not None:
                        totals["requests"] += usage.requests
                        totals["tool_calls"] += usage.tool_calls
                        totals["tokens"] += (usage.input_tokens or 0) + (usage.output_tokens or 0)
                    totals["spend_usd"] += _estimate_turn_cost_usd(
                        usage, input_usd_per_mtok=input_usd_per_mtok,
                        output_usd_per_mtok=output_usd_per_mtok,
                    )
                results.append({
                    "case_id": case.case_id,
                    "case_version": case.case_version,
                    "passed": evaluation.passed,
                    "authoritative": evaluation.authoritative,
                    "turns": [
                        {
                            "turn_index": turn_eval.turn_index,
                            "passed": turn_eval.verdict.passed,
                            "reason_classification": _classify_reason(turn_eval.verdict.reason),
                        }
                        for turn_eval in evaluation.turn_evaluations
                    ],
                })
            except Exception as exc:  # a bad case must not lose the suite's evidence
                results.append({
                    "case_id": case.case_id,
                    "case_version": case.case_version,
                    "passed": False,
                    "authoritative": False,
                    "reason_classification": "suite_exception",
                    "exception_type": type(exc).__name__,
                })
    elapsed_seconds = perf_counter() - started
    all_release_eligible_passed = bool(results) and all(
        item["passed"] for item in results
    )
    now = datetime.now(timezone.utc)
    readiness = _readiness_verdict(
        all_release_eligible_passed, stopped_reason, exception, now=now
    )
    return {
        "report_type": "evaluation-harness-multi-turn-live",
        "report_version": "1",
        "generated_at": now.isoformat(),
        "model": model_name,
        "authoritative": False,
        "opt_in": True,
        "budgeted": True,
        "cases_considered": len(eligible_cases),
        "cases_run": len(results),
        "stopped_reason": stopped_reason,
        "budget": asdict(budget),
        "usage": {**totals, "elapsed_seconds": elapsed_seconds},
        "results": results,
        "readiness": readiness,
        "exception": (
            None
            if exception is None
            else {**asdict(exception), "expires_at": exception.expires_at.isoformat(),
                  "valid_at_generation": exception.is_valid(now=now)}
        ),
    }


def generate_bounded_live_multi_turn_report(
    output_path: Path,
    *,
    model: object,
    model_name: str,
    budget: LiveSuiteBudgetV1,
    golden_dir: Path | None = None,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
    input_usd_per_mtok: float = 0.0,
    output_usd_per_mtok: float = 0.0,
    exception: LiveReadinessExceptionV1 | None = None,
) -> dict[str, object]:
    """The documented explicit command for Story 5.6's live suite (Task 3/5).

    Every release-eligible live scenario for the pinned provider/model must
    pass before the AI feature ships (AC7); this is what produces that
    evidence, bound to the same NFR27 dimensions the deterministic report
    carries, and it can never satisfy or replace that deterministic report --
    `run_bounded_live_multi_turn_suite`'s `authoritative: False` is preserved
    verbatim in the persisted file.
    """
    selected_golden_dir = (
        Path(golden_dir)
        if golden_dir is not None
        else repo_root / "backend" / "evals" / "golden_multi_turn"
    )
    cases = load_multi_turn_cases(selected_golden_dir)
    suite_result = run_bounded_live_multi_turn_suite(
        cases, model=model, budget=budget, model_name=model_name,
        input_usd_per_mtok=input_usd_per_mtok, output_usd_per_mtok=output_usd_per_mtok,
        exception=exception,
    )
    exercised_names = sorted(
        {
            capability_name
            for case in cases
            for turn in case.turns
            for capability_name in turn.capabilities
        }
    )
    installed = installed_modules()
    exercised_by_name = {module.manifest.capability_name: module for module in installed}
    bindings = resolve_bindings(
        {
            **MULTI_TURN_BINDINGS,
            "model": model_name,
            "tool": ", ".join(
                f"{name}@{exercised_by_name[name].manifest.capability_version}"
                for name in exercised_names
                if name in exercised_by_name
            ),
        },
        repo_root=repo_root,
        fixtures=_multi_turn_scenario_specs_for_cases(cases),
        dataset_files=sorted(selected_golden_dir.rglob("*.json")),
        allow_dirty=allow_dirty,
    )
    suite_result["version_bindings"] = bindings
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(suite_result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return suite_result


def _multi_turn_scenario_specs_for_cases(
    cases: Sequence[MultiTurnGoldenCase],
) -> tuple[_ScenarioSpec, ...]:
    identities = sorted({identity for case in cases for identity in case.scenario_fixtures})
    specs: list[_ScenarioSpec] = []
    for identity in identities:
        fixture_id, separator, version = identity.partition(":")
        if not separator or not fixture_id or not version:
            raise ValueError(f"scenario fixture {identity!r} must use fixture_id:version")
        specs.append(_ScenarioSpec(fixture_id=fixture_id, version=version))
    return tuple(specs)


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
    "LiveReadinessExceptionV1",
    "LiveSuiteBudgetV1",
    "MULTI_TURN_BINDINGS",
    "MultiTurnCaseEvaluation",
    "TurnEvaluation",
    "build_evaluation_report",
    "build_multi_turn_evaluation_report",
    "generate_bounded_live_multi_turn_report",
    "generate_demonstration_report",
    "generate_live_diagnostics",
    "generate_multi_turn_demonstration_report",
    "run_bounded_live_multi_turn_suite",
    "run_multi_turn_case",
    "write_evaluation_report",
    "write_multi_turn_evaluation_report",
]
