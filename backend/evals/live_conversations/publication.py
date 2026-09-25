"""Plan a finished live-suite run report's publication to Logfire (Story 5.10).

Pure: report bytes (and the credential values to refuse) in, a frozen
`PublicationPlan` or `PublicationRefused(reason)` out. No Logfire,
pydantic-evals or OpenTelemetry import -- `logfire_publish.py` is the only
module that talks to either.

The content rule (addendum section 6, channel 2, amended 2026-09-25): the plan
is built ONLY from the fields read below. Four are text -- the turn's user
message, its authored obligation, its visible reply (through the judge's own
`runner.visible_activity` projection, never re-implemented) and the judge's
reasons. Every other report field (`verified`, tool and command observations,
fixture setup, usage correlation, judge usage, the raw activity, failure-reason
strings) is never read into the plan. The Logfire `evals` category allows
`inputs`/`output` whatever they hold, so this field list is the whole boundary
for text: add a field only through an addendum change.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from adapters.telemetry import span_policy
from adapters.telemetry.conversation_trace import conversation_trace_ids
from evals.live_conversations.cases import load_scenarios
from evals.live_conversations.runner import visible_activity

REPORT_SCHEMA_VERSION = "1-development"
DATASET_NAME = "live-conversations"
JUDGE_DIMENSIONS = ("relevance", "continuity", "completeness", "clarification_refusal")
REASONING_EFFORTS = frozenset({"none", "low", "medium", "high"})
#: One case's four text fields together, serialized (measured maximum 3 KB).
MAX_CASE_TEXT_BYTES = 16 * 1024
#: Shorter credential values would match ordinary words.
MIN_CREDENTIAL_LENGTH = 8
USAGE_COUNTERS = ("input_tokens", "output_tokens", "requests", "tool_calls")

#: The planner's refusals; `logfire_publish.PUBLISH_REASONS` includes them.
PLAN_REASONS = frozenset({
    "report_unreadable",
    "report_schema_unsupported",
    "report_unfinished",
    "report_malformed",
    "report_contains_credential",
})

_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class PublicationRefused(Exception):
    def __init__(self, reason: str) -> None:
        assert reason in PLAN_REASONS, reason
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class VerdictSpan:
    conversation_id: UUID
    attributes: dict[str, Any]


@dataclass(frozen=True)
class PlannedCase:
    name: str
    inputs: dict[str, Any]
    metadata: dict[str, Any]
    output: dict[str, Any]
    #: `USAGE_COUNTERS` plus `estimated_cost_usd`, or `None` when unrecorded.
    usage: dict[str, int | float] | None


@dataclass(frozen=True)
class PublicationPlan:
    report_run_id: str
    report_sha256: str
    agent_model: str
    experiment_name: str
    experiment_metadata: dict[str, Any]
    verdict_spans: tuple[VerdictSpan, ...]
    cases: tuple[PlannedCase, ...]


def _malformed() -> PublicationRefused:
    return PublicationRefused("report_malformed")


def _require(value: Any, validator) -> Any:
    if validator(value) is None:
        raise _malformed()
    return value


def _positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _malformed()
    return value


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _malformed()
    return value


def _non_negative_number(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _malformed()
    return value


def _unix_nano(value: Any) -> int:
    if not isinstance(value, str):
        raise _malformed()
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _malformed() from None
    if moment.tzinfo is None:
        raise _malformed()
    return ((moment - _EPOCH) // timedelta(microseconds=1)) * 1000


def _iso_utc(unix_nano: int) -> str:
    """Microsecond ISO-8601 UTC, the `shiftmind.live_eval.occurred_at` shape."""
    moment = _EPOCH + timedelta(microseconds=unix_nano // 1000)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _judge_scores(judgment: Any) -> dict[str, dict[str, Any]]:
    if judgment is None:
        return {}
    if not isinstance(judgment, dict):
        raise _malformed()
    scores: dict[str, dict[str, Any]] = {}
    for dimension in JUDGE_DIMENSIONS:
        entry = judgment.get(dimension)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise _malformed()
        score, reason = entry.get("score"), entry.get("reason")
        if score is not None and (isinstance(score, bool) or score not in (0, 1, 2)):
            raise _malformed()
        if reason is not None and not isinstance(reason, str):
            raise _malformed()
        scores[dimension] = {"score": score, "reason": reason}
    return scores


def _usage(row: dict[str, Any]) -> dict[str, int | float] | None:
    usage = row.get("usage")
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise _malformed()
    if usage.get("usage_unavailable"):
        return None
    counters = usage.get("usage")
    if not isinstance(counters, dict):
        return None
    recorded: dict[str, int | float] = {}
    for name in USAGE_COUNTERS:
        if name in counters:
            recorded[name] = _non_negative_number(counters[name])
    if "estimated_cost_usd" in usage:
        recorded["estimated_cost_usd"] = _non_negative_number(usage["estimated_cost_usd"])
    return recorded or None


def _reply(row: dict[str, Any]) -> Any:
    activity = row.get("activity")
    if activity is None:
        return None
    if not isinstance(activity, dict):
        raise _malformed()
    try:
        reply = visible_activity(activity)
        json.dumps(reply)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _malformed() from None
    return reply


def _refuse_credentials(text: str, credential_values: frozenset[str]) -> None:
    for value in credential_values:
        if len(value) >= MIN_CREDENTIAL_LENGTH and value in text:
            raise PublicationRefused("report_contains_credential")


def plan_publication(
    report_bytes: bytes, *, credential_values: frozenset[str] = frozenset()
) -> PublicationPlan:
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PublicationRefused("report_unreadable") from None
    if not isinstance(report, dict):
        raise PublicationRefused("report_unreadable")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise PublicationRefused("report_schema_unsupported")
    finished_unix = report.get("finished_unix")
    if isinstance(finished_unix, bool) or not isinstance(finished_unix, int):
        raise PublicationRefused("report_unfinished")

    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    run_id = _require(report.get("run_id"), span_policy.validate_uuid)
    run_id = str(UUID(run_id))
    agent_model = _require(report.get("model"), span_policy.validate_model_id)
    judge_model = _require(report.get("judge_model"), span_policy.validate_model_id)
    configuration = report.get("configuration")
    code = report.get("code")
    if not isinstance(configuration, dict) or not isinstance(code, dict):
        raise _malformed()
    configuration_digest = _require(
        configuration.get("configuration_digest"), span_policy.validate_sha256
    )
    behavioral_digest = configuration.get("behavioral_digest")
    if behavioral_digest is not None:
        _require(behavioral_digest, span_policy.validate_sha256)
    reasoning_effort = configuration.get("reasoning_effort")
    if reasoning_effort not in REASONING_EFFORTS:
        raise _malformed()
    code_commit = code.get("git_commit")
    if not isinstance(code_commit, str) or not _GIT_COMMIT.fullmatch(code_commit):
        raise _malformed()
    started_unix = _int(report.get("started_unix"))

    scenario_ids = {scenario.id for scenario in load_scenarios()}
    executions = report.get("prefixes")
    if not isinstance(executions, list):
        raise _malformed()

    # Validate every execution; remember the last per (repetition, scenario).
    seen_conversations: set[UUID] = set()
    final_index: dict[tuple[int, str], int] = {}
    parsed: list[tuple[dict[str, Any], UUID | None, list[dict[str, Any]]]] = []
    for position, execution in enumerate(executions):
        if not isinstance(execution, dict):
            raise _malformed()
        scenario = execution.get("scenario")
        if scenario not in scenario_ids or span_policy.validate_scenario_id(scenario) is None:
            raise _malformed()
        repetition = _positive_int(execution.get("repetition"))
        _positive_int(execution.get("attempt"))
        turns = execution.get("turns")
        if not isinstance(turns, list):
            raise _malformed()
        raw_conversation = execution.get("conversation_id")
        conversation_id: UUID | None = None
        if raw_conversation is None:
            if turns:
                raise _malformed()
        else:
            if span_policy.validate_uuid(raw_conversation) is None:
                raise _malformed()
            conversation_id = UUID(raw_conversation)
            if conversation_id in seen_conversations:
                raise _malformed()
            seen_conversations.add(conversation_id)
        parsed.append((execution, conversation_id, turns))
        final_index[(repetition, scenario)] = position

    finals = set(final_index.values())
    verdict_spans: list[VerdictSpan] = []
    cases: list[PlannedCase] = []
    for position, (execution, conversation_id, turns) in enumerate(parsed):
        if conversation_id is None:
            continue
        scenario = execution["scenario"]
        repetition = execution["repetition"]
        attempt = execution["attempt"]
        final_attempt = position in finals
        trace_id, _parent = conversation_trace_ids(conversation_id)
        for index, row in enumerate(turns, 1):
            if not isinstance(row, dict) or row.get("id") != f"turn-{index}":
                raise _malformed()
            verdict = row.get("verdict")
            if verdict not in span_policy.TURN_VERDICTS:
                raise _malformed()
            agent_run_id = row.get("agent_run_id")
            if agent_run_id is not None:
                agent_run_id = str(UUID(_require(agent_run_id, span_policy.validate_uuid)))
            agent_run_status = row.get("agent_run_status")
            if agent_run_status is not None and agent_run_status not in span_policy.AGENT_RUN_STATUSES:
                raise _malformed()
            failures = row.get("factual_failures", [])
            if not isinstance(failures, list) or any(
                span_policy.validate_failure_code(code) is None for code in failures
            ):
                raise _malformed()
            activity = row.get("activity")
            occurred_at = activity.get("occurred_at") if isinstance(activity, dict) else None
            time_unix_nano = (
                _unix_nano(occurred_at) if occurred_at is not None else finished_unix * 10**9
            )
            judge_scores = _judge_scores(row.get("judgment"))
            usage = _usage(row)
            user, obligation = row.get("user"), row.get("obligation")
            if not isinstance(user, str) or not isinstance(obligation, str):
                raise _malformed()
            reply = _reply(row)

            attributes: dict[str, Any] = {
                "shiftmind.live_eval.turn_index": index,
                "shiftmind.live_eval.verdict": verdict,
                "shiftmind.live_eval.agent_model": agent_model,
                "shiftmind.live_eval.configuration_digest": configuration_digest,
                "shiftmind.live_eval.report.run_id": run_id,
                "shiftmind.live_eval.report.sha256": report_sha256,
                "shiftmind.conversation.id": str(conversation_id),
                "shiftmind.live_eval.scenario": scenario,
                "shiftmind.live_eval.repetition": repetition,
                "shiftmind.live_eval.attempt": attempt,
                "shiftmind.live_eval.final_attempt": final_attempt,
                # When the turn ran. The span itself is stamped at publication:
                # Logfire accepted, then silently dropped, spans backdated six
                # days (Story 5.10 Task 11, 2026-09-25).
                "shiftmind.live_eval.occurred_at": _iso_utc(time_unix_nano),
            }
            if agent_run_id is not None:
                attributes["shiftmind.agent_run.id"] = agent_run_id
            if agent_run_status is not None:
                attributes["shiftmind.live_eval.agent_run_status"] = agent_run_status
            if failures:
                attributes["shiftmind.live_eval.factual_failures"] = tuple(failures)
            verdict_spans.append(VerdictSpan(conversation_id, attributes))

            if not final_attempt:
                continue
            text = json.dumps(
                [user, obligation, reply, [s["reason"] for s in judge_scores.values()]],
                ensure_ascii=False,
            )
            if len(text.encode("utf-8")) > MAX_CASE_TEXT_BYTES:
                raise _malformed()
            _refuse_credentials(text, credential_values)
            cases.append(PlannedCase(
                name=f"{scenario}:{index}:rep{repetition}",
                inputs={
                    "scenario": scenario, "turn": index, "repetition": repetition,
                    "user": user, "obligation": obligation,
                },
                metadata={
                    "conversation_id": str(conversation_id),
                    "agent_run_id": agent_run_id,
                    "trace_id": f"{trace_id:032x}",
                },
                output={
                    "reply": reply,
                    "verdict": verdict,
                    "agent_run_status": agent_run_status,
                    "factual_failures": list(failures),
                    "judge_scores": judge_scores,
                },
                usage=usage,
            ))

    experiment_metadata: dict[str, Any] = {
        "report_run_id": run_id,
        "report_sha256": report_sha256,
        "agent_model": agent_model,
        "judge_model": judge_model,
        "configuration_digest": configuration_digest,
        "reasoning_effort": reasoning_effort,
        "code_commit": code_commit,
        "started_unix": started_unix,
        "finished_unix": finished_unix,
    }
    if behavioral_digest is not None:
        experiment_metadata["behavioral_digest"] = behavioral_digest
    return PublicationPlan(
        report_run_id=run_id,
        report_sha256=report_sha256,
        agent_model=agent_model,
        experiment_name=f"{agent_model} {run_id}",
        experiment_metadata=experiment_metadata,
        verdict_spans=tuple(verdict_spans),
        cases=tuple(cases),
    )


__all__ = [
    "DATASET_NAME",
    "PLAN_REASONS",
    "PlannedCase",
    "PublicationPlan",
    "PublicationRefused",
    "VerdictSpan",
    "plan_publication",
]
