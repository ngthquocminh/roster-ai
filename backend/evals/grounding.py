"""Deterministic grounding oracle driver for Story 2.7 golden cases."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_compute import SchedulingComputeResultV1
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.grounding import ClaimProposalV1
from application.grounding.gate import ground_answer
from evals.cases import GoldenCase


def ground_case_outcome(
    case: GoldenCase, outcome: AgentRunOutcomeV1, deps: AgentDepsV1
) -> AgentRunOutcomeV1:
    """Drive authored supported/falsification paths through the real gate."""
    if outcome.answer is None or case.expected_grounding_outcome is None:
        return outcome
    proposal = next(
        segment for segment in outcome.answer.segments
        if isinstance(segment, ClaimProposalV1)
    )
    reference = EvidenceRefV1(
        scenario_version_id=deps.scenario_version_id,
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        producing_run_version=None,
        baseline_schedule_version=None,
        group="demand",
        record_id="outbound:0",
        field="amount",
        start_minute=2880,
        end_minute=4320,
    )
    results: dict[str, SchedulingComputeResultV1] = {}
    if case.expected_grounding_outcome != "missing_evidence":
        result_version = (
            UUID(int=999)
            if case.expected_grounding_outcome == "version_mismatch"
            else deps.scenario_version_id
        )
        # The originating call uses the first turn's arguments. The authored
        # argument-mismatch answer deliberately changes only its proposal.
        call_arguments = case.scripted_turns[0].arguments["request"]["arguments"]
        from application.contracts.grounding import ClaimArgumentsV1
        trusted_arguments = ClaimArgumentsV1(**call_arguments)
        results[proposal.result_id] = SchedulingComputeResultV1(
            metric="required_demand_minutes",
            arguments=trusted_arguments,
            value=60,
            unit="minutes",
            evidence_refs=(replace(reference, scenario_version_id=result_version),),
            scenario_version_id=result_version,
            result_id=proposal.result_id,
        )
    grounded = ground_answer(outcome.answer, deps, results)
    return replace(outcome, grounded_response=grounded)


__all__ = ["ground_case_outcome"]
