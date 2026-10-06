"""Keyless tests for the Story 5.13 live golden-routing generator (Task 2) and the
recorded multi-turn evidence wiring (Task 3).

No test calls a provider: every runtime is built on the case-driven
deterministic double, scored with `run_source="live"`, which is exactly the
scoring path a real provider's outcome takes.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from adapters.telemetry.cost import estimate_cost_usd
from evals.cases import ExpectedToolCall, ForbiddenClaim, GoldenCase, load_cases
from evals.live_golden_routing import (
    OVERALL_THRESHOLD,
    VERDICT_KEY,
    build_routing_report,
    generate_live_routing_evidence,
    production_chat_grant,
    routing_verdict,
    run_routing_pass,
)
from evals.release_configuration import (
    PriceRatesV1,
    apply_override_environment,
    override_price_rates,
    replaced_exports,
    release_allowed_capabilities,
    resolve_compose_value,
)
from evals.report import (
    LiveReadinessExceptionV1,
    LiveSuiteBudgetV1,
    _runtime_for_case,
    generate_live_multi_turn_evidence,
    multi_turn_verdict_reasons,
)
from scripts.evidence_binding import REPO_ROOT

GOLDEN_DIR = REPO_ROOT / "backend" / "evals" / "golden"
MULTI_TURN_DIR = REPO_ROOT / "backend" / "evals" / "golden_multi_turn"
RATES = PriceRatesV1(input_usd_per_mtok=0.2, output_usd_per_mtok=1.2, cache_read_usd_per_mtok=0.02)
CLEAN_CODE = {"git_commit": "a" * 40, "working_tree_dirty": False}


def _double_factory(case, modules, sink):
    return _runtime_for_case(case, modules, sink)


def _cases(*ids: str) -> list[GoldenCase]:
    by_id = {case.case_id: case for case in load_cases(GOLDEN_DIR)}
    return [by_id[case_id] for case_id in ids]


def _misrouted(case: GoldenCase) -> GoldenCase:
    """The same case, expecting a tool the double never calls."""
    return replace(
        case,
        expected_tool_calls=(ExpectedToolCall(tool_name="scheduling_optimize", arguments={}),),
    )


def _pass(cases, **overrides):
    kwargs = dict(
        runtime_factory=_double_factory,
        allowed_capabilities=release_allowed_capabilities(),
        rates=RATES,
        spend_ceiling_usd=10.0,
        code=CLEAN_CODE,
    )
    kwargs.update(overrides)
    return run_routing_pass(cases, **kwargs)


# --------------------------------------------------------------------------- population


def test_release_allowed_set_comes_from_settings_defaults() -> None:
    allowed = release_allowed_capabilities()
    assert "shiftmind_demonstration" not in allowed
    assert {
        "scheduling_baseline", "scheduling_compute", "scheduling_draft",
        "scheduling_draft_discard", "scheduling_inspect", "scheduling_optimize",
    } == allowed


def test_percentages_are_computed_over_the_release_allowed_population() -> None:
    inspect, consequential, demo = _cases(
        "scheduling-inspect-wednesday-workers",
        "scheduling-baseline-approval-required",
        "demonstration-repeat-once",
    )
    run = _pass([inspect, _misrouted(_cases("scheduling-inspect-wednesday-demand")[0]),
                 consequential, _misrouted(demo)])

    # The demonstration case is recorded, never run: the chat path never offers it.
    assert run["cases_run"] == 3
    assert run["cases_not_offered"] == 1
    assert run["counted_cases"] == 3
    assert run["counted_routing_passed"] == 2
    assert run["overall_routing_percentage"] == pytest.approx(66.67)
    assert run["protected_cases"] == 1
    assert run["protected_routing_percentage"] == 100.0
    assert run["meets_thresholds"] is False


def test_demonstration_is_reported_but_never_counted() -> None:
    inspect, demo = _cases("scheduling-inspect-wednesday-workers", "demonstration-repeat-once")
    run = _pass([inspect, _misrouted(demo)])

    demo_record = next(r for r in run["results"] if r["capability"] == "demonstration")
    assert demo_record["counted"] is False
    assert demo_record["not_run_reason"] == "not_offered_on_chat_path"
    # It does not move the counted percentage.
    assert run["overall_routing_percentage"] == 100.0
    assert run["counted_cases"] == 1


def test_routing_alone_decides_a_case() -> None:
    """D9: a grounding failure is recorded beside routing and decides nothing."""
    (case,) = _cases("grounding-fact-supported")
    # The live grounding oracle now expects evidence the double never cites, so
    # grounding fails while the tool route is still exactly right.
    case = replace(case, live_expected_evidence_refs=("not-a-real-evidence-ref",))
    run = _pass([case])
    record = run["results"][0]
    assert record["grounding_passed"] is False
    assert record["routing_passed"] is True
    assert run["overall_routing_percentage"] == 100.0


def test_the_chat_grant_is_production_composition_without_compute() -> None:
    """Review decision 1: production's chat turn, not the case's own tool."""
    names = {module.manifest.capability_name for module in production_chat_grant()}
    assert names == {
        "scheduling_baseline", "scheduling_compute", "scheduling_draft",
        "scheduling_draft_discard", "scheduling_inspect",
    }


def test_every_case_is_offered_the_whole_chat_grant() -> None:
    seen: list[set[str]] = []

    def factory(case, modules, sink):
        seen.append({module.manifest.capability_name for module in modules})
        return _runtime_for_case(case, modules, sink)

    cases = _cases("scheduling-inspect-wednesday-workers", "scheduling-baseline-approval-required")
    run = _pass(cases, runtime_factory=factory)
    chat = {module.manifest.capability_name for module in production_chat_grant()}
    assert seen == [chat, chat]
    assert len(run["granted_tools"]) == len(chat)


def test_a_case_the_chat_path_never_offers_is_recorded_not_run_and_not_counted() -> None:
    inspect, optimize = _cases("scheduling-inspect-wednesday-workers", "optimize-valid-request")
    run = _pass([inspect, optimize])
    record = next(r for r in run["results"] if r["case_id"] == "optimize-valid-request")
    assert record["not_run_reason"] == "not_offered_on_chat_path"
    assert record["counted"] is False
    assert run["counted_cases"] == 1
    assert run["cases_run"] == 1
    assert run["complete"] is True


def _claiming(case: GoldenCase) -> GoldenCase:
    return replace(case, live_forbidden_claims=(
        ForbiddenClaim(claim_id="claims_promotion", question="Does it claim a promotion?"),
    ))


@pytest.mark.parametrize(
    ("p_yes", "outcome"), [(0.9, "fail"), (0.5, "uncertain"), (0.05, "pass")]
)
def test_a_forbidden_claim_decides_the_case_beside_routing(p_yes, outcome) -> None:
    (case,) = _cases("scheduling-baseline-approval-required")
    run = _pass([_claiming(case)],
                claim_judge=lambda case, reply: ({"claims_promotion": p_yes}, 0.001))
    record = run["results"][0]
    assert record["routing_passed"] is True
    assert record["claims"][0]["outcome"] == outcome
    assert record["passed"] is (outcome == "pass")
    if outcome != "pass":
        assert record["routing_classification"] == "forbidden_claim"
        assert run["protected_routing_percentage"] == 0.0


def test_an_unavailable_claim_judge_fails_the_case() -> None:
    def down(case, reply):
        raise RuntimeError("judge down")

    (case,) = _cases("scheduling-baseline-approval-required")
    record = _pass([_claiming(case)], claim_judge=down)["results"][0]
    assert record["claims"][0]["outcome"] == "unavailable"
    assert record["passed"] is False


def test_declared_claims_without_a_judge_are_refused_before_any_call(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    target = golden / "scheduling_baseline" / "draft-and-promotion-same-turn.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        (GOLDEN_DIR / "scheduling_baseline" / "draft-and-promotion-same-turn.json").read_bytes()
    )

    def never(case, modules, sink):
        raise AssertionError("no case may run")

    with pytest.raises(ValueError, match="no claim judge"):
        generate_live_routing_evidence(
            tmp_path / "out.json", runtime_factory=never, model_name="m",
            configuration={}, rates=RATES, golden_dir=golden, allow_dirty=True,
        )


def test_live_ineligible_cases_do_not_run() -> None:
    (ineligible,) = _cases("draft-discard-valid")
    run = _pass([ineligible])
    assert run["cases_eligible"] == 0
    assert run["results"] == []
    assert run["overall_routing_percentage"] is None


# --------------------------------------------------------------------------- verdict


def _run(overall=100.0, protected=100.0, *, code=CLEAN_CODE, complete=True,
         spend_measured=True, results=None):
    return {
        "overall_routing_percentage": overall,
        "protected_routing_percentage": protected,
        "code": code,
        "complete": complete,
        "spend_measured": spend_measured,
        "results": results if results is not None else [{"case_id": "c", "case_version": "1"}],
    }


def test_three_clean_runs_meeting_both_thresholds_pass() -> None:
    assert routing_verdict([_run(), _run(), _run(90.0)]) == []


@pytest.mark.parametrize(
    ("runs", "reason"),
    [
        ([_run(), _run()], "fewer_than_required_runs"),
        ([_run(), _run(), _run(OVERALL_THRESHOLD - 0.01)], "overall_below_threshold"),
        ([_run(), _run(protected=90.0), _run()], "protected_below_threshold"),
        ([_run(), _run(protected=None), _run()], "protected_below_threshold"),
        ([_run(), _run(code={"git_commit": "b" * 40, "working_tree_dirty": False}), _run()],
         "runs_disagree_on_code"),
        ([_run(), _run(), _run(complete=False)], "run_incomplete"),
        ([_run(), _run(), _run(spend_measured=False)], "spend_not_measured"),
        ([_run(code={"git_commit": "a" * 40, "working_tree_dirty": True})] * 3,
         "clean_version_binding_missing"),
        ([_run(), _run(), _run(results=[{"case_id": "other", "case_version": "1"}])],
         "runs_disagree_on_population"),
    ],
)
def test_verdict_blocks_for_each_reason(runs, reason) -> None:
    assert reason in routing_verdict(runs)
    report = build_routing_report(
        runs, model_name="m", configuration={}, allowed_capabilities=frozenset()
    )
    assert report[VERDICT_KEY] == "blocked"


def test_passes_that_agree_but_not_with_the_bound_commit_block() -> None:
    other = {"git_commit": "b" * 40, "working_tree_dirty": False}
    assert routing_verdict([_run()] * 3) == []
    assert "runs_disagree_on_code" in routing_verdict([_run()] * 3, bound_code=other)


def test_a_valid_exception_marks_a_blocked_verdict_excepted_and_records_it() -> None:
    exception = LiveReadinessExceptionV1(
        owner="Minh", rationale="r", scope="s",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        compensating_limitation="l",
    )
    report = build_routing_report(
        [_run(80.0)] * 3, model_name="m", configuration={},
        allowed_capabilities=frozenset(), exception=exception,
    )
    assert report[VERDICT_KEY] == "excepted"
    assert report["blocking_reasons"] == ["overall_below_threshold"]
    assert report["exception"]["owner"] == "Minh"


def test_an_expired_exception_does_not_waive() -> None:
    exception = LiveReadinessExceptionV1(
        owner="Minh", rationale="r", scope="s",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        compensating_limitation="l",
    )
    report = build_routing_report(
        [_run(80.0)] * 3, model_name="m", configuration={},
        allowed_capabilities=frozenset(), exception=exception,
    )
    assert report[VERDICT_KEY] == "blocked"


# --------------------------------------------------------------------------- cost


def test_cost_is_accounted_per_case_at_the_given_rates() -> None:
    cases = _cases("scheduling-inspect-wednesday-workers", "scheduling-baseline-approval-required")
    run = _pass(cases)
    assert run["spend_measured"] is True
    per_case = [r["cost_usd"] for r in run["results"]]
    assert all(cost is not None and cost > 0 for cost in per_case)
    assert run["cost_usd"] == pytest.approx(sum(per_case), abs=1e-6)
    tokens = run["results"][0]["usage"]
    expected, _ = estimate_cost_usd(
        _Usage(**tokens), RATES.input_usd_per_mtok, RATES.output_usd_per_mtok,
        RATES.cache_read_usd_per_mtok,
    )
    assert per_case[0] == pytest.approx(expected)


class _Usage:
    def __init__(self, **values):
        self.__dict__.update(values)
        self.cache_write_tokens = None


def test_unpriced_rates_leave_spend_unmeasured() -> None:
    run = _pass(_cases("scheduling-inspect-wednesday-workers"),
                rates=PriceRatesV1(input_usd_per_mtok=0.0, output_usd_per_mtok=0.0))
    assert run["spend_measured"] is False
    assert "spend_not_measured" in routing_verdict([run] * 3)


def test_an_unpriced_case_stops_the_pass() -> None:
    cases = _cases("scheduling-inspect-wednesday-workers", "scheduling-inspect-wednesday-demand")
    run = _pass(cases, rates=PriceRatesV1(input_usd_per_mtok=0.0, output_usd_per_mtok=0.0))
    assert run["stopped_reason"] == "case_unpriced"
    assert run["complete"] is False
    assert run["cases_run"] == 1


def test_unmeasured_rates_are_refused_before_the_first_paid_call(tmp_path: Path) -> None:
    def never(case, modules, sink):
        raise AssertionError("no case may run")

    # One case that declares no claim, so only the price guard can refuse.
    golden = tmp_path / "golden"
    target = golden / "scheduling_inspect" / "wednesday-workers.json"
    target.parent.mkdir(parents=True)
    target.write_bytes((GOLDEN_DIR / "scheduling_inspect" / "wednesday-workers.json").read_bytes())
    with pytest.raises(ValueError, match="unmeasured"):
        generate_live_routing_evidence(
            tmp_path / "out.json", runtime_factory=never, model_name="m",
            configuration={}, rates=PriceRatesV1(input_usd_per_mtok=0.0, output_usd_per_mtok=0.0),
            golden_dir=golden, allow_dirty=True,
        )


def test_the_spend_ceiling_stops_the_pass_and_marks_it_incomplete() -> None:
    cases = _cases("scheduling-inspect-wednesday-workers", "scheduling-inspect-wednesday-demand")
    run = _pass(cases, spend_ceiling_usd=1e-9)
    assert run["stopped_reason"] == "spend_ceiling_reached"
    assert run["complete"] is False
    assert run["cases_run"] == 1


def test_override_rates_are_the_tracked_prices() -> None:
    rates = override_price_rates()
    assert rates.measured
    assert (rates.input_usd_per_mtok, rates.output_usd_per_mtok) == (0.2, 1.2)


def test_the_override_is_applied_as_compose_applies_it(tmp_path: Path, monkeypatch) -> None:
    """A literal beats an export; `${VAR:-x}` lets a non-empty export win."""
    override = tmp_path / "override.yml"
    override.write_text(
        "services:\n  api:\n    environment:\n"
        "      ZZ_LITERAL: '5'\n"
        "      ZZ_SUBSTITUTED: ${ZZ_SUBSTITUTED:-low}\n"
        "      ZZ_EMPTY: ${ZZ_EMPTY:-low}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZZ_LITERAL", "99")
    monkeypatch.setenv("ZZ_SUBSTITUTED", "high")
    monkeypatch.setenv("ZZ_EMPTY", "")

    assert replaced_exports(override) == ["ZZ_EMPTY", "ZZ_LITERAL"]
    applied = apply_override_environment(override)
    assert applied == {"ZZ_LITERAL": "5", "ZZ_SUBSTITUTED": "high", "ZZ_EMPTY": "low"}
    assert os.environ["ZZ_LITERAL"] == "5"


def test_compose_substitution_prefers_the_environment_then_the_default() -> None:
    assert resolve_compose_value("${X:-low}", {}) == "low"
    assert resolve_compose_value("${X:-low}", {"X": "high"}) == "high"
    assert resolve_compose_value("plain", {}) == "plain"


# --------------------------------------------------------------------------- redaction


def test_the_report_persists_no_prompt_argument_or_reply_content() -> None:
    cases = _cases(
        "scheduling-baseline-approval-bypass-real-tool",
        "scheduling-inspect-wednesday-workers",
        "draft-valid-multi",
    )
    run = _pass(cases)
    serialized = json.dumps(
        build_routing_report([run], model_name="m", configuration={},
                             allowed_capabilities=release_allowed_capabilities()),
        default=str,
    )
    for case in cases:
        assert case.prompt not in serialized
        assert case.expected_visible_text == "" or case.expected_visible_text not in serialized
    # Argument values the cases carry.
    assert "00000000-0000-0000-0000-00000000000b" not in serialized
    assert "max_hours" not in serialized
    assert "arguments" not in serialized


# --------------------------------------------------------------------------- end to end


def test_generated_evidence_is_bound_and_carries_the_verdict_key(tmp_path: Path) -> None:
    golden = tmp_path / "golden"
    golden.mkdir()
    for name in ("scheduling_inspect/wednesday-workers.json",
                 "scheduling_baseline/approval-required.json"):
        target = golden / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((GOLDEN_DIR / name).read_bytes())
    output = tmp_path / "live-golden-routing.json"
    report = generate_live_routing_evidence(
        output, runtime_factory=_double_factory, model_name="test:double",
        configuration={"agent_model": "test:double"}, rates=RATES, runs=3,
        golden_dir=golden, allow_dirty=True,
    )
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written[VERDICT_KEY] == report[VERDICT_KEY]
    assert len(written["runs"]) == 3
    assert written["version_bindings"]["code"]["git_commit"]
    # A dirty tree is recorded, and blocks the verdict on its own.
    if written["version_bindings"]["code"]["working_tree_dirty"]:
        assert "clean_version_binding_missing" in written["blocking_reasons"]
    assert all(run["meets_thresholds"] for run in written["runs"])


# --------------------------------------------------------------------------- multi-turn (Task 3)


_BUDGET = LiveSuiteBudgetV1(
    case_limit=20, request_limit=500, tool_call_limit=500, token_limit=10_000_000,
    elapsed_seconds_limit=600.0, spend_usd_limit=100.0,
)


class _DoubleIsTheModel:
    """`model=None` makes the multi-turn runner build the case's own double."""


def test_override_rates_make_multi_turn_spend_measured(tmp_path: Path, monkeypatch) -> None:
    import evals.report as report_module

    calls: list[dict] = []
    real_suite = report_module.run_bounded_live_multi_turn_suite

    def _suite(cases, **kwargs):
        calls.append(kwargs)
        kwargs = {**kwargs, "model": None}
        return real_suite(cases, **kwargs)

    monkeypatch.setattr(report_module, "run_bounded_live_multi_turn_suite", _suite)
    rates = override_price_rates()
    report = generate_live_multi_turn_evidence(
        tmp_path / "mt.json", model=_DoubleIsTheModel(), model_name="test:double",
        budget=_BUDGET, configuration={}, runs=1,
        input_usd_per_mtok=rates.input_usd_per_mtok,
        output_usd_per_mtok=rates.output_usd_per_mtok,
        allow_dirty=True,
    )
    assert calls[0]["input_usd_per_mtok"] == 0.2
    assert report["runs"][0]["spend_measured"] is True
    assert report["spend_measured"] is True
    assert "spend_not_measured" not in report["blocking_reasons"]
    assert "fewer_than_required_runs" in report["blocking_reasons"]


def test_multi_turn_without_rates_is_not_spend_measured(tmp_path: Path, monkeypatch) -> None:
    import evals.report as report_module

    real_suite = report_module.run_bounded_live_multi_turn_suite
    monkeypatch.setattr(
        report_module, "run_bounded_live_multi_turn_suite",
        lambda cases, **kwargs: real_suite(cases, **{**kwargs, "model": None}),
    )
    report = generate_live_multi_turn_evidence(
        tmp_path / "mt.json", model=_DoubleIsTheModel(), model_name="test:double",
        budget=_BUDGET, configuration={}, runs=1, allow_dirty=True,
    )
    assert report["spend_measured"] is False
    assert "spend_not_measured" in report["blocking_reasons"]


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda runs: runs[:2], "fewer_than_required_runs"),
        (lambda runs: [{**runs[0], "stopped_reason": "aggregate_budget_exhausted"}, *runs[1:]],
         "run_incomplete"),
        (lambda runs: [{**runs[0], "results": [{"passed": False}]}, *runs[1:]], "case_failed"),
        (lambda runs: [{**runs[0], "code": {"git_commit": "b" * 40,
                                              "working_tree_dirty": False}}, *runs[1:]],
         "runs_disagree_on_code"),
        (lambda runs: [{**runs[0], "results": [{"passed": True, "case_id": "other"}]},
                       *runs[1:]],
         "runs_disagree_on_population"),
    ],
)
def test_multi_turn_verdict_blocks_for_each_reason(mutate, reason) -> None:
    good = {"stopped_reason": None, "results": [{"passed": True}], "spend_measured": True,
            "code": CLEAN_CODE}
    assert multi_turn_verdict_reasons([good] * 3) == []
    assert reason in multi_turn_verdict_reasons(mutate([good] * 3))


def test_multi_turn_runs_that_disagree_with_the_bound_commit_block() -> None:
    good = {"stopped_reason": None, "results": [{"passed": True}], "spend_measured": True,
            "code": CLEAN_CODE}
    other = {"git_commit": "b" * 40, "working_tree_dirty": False}
    assert "runs_disagree_on_code" in multi_turn_verdict_reasons([good] * 3, bound_code=other)


def test_multi_turn_cost_prices_cache_reads_at_the_cache_rate() -> None:
    from application.contracts.agent_runtime import AgentUsageV1
    from evals.report import _estimate_turn_cost_usd

    usage = AgentUsageV1(requests=1, tool_calls=0, input_tokens=1_000_000,
                         output_tokens=0, cache_read_tokens=1_000_000)
    cost = _estimate_turn_cost_usd(
        usage, input_usd_per_mtok=RATES.input_usd_per_mtok,
        output_usd_per_mtok=RATES.output_usd_per_mtok,
        cache_read_usd_per_mtok=RATES.cache_read_usd_per_mtok,
    )
    # Every input token was a cache read: priced at 0.02, not the 0.2 input rate.
    assert cost == pytest.approx(0.02)
