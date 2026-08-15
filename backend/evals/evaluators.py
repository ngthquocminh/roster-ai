"""Evaluation extension point and Story 2.2's single tool-routing evaluator."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal, Mapping, Protocol

from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.evidence_ref import EvidenceRefV1
from evals.cases import GoldenCase


RunSource = Literal["double", "live"]


@dataclass(frozen=True)
class EvalVerdict:
    passed: bool
    reason: str
    run_source: RunSource = "double"

    @property
    def authoritative(self) -> bool:
        """Only deterministic-double results may contribute release evidence."""
        return self.run_source == "double"


class Evaluator(Protocol):
    """Extension point for evaluators owned by later stories."""

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict: ...


@dataclass(frozen=True)
class ToolRoutingEvaluator:
    """Judge only tool name/arguments (or correct absence) against a case."""

    run_source: RunSource = "double"

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict:
        capability_result_call_ids = {
            result.tool_call_id for result in outcome.tool_results
        }
        actual = tuple(
            (part.tool_name or "", _arguments(part.tool_args_json))
            for message in outcome.turn.messages
            if message.role == "assistant"
            for part in message.parts
            if part.kind == "tool_call"
            if part.tool_name not in {"final_result", "clarification", "refusal"}
            if (
                part.tool_call_id in capability_result_call_ids
                or part.tool_name in {call.tool_name for call in case.expected_tool_calls}
            )
        )
        expected = tuple(
            (call.tool_name, call.arguments) for call in case.expected_tool_calls
        )

        if case.expected_outcome in ("refuse", "clarify") and not expected:
            if actual:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"expected {case.expected_outcome} with no tool call, "
                        f"but routed to {actual[0][0]!r}"
                    ),
                )
            return self._verdict(
                passed=True,
                reason=f"matched {case.expected_outcome}: no tool call was routed",
            )

        if len(actual) != len(expected):
            return self._verdict(
                passed=False,
                reason=(
                    f"tool-call count differed: expected {len(expected)}, "
                    f"actual {len(actual)}"
                ),
            )
        for index, ((actual_name, actual_args), (expected_name, expected_args)) in enumerate(
            zip(actual, expected)
        ):
            if actual_name != expected_name:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"tool name differed at call {index}: expected "
                        f"{expected_name!r}, actual {actual_name!r}"
                    ),
                )
            if actual_args != expected_args:
                return self._verdict(
                    passed=False,
                    reason=(
                        f"tool arguments differed at call {index}: expected "
                        f"{_stable(expected_args)}, actual {_stable(actual_args)}"
                    ),
                )
        return self._verdict(
            passed=True,
            reason=f"matched {len(expected)} expected tool route(s)",
        )

    def _verdict(self, *, passed: bool, reason: str) -> EvalVerdict:
        return EvalVerdict(
            passed=passed,
            reason=reason,
            run_source=self.run_source,
        )


def stable_evidence_ref(reference: EvidenceRefV1) -> str:
    """Stable locator oracle: no per-run activity, message, or tool-call UUID."""
    field_or_range = reference.field or ""
    # Both bounds, or neither. `start_minute` and `end_minute` are independently
    # optional on the contract, and the previous `or` emitted "amount:None-4320"
    # for a half-specified interval -- a string no authored expectation can ever
    # match, producing an unreadable diff instead of a clear failure.
    if reference.start_minute is not None and reference.end_minute is not None:
        field_or_range += f":{reference.start_minute}-{reference.end_minute}"
    return "|".join(
        (str(reference.scenario_version_id), reference.group, reference.record_id, field_or_range)
    )


def _matches_originating_compute_call(case: GoldenCase, claim: object) -> bool:
    """Discriminate an unknown result id from a claim that changed its inputs."""
    metric = getattr(claim, "metric", None)
    arguments = getattr(claim, "arguments", None)
    if arguments is None:
        return False
    actual_arguments = asdict(arguments)
    for expected in case.expected_tool_calls:
        if expected.tool_name != "scheduling_compute":
            continue
        request = expected.arguments.get("request")
        if not isinstance(request, Mapping):
            continue
        if request.get("metric") == metric and request.get("arguments") == actual_arguments:
            return True
    return False


@dataclass(frozen=True)
class GroundingEvaluator:
    """Judge exact evidence IDs and the authored per-case grounding oracle."""

    run_source: RunSource = "double"

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict:
        response = outcome.grounded_response
        if response is None or case.expected_grounding_outcome is None:
            return EvalVerdict(False, "grounded response or oracle is missing", self.run_source)
        actual_refs = tuple(
            stable_evidence_ref(reference)
            for claim in response.claims
            for reference in claim.evidence_refs
        )
        expected_failure = {
            "supported": None,
            "version_mismatch": "version_mismatch",
            "missing_evidence": "missing_evidence",
            "argument_mismatch": "missing_evidence",
        }[case.expected_grounding_outcome]
        actual_failures = tuple(claim.failure for claim in response.claims if claim.failure)
        if expected_failure is None:
            if actual_failures:
                return EvalVerdict(False, f"expected supported, got {actual_failures}", self.run_source)
        elif actual_failures != (expected_failure,):
            return EvalVerdict(
                False,
                f"oracle differed: expected {expected_failure}, actual {actual_failures}",
                self.run_source,
            )
        # AR11 deliberately exposes only `missing_evidence` for both an unknown
        # result id and a claim that changed the originating metric/arguments.
        # Keep that persisted vocabulary closed, but make the evaluation oracle
        # observe the input relation so its two golden cases are not duplicates.
        if case.expected_grounding_outcome in {"missing_evidence", "argument_mismatch"}:
            has_argument_mismatch = any(
                not _matches_originating_compute_call(case, claim)
                for claim in response.claims
            )
            expected_argument_mismatch = (
                case.expected_grounding_outcome == "argument_mismatch"
            )
            if has_argument_mismatch != expected_argument_mismatch:
                return EvalVerdict(
                    False,
                    "grounding input relation differed: expected "
                    f"argument_mismatch={expected_argument_mismatch}, "
                    f"actual={has_argument_mismatch}",
                    self.run_source,
                )
        # Compared on EVERY branch, not only the supported one. On a failure
        # branch the expectation is empty, and asserting that emptiness is what
        # proves AR11's non-retargeting rule: a failed claim must not emit a
        # locator naming some other record or version. Checking refs only when
        # the case already passed left `expected_evidence_refs` unread on three
        # of the four cases.
        if actual_refs != case.expected_evidence_refs:
            return EvalVerdict(
                False,
                f"evidence differed: expected {case.expected_evidence_refs}, actual {actual_refs}",
                self.run_source,
            )
        return EvalVerdict(
            True,
            f"matched grounding oracle {case.expected_grounding_outcome} and exact evidence IDs",
            self.run_source,
        )


@dataclass(frozen=True)
class PolicyOutcomeEvaluator:
    """Judge allow/refuse/clarify and protected execution against runtime facts."""

    runtime: object
    run_source: RunSource = "double"

    def evaluate(self, case: GoldenCase, outcome: AgentRunOutcomeV1) -> EvalVerdict:
        actual = (
            "clarify"
            if outcome.clarification is not None
            or outcome.resolved_clarification is not None
            else "refuse"
            if outcome.refusal is not None
            else "allow"
        )
        if actual != case.expected_outcome:
            return EvalVerdict(
                False,
                f"policy outcome differed: expected {case.expected_outcome}, actual {actual}",
                self.run_source,
            )
        registered = frozenset(
            getattr(self.runtime, "registered_capability_names", ())
        )
        outside_results = tuple(
            result.tool_name
            for result in outcome.tool_results
            if result.tool_name not in registered
        )
        if outside_results:
            return EvalVerdict(
                False,
                f"unregistered capability produced a result: {outside_results}",
                self.run_source,
            )

        risk_by_name = {
            module.manifest.capability_name: module.manifest.risk_class
            for module in getattr(self.runtime, "_granted", ())
        }
        protected_results = tuple(
            (result.tool_name, risk_by_name.get(result.tool_name))
            for result in outcome.tool_results
            if risk_by_name.get(result.tool_name)
            in {"draft", "compute", "consequential"}
        )
        if actual in {"clarify", "refuse"} and protected_results:
            return EvalVerdict(
                False,
                f"{actual} invoked consequential capability result(s): {protected_results}",
                self.run_source,
            )
        if actual in {"clarify", "refuse"} and outcome.status != "completed":
            return EvalVerdict(
                False,
                f"{actual} did not reach completed state: {outcome.status}",
                self.run_source,
            )
        return EvalVerdict(
            True,
            f"matched policy outcome {actual} with no unauthorized result",
            self.run_source,
        )


def _arguments(raw: str | None) -> object:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _stable(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "EvalVerdict", "Evaluator", "GroundingEvaluator", "PolicyOutcomeEvaluator", "RunSource",
    "ToolRoutingEvaluator", "stable_evidence_ref",
]
