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
        metric="required_demand_minutes", arguments=arguments,
        value=60, unit="minutes", evidence_refs=(_ref(record_id, version),),
        scenario_version_id=version, result_id=result_id,
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
                metric="required_demand_minutes", arguments=ARGS, result_id=result_id
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
        (ClaimProposalV1(metric="required_demand_minutes", arguments=ARGS, result_id=""), {}, "uncited_claim"),
        (ClaimProposalV1(metric="required_demand_minutes", arguments=ARGS, result_id="fake"), {}, "missing_evidence"),
        (
            ClaimProposalV1(metric="required_demand_minutes", arguments=ARGS, result_id="r1"),
            {"r1": _result("r1", arguments=ClaimArgumentsV1(task_id="pick", start_minute=60, end_minute=120))},
            "missing_evidence",
        ),
        (
            ClaimProposalV1(metric="required_demand_minutes", arguments=ARGS, result_id="r1"),
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
    [("not_found", "missing_evidence"),
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


def test_scope_controls_state_coverage_and_non_coverage() -> None:
    assert SCOPE_CONTROLS
    assert all("NOT COVER" in description for description in SCOPE_CONTROLS.values())
