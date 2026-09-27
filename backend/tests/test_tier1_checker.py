"""G' phase 3: tier-1 claim-support checker in shadow mode. Keyless: no test
here reaches the network (the Jev adapter runs over `httpx.MockTransport`)."""
from __future__ import annotations

from dataclasses import replace
import json
import logging

import httpx
import pytest

from adapters.grounding import factory
from adapters.grounding.factory import create_claim_support_checker
from adapters.grounding.jev_checker import (
    OPENROUTER_DECISIONS_ENDPOINT,
    TYPESAFE_ENDPOINT,
    JevClaimSupportChecker,
)
from adapters.grounding.stub_checker import StubClaimSupportChecker
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.grounding import GroundedAnswerV2
from application.ports.claim_support import ClaimSupportItemV1
from application.use_cases.execute_turn import execute_turn
from settings import InvalidFlagError, Settings, default_settings
from tests.test_fact_tags import _deps, _tag, _workers

# -- configuration and provider selection ----------------------------------


def _settings(**overrides) -> Settings:
    base = replace(default_settings(), grounding_tier1_mode="shadow",
                   typesafe_api_key=None, openrouter_api_key=None,
                   agent_runtime_model="deterministic", agent_runtime_api_key=None)
    return replace(base, **overrides)


def test_mode_defaults_to_off_and_off_builds_nothing(monkeypatch) -> None:
    monkeypatch.delenv("GROUNDING_TIER1_MODE", raising=False)
    assert default_settings().grounding_tier1_mode == "off"
    assert create_claim_support_checker(
        _settings(grounding_tier1_mode="off", typesafe_api_key="k")) is None


def test_an_unknown_mode_fails_closed_at_start(monkeypatch) -> None:
    monkeypatch.setenv("GROUNDING_TIER1_MODE", "strip")
    with pytest.raises(InvalidFlagError):
        default_settings()


@pytest.mark.parametrize(("overrides", "endpoint", "model"), [
    # auto prefers TypeSafe directly when its key is set ...
    ({"typesafe_api_key": "ts", "openrouter_api_key": "or"}, TYPESAFE_ENDPOINT, "jev-latest"),
    # ... and falls back to OpenRouter otherwise
    ({"openrouter_api_key": "or"}, OPENROUTER_DECISIONS_ENDPOINT, "typesafe/jev-1.13"),
    # the agent's own OpenRouter key counts (the live stack passes only that one)
    ({"agent_runtime_model": "openrouter:x/y", "agent_runtime_api_key": "agent"},
     OPENROUTER_DECISIONS_ENDPOINT, "typesafe/jev-1.13"),
    # the flag overrides auto
    ({"grounding_tier1_provider": "openrouter", "typesafe_api_key": "ts",
      "openrouter_api_key": "or"}, OPENROUTER_DECISIONS_ENDPOINT, "typesafe/jev-1.13"),
    ({"grounding_tier1_provider": "typesafe", "typesafe_api_key": "ts",
      "grounding_tier1_model": "jev-1.13"}, TYPESAFE_ENDPOINT, "jev-1.13"),
])
def test_provider_selection(overrides, endpoint, model) -> None:
    checker = create_claim_support_checker(_settings(**overrides))
    assert isinstance(checker, JevClaimSupportChecker)
    assert (checker._endpoint, checker._model) == (endpoint, model)
    assert checker.provider == ("typesafe" if endpoint == TYPESAFE_ENDPOINT else "openrouter")


def test_a_missing_key_disables_the_checker_with_one_warning(caplog) -> None:
    factory._warned.clear()
    with caplog.at_level(logging.WARNING, logger=factory.__name__):
        assert create_claim_support_checker(_settings()) is None
        assert create_claim_support_checker(_settings()) is None
        # a typesafe provider forced with no typesafe key is disabled too
        assert create_claim_support_checker(_settings(
            grounding_tier1_provider="typesafe", openrouter_api_key="or")) is None
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 2  # one per distinct cause, never per turn
    assert all("or" not in record.getMessage().split() for record in warnings)


# -- the Jev adapter: request and response mapping -------------------------

#: Recorded response shape (docs.typesafe.ai/api, OpenRouter Decisions API).
RECORDED = {
    "model": "jev-1.13.0",
    "answers": {"s0": {"type": "noul", "noul": 0.97}, "s2": {"type": "noul", "noul": 0.08}},
    "usage": {"input_tokens": 296, "output_tokens": 20},
}

ITEMS = (
    ClaimSupportItemV1("s0", "A is qualified for pick", "Worker record\nname: A"),
    ClaimSupportItemV1("s2", "A is not qualified for pick", "Worker record\nname: A"),
)


def _jev(handler, *, budget: int = 4000) -> JevClaimSupportChecker:
    return JevClaimSupportChecker(
        endpoint=TYPESAFE_ENDPOINT, api_key="secret", model="jev-latest",
        timeout_seconds=1.0, token_budget=budget,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_one_request_carries_one_noul_question_per_fact() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=RECORDED)

    result = _jev(handler).check(ITEMS)
    assert result.probabilities == {"s0": 0.97, "s2": 0.08}
    assert (result.error, result.skipped) == (None, 0)
    (request,) = seen
    assert request.headers["Authorization"] == "Bearer secret"
    body = json.loads(request.content)
    assert body["model"] == "jev-latest"
    assert set(body["questions"]) == {"s0", "s2"}
    assert {q["type"] for q in body["questions"].values()} == {"noul"}
    # each question points at its own fact and record in the state, and the
    # state holds nothing but the facts' text and their records
    assert body["state"] == {"facts": {
        "f0": {"claim": ITEMS[0].claim_text, "record": ITEMS[0].evidence_text},
        "f1": {"claim": ITEMS[1].claim_text, "record": ITEMS[1].evidence_text},
    }}
    assert "`facts.f1.claim`" in body["questions"]["s2"]["instructions"]


@pytest.mark.parametrize(("handler", "error"), [
    (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
    (lambda request: httpx.Response(529), "http_529"),
    (lambda request: httpx.Response(200, json={"answers": {}}), "bad_response"),
    (lambda request: httpx.Response(200, text="not json"), "bad_response"),
])
def test_provider_failures_become_closed_codes_never_exceptions(handler, error) -> None:
    result = _jev(handler).check(ITEMS)
    assert result.error == error


def test_an_oversized_state_is_split_and_a_too_large_fact_is_skipped() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json={"answers": {
            qid: {"type": "noul", "noul": 0.9} for qid in body["questions"]}})

    huge = ClaimSupportItemV1("s9", "x", "y" * 2000)
    result = _jev(handler, budget=150).check((*ITEMS, huge))
    assert len(bodies) == 2  # each normal fact alone fits; together they do not
    assert set(result.probabilities) == {"s0", "s2"}
    assert result.skipped == 1


# -- the shadow hook, every matrix row with the double ---------------------


class _Sink:
    def __init__(self) -> None:
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


def _turn(text: str, checker, *, telemetry=None):
    deps = replace(_deps(), telemetry=telemetry)

    class Runtime:
        def run_turn(self, _request):
            return AgentRunOutcomeV1(answer=GroundedAnswerV2(text=text))

    return execute_turn(Runtime(), deps, prompt="q", calculation_results=[_workers(deps)],
                        claim_checker=checker)


TWO_FACTS = (_tag("w1", "name", "A", "It is worker A") + " and "
             + _tag("w1", "qualifications", "pick", "A is qualified for pick"))


def test_shadow_two_supported_facts_make_one_call_and_record_probabilities() -> None:
    checker, sink = StubClaimSupportChecker(0.8), _Sink()
    plain = _turn(TWO_FACTS, None).grounded_response
    shadow = _turn(TWO_FACTS, checker, telemetry=sink).grounded_response
    (items,) = checker.calls
    assert [item.claim_text for item in items] == ["It is worker A", "A is qualified for pick"]
    assert "name: A" in items[0].evidence_text and "ev" not in items[0].evidence_text.split()
    assert [fact.support_probability for fact in shadow.facts] == [0.8, 0.8]
    # nothing else about the response changes
    assert replace(shadow, segments=tuple(
        replace(s, support_probability=None) if s.kind == "fact" else s
        for s in shadow.segments)) == plain
    (record,) = sink.records
    assert record.event == "grounding.tier1.completed"
    assert record.labels == {"tier1_outcome": "ok", "tier1_provider": "stub",
                             "tier1_checked": "2", "tier1_skipped": "0",
                             "tier1_low": "0", "tier1_mid": "2", "tier1_high": "0"}
    assert "worker A" not in repr(record)


def test_mode_off_makes_no_request_and_leaves_the_field_null() -> None:
    response = _turn(TWO_FACTS, None).grounded_response
    assert [fact.support_probability for fact in response.facts] == [None, None]


@pytest.mark.parametrize("text", [
    "Only prose here, and a value {{r1}}.",
    _tag("w1", "name", "Z", "a fact that failed tier 0"),
])
def test_no_supported_fact_means_no_request(text) -> None:
    checker = StubClaimSupportChecker()
    _turn(text, checker)
    assert checker.calls == []


def test_a_checker_failure_leaves_the_response_unchanged_and_reports_a_code() -> None:
    sink = _Sink()
    plain = _turn(TWO_FACTS, None).grounded_response
    failed = _turn(TWO_FACTS, StubClaimSupportChecker(error="timeout"), telemetry=sink)
    assert failed.status == "completed" and failed.grounded_response == plain
    assert sink.records[0].labels["tier1_outcome"] == "timeout"


def test_a_checker_that_raises_is_swallowed() -> None:
    class Exploding:
        name = "boom"

        def check(self, items):
            raise RuntimeError("provider down")

    outcome = _turn(TWO_FACTS, Exploding())
    assert outcome.status == "completed"
    assert [fact.support_probability for fact in outcome.grounded_response.facts] == [None, None]


def test_a_batch_is_all_or_nothing_and_the_first_error_is_kept() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:  # first batch: one good answer, one boolean
            return httpx.Response(200, json={"answers": {
                "s0": {"type": "noul", "noul": 0.9}, "s2": {"type": "noul", "noul": True}}})
        return httpx.Response(503)

    result = _jev(handler).check(ITEMS)
    assert result.probabilities == {}  # s0 is not kept from the failed batch
    assert result.error == "bad_response"


def test_a_budget_below_one_fact_reports_all_skipped() -> None:
    result = _jev(lambda request: httpx.Response(200, json=RECORDED), budget=10).check(ITEMS)
    assert (result.probabilities, result.skipped, result.error) == ({}, 2, "all_skipped")


def test_the_timeout_bounds_the_whole_turn_not_each_batch() -> None:
    checker = _jev(lambda request: httpx.Response(200, json={"answers": {
        qid: {"type": "noul", "noul": 0.9} for qid in json.loads(request.content)["questions"]}}),
        budget=150)
    checker._timeout = 0.0  # already spent before the first batch
    result = checker.check(ITEMS)
    assert (result.probabilities, result.skipped, result.error) == ({}, 2, "timeout")


# -- bare-value facts and the live-eval report ------------------------------

@pytest.mark.parametrize(("text", "value", "bare"), [
    ("C Fork | Grid P 8GR", "C Fork | Grid P 8GR", True),
    ("**C Fork | Grid P 8GR**", "C Fork | Grid P 8GR", True),
    ("pick.", "Pick", True),
    ("A is qualified for pick", "pick", False),
    ("Maximum Agency Shifts: 6 weekly", "6", False),
    ("", "", False),
])
def test_restates_value_only(text, value, bare) -> None:
    from application.grounding.claim_tags import restates_value_only

    assert restates_value_only(text, value) is bare


def test_a_fact_that_only_restates_its_value_is_not_sent_to_tier1() -> None:
    checker = StubClaimSupportChecker()
    response = _turn(_tag("w1", "name", "A", "**A**") + " and "
                     + _tag("w1", "qualifications", "pick", "A is qualified for pick"),
                     checker).grounded_response
    (items,) = checker.calls
    assert [item.claim_text for item in items] == ["A is qualified for pick"]
    assert [fact.support_probability for fact in response.facts] == [None, 0.95]
    # only bare facts: no request at all
    bare = StubClaimSupportChecker()
    _turn(_tag("w1", "name", "A", "A"), bare)
    assert bare.calls == []


def test_the_report_summarises_checker_latency_provider_and_tier0_only_facts() -> None:
    from evals.live_conversations.reporting import summarize_tier1, tier1_fact_rows

    activity = {"response": {"segments": [
        {"kind": "fact", "text": "A", "field": "name", "value": "A",
         "verdict": "supported", "support_probability": None},
        {"kind": "fact", "text": "A is qualified for pick", "field": "qualifications",
         "value": "pick", "verdict": "supported", "support_probability": 0.2},
    ]}}
    turn = {"tier1_facts": tier1_fact_rows(activity), "tier1": {
        "labels": {"tier1_outcome": "ok", "tier1_provider": "typesafe"}, "duration_ms": 310.0}}
    summary = summarize_tier1([{"run_id": "r", "prefixes": [
        {"scenario": "A", "turns": [turn, {"tier1_facts": None, "tier1": None}]}]}])
    assert (summary["checked"], summary["tier0_only"], summary["supported_unchecked"]) == (1, 1, 0)
    assert summary["checker_providers"] == {"typesafe": 1}
    assert summary["checker_outcomes"] == {"ok": 1}
    assert summary["checker_latency_ms"] == {"median": 310.0, "p95": 310.0, "max": 310.0}
    assert [fact["text"] for fact in summary["low_probability"]] == ["A is qualified for pick"]


def test_the_live_wording_probe_is_balanced_and_keyless_importable() -> None:
    from evals.tier1_probe import CASES

    assert len({case for case, *_ in CASES}) == len(CASES)
    expected = [supported for *_, supported in CASES]
    assert expected.count(False) >= expected.count(True) >= 4
