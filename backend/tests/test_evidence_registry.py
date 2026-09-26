"""Phase 1 of the G' grounding redesign: per-turn short citation handles."""
from __future__ import annotations

from application.capabilities.scheduling_compute import (
    SchedulingComputeRequestV1,
    _model_view,
    derive_result_id,
    scheduling_compute,
)
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.grounding import ClaimArgumentsV1
from application.grounding.evidence_registry import (
    EvidenceRegistry,
    trusted_results_by_citation,
)
from application.use_cases.execute_turn import execute_turn
from tests.test_grounding_gate import ARGS, ReaderStub, _answer, _deps, _result
from tests.test_scheduling_compute import ProjectionStub
from tests.test_scheduling_compute import _deps as _compute_deps

FULL_ID = "a" * 64


def test_handles_are_minted_in_first_seen_order_and_idempotently() -> None:
    registry = EvidenceRegistry()
    assert registry.handle_for("x") == "r1"
    assert registry.handle_for("y") == "r2"
    assert registry.handle_for("x") == "r1"
    assert registry.result_id_for("r2") == "y"
    assert registry.result_id_for("r9") is None
    assert registry.handle_of("z") is None


def test_every_new_deps_restarts_handles_at_r1() -> None:
    first, second = _deps(ReaderStub()), _deps(ReaderStub())
    first.evidence_registry.handle_for("x")
    assert second.evidence_registry.handle_for("y") == "r1"
    assert first.evidence_registry is not second.evidence_registry
    assert "evidence_registry" not in repr(first)


def test_trusted_results_are_keyed_by_full_id_and_handle() -> None:
    registry = EvidenceRegistry()
    registry.handle_for(FULL_ID)
    result = _result(FULL_ID)
    unrelated = object()
    assert trusted_results_by_citation([result, unrelated], registry) == {
        FULL_ID: result, "r1": result,
    }
    assert trusted_results_by_citation([result], None) == {FULL_ID: result}


def test_compute_shows_the_model_a_handle_and_keeps_the_trusted_id_canonical() -> None:
    deps = _compute_deps(ProjectionStub())
    first = SchedulingComputeRequestV1(
        metric="staffed_minutes",
        arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=60),
    )
    second = SchedulingComputeRequestV1(
        metric="staffed_minutes",
        arguments=ClaimArgumentsV1(task_id="pick", start_minute=0, end_minute=30),
    )
    a = scheduling_compute(deps, first)
    again = scheduling_compute(deps, first)
    b = scheduling_compute(deps, second)
    assert a.result_id == derive_result_id(first.metric, first.arguments, a.scenario_version_id)
    assert [_model_view(r).result_id for r in (a, again, b)] == ["r1", "r1", "r2"]


def _turn(cited: str, result_id: str = FULL_ID) -> AgentRunOutcomeV1:
    deps = _deps(ReaderStub())

    class Runtime:
        name = "scripted"

        def run_turn(self, _request):
            deps.evidence_registry.handle_for(result_id)
            return AgentRunOutcomeV1(answer=_answer(cited))

    return execute_turn(
        Runtime(), deps, prompt="how much?", calculation_results=[_result(result_id)]
    )


def test_a_handle_citation_grounds_and_persists_the_canonical_id() -> None:
    claim = _turn("r1").grounded_response.claims[0]
    assert (claim.verdict, claim.value, claim.result_id) == ("supported", 60, FULL_ID)


def test_a_full_id_returned_this_turn_still_resolves() -> None:
    claim = _turn(FULL_ID).grounded_response.claims[0]
    assert (claim.verdict, claim.result_id) == ("supported", FULL_ID)


def test_an_unknown_handle_is_missing_evidence_and_keeps_the_cited_value() -> None:
    claim = _turn("r9").grounded_response.claims[0]
    assert (claim.verdict, claim.failure, claim.result_id) == ("failed", "missing_evidence", "r9")
    assert claim.arguments == ARGS
