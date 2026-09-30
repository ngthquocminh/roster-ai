"""G' phase 2b: record handles and `<claim>` fact tags (tier-0 checks)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_inspect import (
    SchedulingInspectRequestV1,
    scheduling_inspect,
)
from application.contracts.agent_runtime import AgentBudgetV1, AgentRunOutcomeV1
from application.contracts.grounding import (
    GroundedAnswerV2,
    GroundedFactV1,
    GroundedProseSegmentV1,
)
from application.grounding.claim_tags import FactTagPart, PlainTextPart, parse_claim_tags
from application.grounding.evidence_registry import EvidenceRegistry, trusted_records_by_handle
from application.grounding.gate import ground_answer
from application.use_cases.execute_turn import execute_turn, outcome_visible_text
from evals.fixture_projection import FIXTURE_IDENTITY, FixtureProjectionReader


def _deps() -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=UUID(int=1), site_id=FIXTURE_IDENTITY, membership_id=UUID(int=2),
        request_id=UUID(int=3), agent_run_id=UUID(int=4), conversation_id=UUID(int=5),
        scenario_id=FIXTURE_IDENTITY, scenario_version_id=FIXTURE_IDENTITY,
        policy_version="v1", clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc),
        projection_reader=FixtureProjectionReader(), connection=object(),
        remaining_budget=AgentBudgetV1(),
    )


def _workers(deps: AgentDepsV1):
    return scheduling_inspect(deps, SchedulingInspectRequestV1(group="workers"))


def _tag(ev: str, field: str, value: str, text: str = "the fact") -> str:
    return f"<claim ev='{ev}' field='{field}' value='{value}'>{text}</claim>"


def _ground(text: str) -> tuple[object, ...]:
    deps = _deps()
    results = (_workers(deps),)
    return ground_answer(
        GroundedAnswerV2(text=text), deps, {}, trusted_records_by_handle(results)
    ).segments


# -- registry and inspect -------------------------------------------------

def test_record_handles_are_prefixed_per_group_and_idempotent() -> None:
    registry = EvidenceRegistry()
    assert registry.handle_for_record("workers", "a") == "w1"
    assert registry.handle_for_record("workers", "b") == "w2"
    assert registry.handle_for_record("work-areas-and-tasks", "a") == "t1"
    assert registry.handle_for_record("workers", "a") == "w1"
    assert registry.record_for("t1") == ("work-areas-and-tasks", "a")
    assert registry.record_for("w9") is None
    # calculation handles keep their own `r` sequence
    assert registry.handle_for("some-result") == "r1"


def test_every_inspected_row_carries_its_handle() -> None:
    result = _workers(_deps())
    assert [item["ev"] for item in result.items] == [
        f"w{index}" for index in range(1, len(result.items) + 1)
    ]


# -- the I/O matrix -------------------------------------------------------

def test_a_supported_fact_carries_its_record_locator() -> None:
    (fact,) = _ground(_tag("w1", "qualifications", "pick", "A is qualified for pick"))
    assert isinstance(fact, GroundedFactV1)
    assert (fact.verdict, fact.failure, fact.field, fact.value) == (
        "supported", None, "qualifications", "pick")
    assert fact.text == "A is qualified for pick"
    (reference,) = fact.evidence_refs
    assert (reference.group, reference.record_id, reference.field) == (
        "workers", "w1", "qualifications")


@pytest.mark.parametrize(("ev", "field", "value", "failure"), [
    ("w1", "qualifications", "pack", "value_mismatch"),
    ("w1", "salary", "1", "unknown_field"),
    ("w1", "ev", "w1", "unknown_field"),
    ("w99", "name", "A", "missing_evidence"),
])
def test_an_unsupported_fact_is_failed_but_kept(ev, field, value, failure) -> None:
    before, fact, after = _ground("Note: " + _tag(ev, field, value) + " -- done.")
    assert before == GroundedProseSegmentV1(text="Note: ")
    assert (fact.verdict, fact.failure, fact.text) == ("failed", failure, "the fact")
    assert fact.evidence_refs == ()
    assert after == GroundedProseSegmentV1(text=" -- done.")


@pytest.mark.parametrize("value", ["38", "38.0", " 38 "])
def test_a_numeric_field_matches_by_numeric_equality(value) -> None:
    (fact,) = _ground(_tag("w1", "contracted_hours", value))
    assert fact.verdict == "supported"


def test_text_matches_exactly_and_a_nested_list_by_any_scalar() -> None:
    assert _ground(_tag("w1", "name", "A"))[0].verdict == "supported"
    assert _ground(_tag("w1", "name", "a"))[0].failure == "value_mismatch"
    # qualifications is a list of {task_id, rate}: either scalar matches.
    assert _ground(_tag("w1", "qualifications", "1.0"))[0].verdict == "supported"


def test_a_fact_read_on_another_version_is_a_version_mismatch() -> None:
    deps = _deps()
    records = trusted_records_by_handle((_workers(deps),))
    rotated = replace(deps, scenario_version_id=UUID(int=999))
    (fact,) = ground_answer(
        GroundedAnswerV2(text=_tag("w1", "name", "A")), rotated, {}, records).segments
    assert fact.failure == "version_mismatch"


@pytest.mark.parametrize(("text", "expected"), [
    ("x <claim ev='w1' field='name'>A</claim> y", "x A y"),          # missing attribute
    ("x <claim ev='w1' field='name' value='A'>A y", "x A y"),         # unclosed
    ("x <claim ev='w1' field='name' value='A'>A "
     "<claim ev='w2' field='name' value='B'>B</claim></claim> y", "x A B y"),  # nested
    ("x </claim> y", "x  y"),                                         # orphan close
    # an opener never closed with `>` (live run ad89854, B:2)
    ("Loader M03 — <claim ev='t6' field='function' value='Despatch</claim>, Main",
     "Loader M03 — Despatch, Main"),
    ("x <claim ev='t6' field='f' value='A\n- y", "x A\n- y"),        # never swallows the next line
    # the value closed but the tag did not (live run ad89854, C:1): keep the prose after it
    ("— <claim ev='t6' field='function' value='despatch'; area: main", "— despatch; area: main"),
    ("x <claim-note ev='w1'>A</claim-note> y",                        # another tag
     "x <claim-note ev='w1'>A</claim-note> y"),
])
def test_a_malformed_tag_shows_its_text_as_prose_without_the_syntax(text, expected) -> None:
    assert parse_claim_tags(text) == (PlainTextPart(expected),)
    assert _ground(text) == (GroundedProseSegmentV1(text=expected),)


def test_only_an_unterminated_opener_is_reported_malformed() -> None:
    from application.grounding.claim_tags import malformed_claim_tags

    assert malformed_claim_tags("x <claim ev='t6' field='f' value='A</claim>, B") == (
        "<claim ev='t6' field='f' value='A",)
    assert malformed_claim_tags(_tag("w1", "name", "A", "A")) == ()


def test_attributes_accept_either_quote_in_any_order() -> None:
    assert parse_claim_tags('<claim value="T1" field="q" ev="w3">t</claim>') == (
        FactTagPart(text="t", ev="w3", field="q", value="T1"),)


def test_placeholders_and_facts_share_one_answer() -> None:
    segments = _ground("Hi {{r9}} and " + _tag("w1", "name", "A", "A"))
    assert [getattr(segment, "kind") for segment in segments] == [
        "prose", "claim", "prose", "fact"]


def test_execute_turn_checks_facts_against_this_turns_inspect_rows() -> None:
    deps = _deps()

    class Runtime:
        def run_turn(self, _request):
            return AgentRunOutcomeV1(answer=GroundedAnswerV2(
                text=_tag("w1", "name", "A", "Worker A") + " and "
                + _tag("w1", "grade", "9", "grade nine")))

    outcome = execute_turn(Runtime(), deps, prompt="who is w1?",
                           calculation_results=[_workers(deps)])
    assert [fact.verdict for fact in outcome.grounded_response.facts] == ["supported", "failed"]
    assert outcome_visible_text(outcome) == (
        "Worker A and grade nine (unverified: value_mismatch)")
