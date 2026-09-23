"""Why an invalid-output run failed reaches `agent.run.completed` as labels.

Story 5.7 B5 failed with `invalid_output` and no cause in its telemetry; the
live evaluation reads exactly these labels to diagnose a failed turn.
"""
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID

from api.routers.conversations import _emit_agent_run_completed
from application.contracts.agent_runtime import AgentRunOutcomeV1
from application.contracts.telemetry import TELEMETRY_LABEL_KEYS


class Sink:
    def __init__(self):
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _labels(outcome):
    sink = Sink()
    deps = SimpleNamespace(request_id=UUID(int=1), site_id=UUID(int=2), actor_id=UUID(int=3),
                           conversation_id=UUID(int=4), agent_run_id=UUID(int=5))
    settings = SimpleNamespace(agent_runtime_model="test")
    _emit_agent_run_completed(telemetry=sink, settings=settings, deps=deps, outcome=outcome,
                              agent_run_status="agent_failed", run_started=perf_counter())
    (record,) = sink.records
    assert set(record.labels) <= TELEMETRY_LABEL_KEYS
    return record.labels


def test_a_framework_cause_and_a_named_rule_are_both_labelled():
    labels = _labels(AgentRunOutcomeV1(
        status="failed", failure_reason="invalid_output", failure_source="agent",
        retry_rule="numeric_prose", retry_cause="ToolRetryError"))
    assert labels["retry_rule"] == "numeric_prose"
    assert labels["retry_cause"] == "ToolRetryError"


def test_a_failure_with_no_cause_adds_no_empty_labels():
    labels = _labels(AgentRunOutcomeV1(
        status="failed", failure_reason="invalid_output", failure_source="agent"))
    assert "retry_rule" not in labels and "retry_cause" not in labels
