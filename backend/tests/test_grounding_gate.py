from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_compute import SchedulingComputeResultV1
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.evidence_ref import DemandIntervalResolutionV1, EvidenceRefV1
from application.contracts.grounding import (
    ClaimArgumentsV1,
    ClaimProposalV1,
    GroundedAnswerV1,
    GroundedProseSegmentV1,
)
from application.contracts.scenario_projection import DemandIntervalV1
from application.grounding.gate import (
    SCOPE_CONTROLS,
    UncitedNumericProseError,
    ground_answer,
)

SITE = UUID(int=1)
SCENARIO = UUID(int=2)
VERSION = UUID(int=3)
OTHER_VERSION = UUID(int=4)
ARGS = ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60)


def _ref(record_id: str = "d1", version: UUID = VERSION) -> EvidenceRefV1:
    return EvidenceRefV1(
        scenario_version_id=version, checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1", checksum_digest="a" * 64,
        producing_run_version=None, baseline_schedule_version="baseline-v1",
        group="demand", record_id=record_id, field="amount",
        start_minute=0, end_minute=60,
    )


def _result(
    result_id: str, *, arguments: ClaimArgumentsV1 = ARGS,
    version: UUID = VERSION, record_id: str = "d1"
) -> SchedulingComputeResultV1:
    return SchedulingComputeResultV1(
        metric="required_headcount_minutes", arguments=arguments,
        value=60, unit="minutes", evidence_refs=(_ref(record_id, version),),
        scenario_version_id=version, result_id=result_id, consumed_row_count=1,
    )


class ReaderStub:
    def __init__(self, outcome: str = "resolved") -> None:
        self.outcome = outcome
        self.requested: list[tuple[UUID, str]] = []

    def resolve_demand_interval(
        self, _connection, scenario_id, scenario_version_id, record_id
    ):
        self.requested.append((scenario_version_id, record_id))
        if self.outcome == "unauthorized":
            return None
        item = None
        if self.outcome == "resolved":
            item = DemandIntervalV1(record_id, "outbound", "pick", None, 0, 60, 1, "headcount")
        return DemandIntervalResolutionV1(
            outcome=self.outcome,
            scenario_id=scenario_id,
            current_scenario_version_id=VERSION,
            item=item,
        )


def _deps(reader: ReaderStub) -> AgentDepsV1:
    ids = [UUID(int=value) for value in range(10, 15)]
    return AgentDepsV1(
        actor_id=ids[0], site_id=SITE, membership_id=ids[1], request_id=ids[2],
        agent_run_id=ids[3], conversation_id=ids[4], scenario_id=SCENARIO,
        scenario_version_id=VERSION, policy_version="v1",
        clock=lambda: datetime(2026, 8, 13, tzinfo=timezone.utc),
        projection_reader=reader, connection=object(),
        remaining_budget=AgentBudgetV1(),
    )


def _answer(*result_ids: str) -> GroundedAnswerV1:
    return GroundedAnswerV1(
        segments=tuple(
            ClaimProposalV1(
                metric="required_headcount_minutes", arguments=ARGS, result_id=result_id
            )
            for result_id in result_ids
        )
    )


def test_supported_citation_attaches_trusted_value_and_exact_locator() -> None:
    reader = ReaderStub()
    response = ground_answer(_answer("r1"), _deps(reader), {"r1": _result("r1")})
    claim = response.claims[0]
    assert (claim.verdict, claim.value, claim.failure) == ("supported", 60, None)
    assert claim.evidence_refs == (_ref(),)
    assert reader.requested == [(VERSION, "d1")]


@pytest.mark.parametrize(
    ("proposal", "results", "failure"),
    [
        (ClaimProposalV1(metric="required_headcount_minutes", arguments=ARGS, result_id=""), {}, "uncited_claim"),
        (ClaimProposalV1(metric="required_headcount_minutes", arguments=ARGS, result_id="fake"), {}, "missing_evidence"),
        (
            ClaimProposalV1(metric="required_headcount_minutes", arguments=ARGS, result_id="r1"),
            {"r1": _result("r1", arguments=ClaimArgumentsV1(task_id="pick", start_minute=60, end_minute=120))},
            "missing_evidence",
        ),
        (
            ClaimProposalV1(metric="required_headcount_minutes", arguments=ARGS, result_id="r1"),
            {"r1": _result("r1", version=OTHER_VERSION)},
            "version_mismatch",
        ),
    ],
)
def test_gate_falsifies_uncited_fabricated_argument_and_version_mismatch(
    proposal, results, failure
) -> None:
    response = ground_answer(GroundedAnswerV1(segments=(proposal,)), _deps(ReaderStub()), results)
    claim = response.claims[0]
    assert claim.verdict == "failed"
    assert claim.failure == failure
    assert claim.value is None and claim.evidence_refs == ()


def test_bare_unicode_decimal_digit_fails_the_whole_answer() -> None:
    with pytest.raises(UncitedNumericProseError):
        ground_answer(
            GroundedAnswerV1(segments=(GroundedProseSegmentV1(text="short by ٢ hours"),)),
            _deps(ReaderStub()),
            {},
        )


@pytest.mark.parametrize(
    ("resolver_outcome", "failure"),
    # `not_found` is calculation_failed, not missing_evidence: the locator came
    # from the calculator, which the model cannot influence, so attributing it
    # to model fabrication would put one label on both sides of the trust
    # boundary. version_mismatch and unauthorized_evidence are two of AR11's
    # three named EVIDENCE states and stay as they are.
    [("not_found", "calculation_failed"),
     ("version_mismatch", "version_mismatch"),
     ("unauthorized", "unauthorized_evidence")],
)
def test_exact_target_failure_never_retargets(resolver_outcome, failure) -> None:
    reader = ReaderStub(resolver_outcome)
    response = ground_answer(_answer("r1"), _deps(reader), {"r1": _result("r1", record_id="missing")})
    claim = response.claims[0]
    assert claim.failure == failure and claim.evidence_refs == ()
    assert reader.requested == [(VERSION, "missing")]


def test_one_failed_claim_preserves_supported_siblings_in_order() -> None:
    response = ground_answer(
        _answer("r1", "fake", "r3"),
        _deps(ReaderStub()),
        {"r1": _result("r1"), "r3": _result("r3")},
    )
    assert [claim.verdict for claim in response.claims] == ["supported", "failed", "supported"]
    assert response.claims[0].evidence_refs and response.claims[2].evidence_refs
    assert response.claims[1].failure == "missing_evidence"


def test_a_proven_empty_match_set_is_supported_without_locators() -> None:
    """Zero is the one value whose evidence is not a set of records --
    `EvidenceRefV1` addresses a `record_id` and absence has none. Failing it as
    `missing_evidence` blamed the model for the calculator's own output and
    made the only provably-correct answer unrenderable.
    """
    empty = SchedulingComputeResultV1(
        metric="required_headcount_minutes", arguments=ARGS, value=0,
        unit="minutes", evidence_refs=(), scenario_version_id=VERSION,
        result_id="r1", consumed_row_count=0,
    )
    claim = ground_answer(_answer("r1"), _deps(ReaderStub()), {"r1": empty}).claims[0]
    assert (claim.verdict, claim.value, claim.evidence_refs) == ("supported", 0, ())
    assert claim.failure is None


@pytest.mark.parametrize(
    ("value", "refs", "consumed"),
    # rows folded into a value but never cited -- a truncating calculator.
    [(60, 0, 3), (0, 0, 2), (60, 1, 2)],
)
def test_an_uncited_consumed_row_is_a_calculator_fault_not_model_fabrication(
    value, refs, consumed
) -> None:
    result = SchedulingComputeResultV1(
        metric="required_headcount_minutes", arguments=ARGS, value=value,
        unit="minutes", evidence_refs=tuple(_ref("d1") for _ in range(refs)),
        scenario_version_id=VERSION, result_id="r1", consumed_row_count=consumed,
    )
    claim = ground_answer(_answer("r1"), _deps(ReaderStub()), {"r1": result}).claims[0]
    assert claim.failure == "calculation_failed"


def test_a_nonzero_value_with_no_locator_can_never_render() -> None:
    """The empty-set allowance must not become a hole for trap #1: a value
    without a single citation is a fault regardless of the reported count.
    """
    result = SchedulingComputeResultV1(
        metric="required_headcount_minutes", arguments=ARGS, value=999,
        unit="minutes", evidence_refs=(), scenario_version_id=VERSION,
        result_id="r1", consumed_row_count=0,
    )
    claim = ground_answer(_answer("r1"), _deps(ReaderStub()), {"r1": result}).claims[0]
    assert (claim.verdict, claim.failure) == ("failed", "calculation_failed")


@pytest.mark.parametrize("text", ["about 5 hours", "roughly ⑥ shifts", "½ a shift"])
def test_prose_carrying_any_numeric_character_is_rejected(text) -> None:
    """`isdecimal()` is False for superscripts, circled digits and vulgar
    fractions, so the declared control over-claimed. isnumeric covers them.
    """
    with pytest.raises(UncitedNumericProseError):
        ground_answer(
            GroundedAnswerV1(segments=(GroundedProseSegmentV1(text=text),)),
            _deps(ReaderStub()),
            {},
        )


def test_scope_controls_state_coverage_and_non_coverage() -> None:
    assert SCOPE_CONTROLS
    assert all("NOT COVER" in description for description in SCOPE_CONTROLS.values())


def test_a_real_calculator_result_grounds_end_to_end_through_the_gate() -> None:
    """The seam AC1 actually rests on, exercised with no hand-built result.

    Every other test in this file constructs `SchedulingComputeResultV1` by
    hand, and `test_scheduling_compute.py` never calls `ground_answer`. So the
    chain that AC1 is a claim about -- calculator computes -> derives a
    content-addressed `result_id` -> model cites that id -> gate verifies and
    attaches the calculator's OWN locators -> supported claim -- was asserted
    nowhere end to end.
    """
    from application.capabilities.scheduling_compute import (
        SchedulingComputeRequestV1,
        derive_result_id,
        scheduling_compute,
    )
    from application.contracts.agent_runtime import AgentBudgetV1
    from evals.fixture_projection import (
        FIXTURE_IDENTITY,
        WEDNESDAY_END,
        WEDNESDAY_START,
        FixtureProjectionReader,
    )

    arguments = ClaimArgumentsV1(
        task_id="pick", family="outbound",
        start_minute=WEDNESDAY_START, end_minute=WEDNESDAY_END,
    )
    deps = AgentDepsV1(
        actor_id=UUID(int=20), site_id=FIXTURE_IDENTITY, membership_id=UUID(int=21),
        request_id=UUID(int=22), agent_run_id=UUID(int=23), conversation_id=UUID(int=24),
        scenario_id=FIXTURE_IDENTITY, scenario_version_id=FIXTURE_IDENTITY,
        policy_version="v1", clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc),
        projection_reader=FixtureProjectionReader(), connection=object(),
        remaining_budget=AgentBudgetV1(),
    )

    result = scheduling_compute(
        deps,
        SchedulingComputeRequestV1(
            metric="required_headcount_minutes", arguments=arguments
        ),
    )
    proposal = ClaimProposalV1(
        metric="required_headcount_minutes",
        arguments=arguments,
        result_id=result.result_id,
    )
    response = ground_answer(
        GroundedAnswerV1(segments=(proposal,)), deps, {result.result_id: result}
    )
    claim = response.claims[0]

    # The id the model cites is derivable, which is what makes a scripted
    # golden case able to name it literally.
    assert result.result_id == derive_result_id(
        "required_headcount_minutes", arguments, FIXTURE_IDENTITY
    )
    assert claim.verdict == "supported" and claim.failure is None
    # 720 minutes x 2 heads + 720 x 1: the calculator's value, not the model's.
    assert (claim.value, claim.unit) == (2160, "minutes")
    # The locators are the calculator's own, naming only rows it consumed --
    # the inbound, pack, volume and Thursday rows are all correctly excluded.
    assert [reference.record_id for reference in claim.evidence_refs] == [
        "d-outbound-0", "d-outbound-1",
    ]
    assert claim.evidence_refs == result.evidence_refs
