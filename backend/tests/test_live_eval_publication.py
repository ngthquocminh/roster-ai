"""Story 5.10: publishing a finished live-suite run report to Logfire.

Every publication runs the REAL publisher in a subprocess (`logfire.configure`
sets the process-global tracer provider, which this process must never have)
against a local HTTP server that decodes each OTLP body. Its environment comes
from `publisher_env`, which ALWAYS sets `LOGFIRE_TOKEN` and `LOGFIRE_BASE_URL`,
so `backend/.env`'s real token can never be loaded (`override=False`). No live
provider, no real token, no hosted Logfire.

The report is synthetic: two scenarios, a retried (non-final) attempt, a turn
with no activity, a `needs_review` turn, factual failures, and a conversation
whose UUID has zero low 64 bits. Excluded report fields carry Story 5.2's
secret and adversarial canaries plus a per-field marker; the four text fields
addendum section 6 publishes carry their own markers (and the prompt-injection
text, which must arrive as inert data).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from adapters.telemetry import span_policy
from adapters.telemetry.conversation_trace import conversation_traceparent_header
from api.tracing import conversation_traceparent
from evals.content_minimization_report import CREDENTIAL_ENV_VARS
from evals.live_conversations.publication import (
    MAX_CASE_TEXT_BYTES,
    PublicationRefused,
    plan_publication,
)
from tests.test_content_minimization import ADVERSARIAL_TEXT, INJECTION_TEXT, SECRET_CANARY
from tests.trace_capture import (
    ExportedSpan,
    ServerRequest,
    closed_port,
    decode_bodies,
    fixture_server,
    spans_from_requests,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
TOKEN_CANARY = "CANARY-LOGFIRE-5-10"
JUDGE_KEY_VAR = "LIVE_CONVERSATION_JUDGE_API_KEY"
SUBPROCESS_TIMEOUT = 120

RUN_ID = "5f0e7a52-51a0-4d41-9d8c-3c2a3b8f1a10"
MODEL = "openrouter:openai/gpt-test"
JUDGE_MODEL = "openrouter:google/judge-test"
DIGEST = "a" * 64
COMMIT = "b" * 40
STARTED, FINISHED = 1_789_000_000, 1_789_000_900

RETRIED = UUID("11111111-1111-4111-8111-111111111111")
FINAL_A = UUID("22222222-2222-4222-8222-222222222222")
#: Low 64 bits zero: the synthesized parent must become 1.
ZERO_LOW = UUID("33333333-3333-4333-0000-000000000000")

#: Included text: must arrive verbatim, in its case only.
MARK_USER = "MARK-USER-5-10"
MARK_OBLIGATION = "MARK-OBLIGATION-5-10"
MARK_REPLY = "MARK-REPLY-5-10"
MARK_REASON = "MARK-REASON-5-10"
#: Logfire's default scrubbing rewrites both of these (fact 6).
SCRUB_CODE = "unauthorized_effect"
SCRUB_SENTENCE = "Your session with the author is ready."

#: Excluded fields: one marker each, plus 5.2's canaries.
EXCLUDED = {
    "verified": "EXCLUDED-VERIFIED-5-10",
    "tool_observations": "EXCLUDED-TOOLS-5-10",
    "command_observations": "EXCLUDED-COMMANDS-5-10",
    "fixture_setup": "EXCLUDED-FIXTURE-5-10",
    "correlation": "EXCLUDED-CORRELATION-5-10",
    "judge_usage": "EXCLUDED-JUDGE-USAGE-5-10",
    "raw_activity": "EXCLUDED-RAW-ACTIVITY-5-10",
    "incomplete_reason": "EXCLUDED-INCOMPLETE-5-10",
}
EXCLUDED_CANARIES = (*EXCLUDED.values(), SECRET_CANARY, ADVERSARIAL_TEXT)


def _excluded(field: str) -> str:
    return f"{EXCLUDED[field]} {SECRET_CANARY} {ADVERSARIAL_TEXT}"


def _judgment(reason: str = "Relevant.") -> dict[str, Any]:
    return {
        "relevance": {"score": 2, "evidence_ids": [], "reason": reason},
        "continuity": {"score": 1, "evidence_ids": [], "reason": "Some continuity."},
        "completeness": {"score": 2, "evidence_ids": [], "reason": "Complete."},
        "clarification_refusal": {"score": None, "evidence_ids": [], "reason": "N/A."},
        "verdict": "pass",
    }


def _usage() -> dict[str, Any]:
    return {
        "event": "agent.run.completed",
        "correlation": {"actor_id": _excluded("correlation")},
        "usage": {"requests": 2, "tool_calls": 1, "input_tokens": 100, "output_tokens": 10},
        "estimated_cost_usd": 0.0015,
    }


def _prose(text: str, occurred_at: str) -> dict[str, Any]:
    return {
        "activity_type": "agent_response",
        "occurred_at": occurred_at,
        "debug": _excluded("raw_activity"),
        "response": {"segments": [{"kind": "prose", "text": text}]},
    }


def _turn(index: int, **fields: Any) -> dict[str, Any]:
    row = {
        "id": f"turn-{index}",
        "user": f"user message {index}",
        "obligation": f"obligation {index}",
        "verdict": "pass",
        "agent_run_id": str(UUID(int=0xA000 + index)),
        "agent_run_status": "agent_completed",
        "factual_failures": [],
        "judgment": _judgment(),
        "judge_usage": {"note": _excluded("judge_usage")},
        "usage": _usage(),
        "verified": {"note": _excluded("verified")},
        "judge_unknown_citations": [],
    }
    row.update(fields)
    return row


def _execution(scenario: str, attempt: int, conversation: UUID, turns: list, **extra) -> dict:
    return {
        "scenario": scenario, "endpoint": len(turns), "repetition": 1, "attempt": attempt,
        "status": "passed", "turns": turns, "conversation_id": str(conversation),
        "isolation_id": f"iso-{conversation.hex[:8]}",
        "fixture_setup": {"note": _excluded("fixture_setup")},
        "tool_observations": [{"note": _excluded("tool_observations")}],
        "command_observations": [{"note": _excluded("command_observations")}],
        **extra,
    }


def synthetic_report() -> dict[str, Any]:
    retried = _execution(
        "A", 1, RETRIED,
        [_turn(1, activity=_prose("a retried reply", "2026-09-19T06:00:00.000001Z"))],
        status="incomplete", incomplete_reason=_excluded("incomplete_reason"),
    )
    final_a = _execution("A", 2, FINAL_A, [
        _turn(
            1,
            user=f"{MARK_USER} {INJECTION_TEXT}",
            obligation=MARK_OBLIGATION,
            activity=_prose(MARK_REPLY, "2026-09-19T06:32:09.631032Z"),
            judgment=_judgment(MARK_REASON),
        ),
        _turn(
            2,
            verdict="needs_review",
            factual_failures=[SCRUB_CODE],
            activity=_prose(SCRUB_SENTENCE, "2026-09-19T06:33:00Z"),
        ),
        # Stopped before a reply: no activity, no run, no judgment.
        {"id": "turn-3", "user": "user message 3", "obligation": "obligation 3",
         "verdict": "incomplete"},
    ])
    final_b = _execution("B", 1, ZERO_LOW, [
        _turn(
            1,
            verdict="fail",
            agent_run_status="agent_failed",
            factual_failures=["unsuccessful_agent_turn"],
            activity={
                "activity_type": "clarification", "occurred_at": "2026-09-19T07:00:00+00:00",
                "clarification": {"question": "Which site?"},
            },
            usage={"usage_unavailable": True, "correlation": {"actor_id": _excluded("correlation")}},
        ),
    ])
    return {
        "schema_version": "1-development", "run_id": RUN_ID, "started_unix": STARTED,
        "model": MODEL, "judge_model": JUDGE_MODEL, "images_rebuilt": True,
        "code": {"git_commit": COMMIT, "working_tree_dirty": False},
        "configuration": {
            "agent": {"model": MODEL}, "judge": {"model": JUDGE_MODEL},
            "reasoning_effort": "low", "configuration_digest": DIGEST,
        },
        "images": None, "prefixes": [retried, final_a, final_b],
        "incomplete_reason": None, "finished_unix": FINISHED,
    }


def _bytes(report: dict[str, Any]) -> bytes:
    return json.dumps(report, indent=2).encode("utf-8")


# --- the subprocess harness ---------------------------------------------------


def publisher_env(token: str, base_url: str, **extra: str) -> dict[str, str]:
    """The ONE environment every publisher subprocess gets.

    Both Logfire variables are always set, so `load_dotenv(override=False)`
    cannot supply the real token from `backend/.env`; every credential
    variable is set empty for the same reason, unless a test sets it.
    """
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("LOGFIRE_", "OTEL_"))
    }
    for name in (*CREDENTIAL_ENV_VARS, JUDGE_KEY_VAR):
        env[name] = ""
    env["AGENT_TRACE_CONTENT_MODE"] = "off"
    env["LOGFIRE_TOKEN"] = token
    env["LOGFIRE_BASE_URL"] = base_url
    env.update(extra)
    return env


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str
    result: dict[str, Any]
    requests: list[ServerRequest]
    seconds: float

    def spans(self) -> list[ExportedSpan]:
        return spans_from_requests(
            decode_bodies([r.body for r in self.requests if r.method == "POST"])
        )

    def payload_text(self) -> str:
        return b"".join(
            message.SerializeToString()
            for message in decode_bodies([r.body for r in self.requests if r.method == "POST"])
        ).decode("latin-1") + json.dumps(
            [(s.name, s.attributes, s.resource) for s in self.spans()], default=str
        )


def _publish(report_path: Path, env: dict[str, str], seen: list[ServerRequest],
             args: tuple[str, ...] = ()) -> Run:
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", "evals.live_conversations.logfire_publish", str(report_path), *args],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
    )
    lines = completed.stdout.strip().splitlines()
    return Run(
        returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
        result=json.loads(lines[-1]) if lines else {},
        requests=list(seen), seconds=time.monotonic() - started,
    )


def publish(report_path: Path, behaviour: str = "ok", *, token: str = TOKEN_CANARY,
            args: tuple[str, ...] = (), **extra_env: str) -> Run:
    seen: list[ServerRequest] = []
    if behaviour == "unreachable":
        return _publish(
            report_path,
            publisher_env(token, f"http://127.0.0.1:{closed_port()}", **extra_env),
            seen,
        )
    with fixture_server(behaviour, seen) as url:
        return _publish(report_path, publisher_env(token, url, **extra_env), seen, args)


def _digests() -> dict[str, str]:
    tracked = subprocess.run(
        ["git", "ls-files", "evidence", "backend/evals/baselines"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert tracked, "no tracked evidence or baseline files were found"
    return {
        path: hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest() for path in tracked
    }


@pytest.fixture(scope="module")
def published(tmp_path_factory) -> tuple[Run, Path, dict[str, str], dict[str, str]]:
    report_path = tmp_path_factory.mktemp("publish") / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    before = {**_digests(), "report": hashlib.sha256(report_path.read_bytes()).hexdigest()}
    run = publish(report_path)
    after = {**_digests(), "report": hashlib.sha256(report_path.read_bytes()).hexdigest()}
    assert run.returncode == 0, (run.stdout, run.stderr)
    return run, report_path, before, after


def _verdicts(run: Run) -> list[ExportedSpan]:
    return [s for s in run.spans() if s.name == "live_eval.verdict"]


def _cases(run: Run) -> dict[str, ExportedSpan]:
    return {
        s.attributes["case_name"]: s
        for s in run.spans() if s.scope == "pydantic-evals" and "case_name" in s.attributes
        and s.name.startswith("case")
    }


def _json_attr(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


# --- AC1 ---------------------------------------------------------------------


def test_one_verdict_span_per_turn_of_every_attempt_in_its_conversation_trace(published) -> None:
    run = published[0]
    verdicts = _verdicts(run)
    report = synthetic_report()
    expected = [
        (execution, index, row)
        for execution in report["prefixes"]
        for index, row in enumerate(execution["turns"], 1)
    ]
    assert run.result["verdict_spans"] == len(expected) == len(verdicts) == 5
    by_key = {
        (s.attributes["shiftmind.conversation.id"], s.attributes["shiftmind.live_eval.turn_index"]): s
        for s in verdicts
    }
    report_sha256 = hashlib.sha256(published[1].read_bytes()).hexdigest()
    for execution, index, row in expected:
        conversation = UUID(execution["conversation_id"])
        span = by_key[(str(conversation), index)]
        low = (conversation.int & ((1 << 64) - 1)) or 1
        assert span.trace_id == conversation.hex
        assert span.parent_span_id == f"{low:016x}"
        # Stamped at publication, never backdated (Task 11: Logfire dropped
        # spans dated six days back); the turn's time is an attribute.
        assert abs(span.start_time_unix_nano - time.time_ns()) < 3600 * 10**9
        assert span.end_time_unix_nano >= span.start_time_unix_nano
        occurred = (row.get("activity") or {}).get("occurred_at")
        moment = (
            datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            if occurred else datetime.fromtimestamp(FINISHED, timezone.utc)
        )
        expected_occurred = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        attributes = {
            "shiftmind.live_eval.turn_index": index,
            "shiftmind.live_eval.verdict": row["verdict"],
            "shiftmind.live_eval.agent_model": MODEL,
            "shiftmind.live_eval.configuration_digest": DIGEST,
            "shiftmind.live_eval.report.run_id": RUN_ID,
            "shiftmind.live_eval.report.sha256": report_sha256,
            "shiftmind.conversation.id": str(conversation),
            "shiftmind.live_eval.scenario": execution["scenario"],
            "shiftmind.live_eval.repetition": 1,
            "shiftmind.live_eval.attempt": execution["attempt"],
            "shiftmind.live_eval.final_attempt": conversation != RETRIED,
            "shiftmind.live_eval.occurred_at": expected_occurred,
            "logfire.msg": "live_eval.verdict",
            "logfire.span_type": "span",
        }
        if row.get("agent_run_id"):
            attributes["shiftmind.agent_run.id"] = row["agent_run_id"]
        if row.get("agent_run_status"):
            attributes["shiftmind.live_eval.agent_run_status"] = row["agent_run_status"]
        if row.get("factual_failures"):
            attributes["shiftmind.live_eval.factual_failures"] = row["factual_failures"]
        assert span.attributes == attributes
    assert {s.parent_span_id for s in verdicts if s.trace_id == ZERO_LOW.hex} == {"0" * 15 + "1"}


def test_the_experiment_is_named_by_report_identity_and_covers_final_attempts_only(
    published,
) -> None:
    run = published[0]
    [experiment] = [s for s in run.spans() if s.name.startswith("evaluate")]
    attributes = experiment.attributes
    assert attributes["name"] == f"{MODEL} {RUN_ID}" == run.result["experiment"]
    assert attributes["dataset_name"] == "live-conversations"
    assert attributes["gen_ai.operation.name"] == "experiment"
    assert attributes["n_cases"] == 4 == run.result["cases"]  # the retried attempt is not a case
    # RecordedVerdict is the only boolean evaluator; 1 of 4 final turns passed.
    assert attributes["assertion_pass_rate"] == pytest.approx(0.25)
    metadata = _json_attr(attributes["metadata"])
    assert metadata["report_run_id"] == RUN_ID
    assert metadata["report_sha256"] == hashlib.sha256(published[1].read_bytes()).hexdigest()
    assert metadata["agent_model"] == MODEL and metadata["code_commit"] == COMMIT
    assert set(_cases(run)) == {"A:1:rep1", "A:2:rep1", "A:3:rep1", "B:1:rep1"}


def test_nothing_is_re_executed_the_case_output_is_the_recording(published) -> None:
    """The subprocess could reach nothing but the capture server; every case's
    output, scores and labels are exactly what the report recorded."""
    run = published[0]
    plan = plan_publication(published[1].read_bytes())
    cases = _cases(run)
    for planned in plan.cases:
        span = cases[planned.name].attributes
        assert _json_attr(span["output"]) == planned.output
        assert _json_attr(span["inputs"]) == planned.inputs
        scores = _json_attr(span["scores"])
        expected = {
            dim: entry["score"] for dim, entry in planned.output["judge_scores"].items()
            if entry["score"] is not None
        }
        assert {name: score["value"] for name, score in scores.items()} == expected
        labels = _json_attr(span["labels"])
        assert labels["verdict"]["value"] == planned.output["verdict"]
    usage_metrics = _json_attr(cases["A:1:rep1"].attributes["metrics"])
    assert usage_metrics["input_tokens"] == 100 and usage_metrics["estimated_cost_usd"] == 0.0015
    assert {r.method for r in run.requests} == {"POST"}


# --- content rule ---------------------------------------------------------------


def test_excluded_report_fields_never_leave(published) -> None:
    run = published[0]
    payload = run.payload_text()
    for canary in EXCLUDED_CANARIES:
        assert canary not in payload, canary
    assert TOKEN_CANARY not in payload
    for span in run.spans():
        assert not any(key.startswith("code.") for key in span.attributes), span.name


def test_included_text_arrives_verbatim_in_its_case_and_nowhere_else(published) -> None:
    run = published[0]
    case = _cases(run)["A:1:rep1"].attributes
    inputs, output = _json_attr(case["inputs"]), _json_attr(case["output"])
    assert inputs["user"] == f"{MARK_USER} {INJECTION_TEXT}"
    assert inputs["obligation"] == MARK_OBLIGATION
    assert output["reply"] == [{"text": MARK_REPLY}]
    assert _json_attr(case["scores"])["relevance"]["reason"] == MARK_REASON
    verdict_text = json.dumps([s.attributes for s in _verdicts(run)])
    for marker in (MARK_USER, MARK_OBLIGATION, MARK_REPLY, MARK_REASON):
        assert marker not in verdict_text
    for other_name, other in _cases(run).items():
        if other_name != "A:1:rep1":
            assert MARK_USER not in json.dumps(other.attributes)


def test_logfire_scrubbing_is_off_closed_codes_and_text_arrive_verbatim(published) -> None:
    run = published[0]
    [needs_review] = [
        s for s in _verdicts(run) if s.attributes["shiftmind.live_eval.verdict"] == "needs_review"
    ]
    assert needs_review.attributes["shiftmind.live_eval.factual_failures"] == [SCRUB_CODE]
    output = _json_attr(_cases(run)["A:2:rep1"].attributes["output"])
    assert output["reply"] == [{"text": SCRUB_SENTENCE}]
    assert "Scrubbed" not in run.payload_text()


def test_every_resource_is_rebuilt_and_tagged_live_eval(published) -> None:
    spans = published[0].spans()
    assert spans
    for span in spans:
        assert set(span.resource) == span_policy.RESOURCE_ALLOW | {"deployment.environment"}
        assert span.resource["deployment.environment"] == "live-eval"
        assert span.resource["service.name"] == "shiftmind-live-eval-publisher"


# --- AC2: untouched, never read back ---------------------------------------------


def test_only_otlp_posts_are_sent_and_report_baseline_evidence_are_untouched(published) -> None:
    run, _path, before, after = published
    assert run.requests and {(r.method, r.path) for r in run.requests} == {("POST", "/v1/traces")}
    assert before == after


def test_verdicts_only_writes_the_verdict_spans_and_no_experiment(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    run = publish(report_path, args=("--verdicts-only",))
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert {span.scope for span in run.spans()} == {"shiftmind.live_eval"}
    assert len(_verdicts(run)) == 5
    assert run.result["cases"] == 0


def test_a_failed_publication_touches_nothing_either(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    before = {**_digests(), "report": hashlib.sha256(report_path.read_bytes()).hexdigest()}
    run = publish(report_path, "rejected")
    after = {**_digests(), "report": hashlib.sha256(report_path.read_bytes()).hexdigest()}
    assert run.returncode == 1
    assert before == after


def test_token_absent_refuses_before_anything_is_sent(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    run = publish(report_path, token="")
    assert (run.returncode, run.result["outcome"], run.result["reason"]) == (
        2, "refused", "logfire_token_absent",
    )
    assert run.requests == []


@pytest.mark.parametrize("behaviour", ("unreachable", "rejected", "slow"))
def test_an_unavailable_logfire_exits_1_within_a_bound(tmp_path, behaviour) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    run = publish(report_path, behaviour)
    assert (run.returncode, run.result["outcome"], run.result["reason"]) == (
        1, "failed", "logfire_export_failed",
    ), (run.stdout, run.stderr)
    assert run.seconds <= 20 + 5  # + interpreter start and pydantic-ai import
    assert TOKEN_CANARY not in run.stdout + run.stderr


def test_a_refused_report_sends_nothing(tmp_path) -> None:
    report = synthetic_report()
    del report["finished_unix"]
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(report))
    run = publish(report_path)
    assert (run.returncode, run.result["reason"]) == (2, "report_unfinished")
    assert run.requests == []


def test_a_credential_in_the_text_refuses_and_is_never_printed(tmp_path) -> None:
    credential = "sk-or-CANARY-5-10-credential"
    report = synthetic_report()
    report["prefixes"][1]["turns"][0]["activity"]["response"]["segments"][0]["text"] = (
        f"the key is {credential}"
    )
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(report))
    run = publish(report_path, OPENROUTER_API_KEY=credential)
    assert (run.returncode, run.result["reason"]) == (2, "report_contains_credential")
    assert run.requests == []
    assert credential not in run.stdout + run.stderr


# --- planner-level refusals -------------------------------------------------------


def _mutated(mutate) -> bytes:
    report = copy.deepcopy(synthetic_report())
    mutate(report)
    return _bytes(report)


def _set(path: tuple, value: Any):
    def mutate(report: dict) -> None:
        target = report
        for key in path[:-1]:
            target = target[key]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
    return mutate


_DELETE = object()
REFUSALS = {
    "not json": (lambda: b"\xff{", "report_unreadable"),
    "not an object": (lambda: b"[]", "report_unreadable"),
    "schema": (lambda: _mutated(_set(("schema_version",), "2")), "report_schema_unsupported"),
    "unfinished": (lambda: _mutated(_set(("finished_unix",), None)), "report_unfinished"),
    "run id": (lambda: _mutated(_set(("run_id",), "run-1")), "report_malformed"),
    "model": (lambda: _mutated(_set(("model",), "gpt 5")), "report_malformed"),
    "digest": (
        lambda: _mutated(_set(("configuration", "configuration_digest"), "A" * 64)),
        "report_malformed",
    ),
    "canary failure code": (
        lambda: _mutated(_set(("prefixes", 1, "turns", 1, "factual_failures"), [SECRET_CANARY])),
        "report_malformed",
    ),
    "duplicate conversation": (
        lambda: _mutated(_set(("prefixes", 2, "conversation_id"), str(FINAL_A))),
        "report_malformed",
    ),
    "unknown scenario": (lambda: _mutated(_set(("prefixes", 0, "scenario"), "Z")), "report_malformed"),
    "turn id": (lambda: _mutated(_set(("prefixes", 1, "turns", 0, "id"), "turn-9")), "report_malformed"),
    "verdict": (
        lambda: _mutated(_set(("prefixes", 1, "turns", 0, "verdict"), "passed")),
        "report_malformed",
    ),
    "score": (
        lambda: _mutated(_set(("prefixes", 1, "turns", 0, "judgment", "relevance", "score"), 3)),
        "report_malformed",
    ),
    "oversized text": (
        lambda: _mutated(_set(
            ("prefixes", 1, "turns", 0, "user"), "x" * (MAX_CASE_TEXT_BYTES + 1)
        )),
        "report_malformed",
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_the_planner_refuses_with_a_closed_reason(case) -> None:
    build, reason = REFUSALS[case]
    with pytest.raises(PublicationRefused) as refused:
        plan_publication(build())
    assert refused.value.reason == reason


def test_the_credential_check_matches_exact_values_of_eight_or_more_characters() -> None:
    def with_reply(text: str) -> bytes:
        return _mutated(_set(
            ("prefixes", 1, "turns", 0, "activity", "response", "segments", 0, "text"), text
        ))

    with pytest.raises(PublicationRefused) as refused:
        plan_publication(with_reply("x CANARY-8c x"), credential_values=frozenset({"CANARY-8c"}))
    assert refused.value.reason == "report_contains_credential"
    # Seven characters is below the floor: ordinary words must not trip it.
    assert plan_publication(with_reply("x ABCDEFG x"), credential_values=frozenset({"ABCDEFG"}))
    # A credential only in an EXCLUDED field is never read, so never matched.
    assert plan_publication(_bytes(synthetic_report()), credential_values=frozenset({SECRET_CANARY}))


# --- shared rules -----------------------------------------------------------------


@pytest.mark.parametrize("conversation", (FINAL_A, ZERO_LOW, UUID(int=0), UUID(int=(1 << 128) - 1)))
def test_the_traceparent_equals_the_api_boundary_derivation(conversation) -> None:
    # Written out independently: both sides now share one function, so
    # comparing them alone would pass for any derivation.
    parent = (conversation.int & ((1 << 64) - 1)) or 1
    expected = f"00-{conversation.hex}-{parent:016x}-01"
    assert conversation_traceparent_header(conversation) == expected
    assert conversation_traceparent(
        f"/api/v1/conversations/{conversation}/messages"
    ) == expected.encode("ascii")


def _reason_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value.startswith(("report_", "logfire_", "configuration_"))
        and node.value.replace("_", "").isalpha() and node.value.islower()
    }


def test_publish_reasons_is_exactly_the_reasons_the_code_can_emit() -> None:
    from evals.live_conversations.logfire_publish import PUBLISH_REASONS

    emitted = _reason_literals(BACKEND_ROOT / "evals/live_conversations/publication.py") | (
        _reason_literals(BACKEND_ROOT / "evals/live_conversations/logfire_publish.py")
    )
    emitted -= {"report_run_id", "report_sha256", "configuration_digest"}
    assert emitted == PUBLISH_REASONS


def test_the_subprocess_env_always_sets_both_logfire_variables() -> None:
    env = publisher_env(TOKEN_CANARY, "http://127.0.0.1:9")
    assert env["LOGFIRE_TOKEN"] == TOKEN_CANARY
    assert env["LOGFIRE_BASE_URL"] == "http://127.0.0.1:9"
    assert publisher_env("", "http://127.0.0.1:9")["LOGFIRE_TOKEN"] == ""
    assert all(env[name] == "" for name in CREDENTIAL_ENV_VARS if name != "LOGFIRE_TOKEN")


def test_neither_logfire_pytest_plugin_is_registered(pytestconfig) -> None:
    manager = pytestconfig.pluginmanager
    assert manager.get_plugin("logfire") is None
    assert manager.get_plugin("pytest_logfire") is None
    names = {
        getattr(plugin, "__name__", "") for plugin in manager.get_plugins()
    }
    assert not any(name.startswith("logfire") for name in names), names


# --- drift check on OBSERVED raw keys (Task 4) -------------------------------------

_RAW_KEYS_SCRIPT = """
import json, sys
from collections import defaultdict
import logfire
from opentelemetry.sdk.trace import SpanProcessor
from evals.live_conversations import logfire_publish

observed = defaultdict(set)

class Raw(SpanProcessor):
    def on_end(self, span):
        scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
        observed[scope].update((span.attributes or {}).keys())

real = logfire.configure
def configure(**kwargs):
    kwargs["additional_span_processors"] = [*kwargs["additional_span_processors"], Raw()]
    return real(**kwargs)
logfire.configure = configure
code = logfire_publish.main([sys.argv[1]])
print(json.dumps({scope: sorted(keys) for scope, keys in observed.items()}))
sys.exit(code)
"""


def test_every_raw_key_the_publisher_emits_is_classified(tmp_path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_bytes(_bytes(synthetic_report()))
    with fixture_server("ok") as url:
        completed = subprocess.run(
            [sys.executable, "-c", _RAW_KEYS_SCRIPT, str(report_path)],
            cwd=BACKEND_ROOT, env=publisher_env(TOKEN_CANARY, url),
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
        )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout.strip().splitlines()[-1])
    assert set(observed) == {"pydantic-evals", "shiftmind.live_eval"}
    for scope, keys in observed.items():
        category = span_policy.categorize(scope)
        assert category in (span_policy.EVALS, span_policy.LIVE_EVAL)
        assert span_policy.unclassified_keys(category, keys) == set(), scope
    assert "code.filepath" in observed["pydantic-evals"]  # really observed, then dropped
