"""Publish a finished live-suite run report to Logfire (Story 5.10).

    uv run python -m evals.live_conversations.logfire_publish <report.json>

Input is the RAW run report `suite.py --output` writes, never the evidence
document (it has no conversation IDs). Two things are written:

* one `live_eval.verdict` span per turn of every attempt, inside that
  conversation's trace (trace ID = the conversation UUID, the parent 5.9's
  API boundary synthesizes), at the turn's recorded time;
* one pydantic-evals experiment over the final attempts, named
  `{model} {run_id}` under dataset `live-conversations`. The task returns the
  recorded output and the evaluators return recorded verdicts: nothing is
  re-executed -- no model, API, judge or fixture is called.

The Logfire SDK is ONLY the in-process tracer provider: `send_to_logfire=False`
(its exporter ships the host, OS, git HEAD and absolute paths, and reads back
from Logfire), and every span leaves through 5.9's `SanitizingSpanExporter`
(AD-12). Delivery is proven by the export's recorded results, never by
`force_flush()`, which returns `True` after a 401. The report is read once,
read-only; nothing is ever read back from Logfire.

Exit codes: 0 published; 1 `logfire_export_failed`; 2 any refusal. One JSON
line on stdout says which.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
from opentelemetry import trace
from pydantic_evals import Case, Dataset, increment_eval_metric
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from adapters.telemetry import span_policy
from adapters.telemetry.conversation_trace import conversation_traceparent_header
from adapters.telemetry.spans import build_live_eval_publication_export
from application.app_version import APP_VERSION
from evals.content_minimization_report import CREDENTIAL_ENV_VARS
from evals.live_conversations.publication import (
    DATASET_NAME,
    PLAN_REASONS,
    PublicationPlan,
    PublicationRefused,
    plan_publication,
)
from settings import InvalidFlagError, default_settings

#: The closed vocabulary of reasons this publisher can print.
PUBLISH_REASONS = frozenset(
    PLAN_REASONS | {"configuration_invalid", "logfire_token_absent", "logfire_export_failed"}
)
EXIT_PUBLISHED, EXIT_EXPORT_FAILED, EXIT_REFUSED = 0, 1, 2
SERVICE_NAME = "shiftmind-live-eval-publisher"
VERDICT_SPAN_NAME = "live_eval.verdict"
#: The judge's key is not in 5.2's list: the stack never receives it.
JUDGE_CREDENTIAL_ENV_VAR = "LIVE_CONVERSATION_JUDGE_API_KEY"


# --- the experiment: recorded, never re-executed (Decision 7) ---------------


@dataclass
class RecordedVerdict(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return ctx.output["verdict"] == "pass"


@dataclass
class RecordedJudgeScores(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> dict[str, EvaluationReason]:
        return {
            dimension: EvaluationReason(value=entry["score"], reason=entry["reason"])
            for dimension, entry in ctx.output["judge_scores"].items()
            if entry["score"] is not None
        }


@dataclass
class RecordedOutcome(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> dict[str, str]:
        labels = {"verdict": ctx.output["verdict"]}
        if ctx.output["agent_run_status"] is not None:
            labels["agent_run_status"] = ctx.output["agent_run_status"]
        return labels


def _run_experiment(plan: PublicationPlan) -> None:
    recorded = {case.name: case for case in plan.cases}

    # Named for the case span's `task_name`, which is the function's name.
    async def recorded_live_turn(inputs: dict[str, Any]) -> dict[str, Any]:
        case = recorded[f"{inputs['scenario']}:{inputs['turn']}:rep{inputs['repetition']}"]
        for name, amount in (case.usage or {}).items():
            increment_eval_metric(name, amount)
        return case.output

    dataset = Dataset(
        name=DATASET_NAME,
        cases=[
            Case(name=case.name, inputs=case.inputs, metadata=case.metadata, expected_output=None)
            for case in plan.cases
        ],
        evaluators=[RecordedVerdict(), RecordedJudgeScores(), RecordedOutcome()],
    )
    dataset.evaluate_sync(
        recorded_live_turn,
        name=plan.experiment_name,
        task_name="recorded_live_turn",
        metadata=plan.experiment_metadata,
        progress=False,
    )


# --- verdict spans (Decision 5) ---------------------------------------------


def _write_verdict_spans(plan: PublicationPlan) -> None:
    # After `logfire.configure`, the global provider is Logfire's. The
    # OpenTelemetry API is used because only `start_span` takes a start time.
    tracer = trace.get_tracer(span_policy.LIVE_EVAL_SCOPE)
    for verdict in plan.verdict_spans:
        carrier = {"traceparent": conversation_traceparent_header(verdict.conversation_id)}
        with logfire.propagate.attach_context(carrier):
            tracer.start_span(
                VERDICT_SPAN_NAME,
                kind=trace.SpanKind.INTERNAL,
                attributes=verdict.attributes,
                start_time=verdict.time_unix_nano,
            ).end(end_time=verdict.time_unix_nano)


# --- the command ------------------------------------------------------------


def _emit(outcome: str, reason: str | None, plan: PublicationPlan | None = None,
          spans_exported: int | None = None) -> None:
    assert reason is None or reason in PUBLISH_REASONS, reason
    print(json.dumps({
        "outcome": outcome,
        "reason": reason,
        "report_run_id": plan.report_run_id if plan else None,
        "report_sha256": plan.report_sha256 if plan else None,
        "experiment": plan.experiment_name if plan else None,
        "verdict_spans": len(plan.verdict_spans) if plan else None,
        "cases": len(plan.cases) if plan else None,
        "spans_exported": spans_exported,
    }))


def _refuse(reason: str, plan: PublicationPlan | None = None) -> int:
    _emit("refused", reason, plan)
    return EXIT_REFUSED


def _credential_values() -> frozenset[str]:
    names = (*CREDENTIAL_ENV_VARS, JUDGE_CREDENTIAL_ENV_VAR)
    return frozenset(value for name in names if (value := (os.environ.get(name) or "").strip()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="publish_live_eval", description=__doc__.split("\n")[0])
    parser.add_argument("report", type=Path, help="a finished raw live-suite run report")
    args = parser.parse_args(argv)

    try:
        settings = default_settings()
    except InvalidFlagError:
        return _refuse("configuration_invalid")
    if not settings.logfire_token:
        return _refuse("logfire_token_absent")
    try:
        report_bytes = args.report.read_bytes()
    except OSError:
        return _refuse("report_unreadable")
    try:
        plan = plan_publication(report_bytes, credential_values=_credential_values())
    except PublicationRefused as refused:
        return _refuse(refused.reason)

    export = build_live_eval_publication_export(settings)
    assert export is not None  # the token was checked above
    logfire.configure(
        send_to_logfire=False,  # no Logfire exporter, no GET /v1/info read-back
        additional_span_processors=[export.processor],  # 5.9's sanitizer -> OTLP
        service_name=SERVICE_NAME,
        service_version=APP_VERSION,  # not Logfire's git-HEAD default
        console=False,
        metrics=False,
        inspect_arguments=False,
        # Logfire's deny-list rewrote `unauthorized_effect` to "[Scrubbed due
        # to 'auth']" and would mangle synthetic text; the sanitizer's
        # allow-list and the planner's field list are the control.
        scrubbing=False,
        distributed_tracing=True,  # the one deliberate extraction: the verdict parent
        add_baggage_to_attributes=False,
    )
    try:
        _write_verdict_spans(plan)
        _run_experiment(plan)
    finally:
        delivery = export.finish()
    if not delivery.delivered:
        _emit("failed", "logfire_export_failed", plan, delivery.accepted)
        return EXIT_EXPORT_FAILED
    _emit("published", None, plan, delivery.accepted)
    return EXIT_PUBLISHED


if __name__ == "__main__":
    sys.exit(main())
