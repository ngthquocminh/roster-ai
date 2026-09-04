"""Executable boundaries for owned, low-cardinality operational telemetry."""
from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from api.deps import get_telemetry_sink
from api.main import app
from application.contracts.telemetry import (
    TELEMETRY_LABEL_KEYS,
    CorrelationV1,
    TelemetryRecordV1,
)
from tests.test_decide_approval import BaselineWriter, Memberships, pending
from application.use_cases.decide_approval import DecideApprovalCommandV1, decide_approval

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRODUCER_ROOTS = ("api", "agent", "application", "worker")
RUN_SCOPED_EVENTS = {
    "agent.run.completed",
    "agent.model.calls.completed",
    "agent.tool.call.completed",
    "solver.run.completed",
    "job.leased",
    "run.first_event.persisted",
    "approval.decided",
}
RUN_ATTRIBUTION_EXEMPT_EVENTS = {"api.request.completed"}
FORBIDDEN_TEXT_FIELDS = {
    "message", "detail", "summary", "error", "text", "prompt",
    "args", "arguments", "result", "content",
}


def _python_files(*roots: str) -> list[Path]:
    return [
        path
        for root in roots
        for path in (BACKEND_ROOT / root).rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def telemetry_calls(source: str) -> list[tuple[str, set[str], set[str]]]:
    """Return event name, literal label keys, and correlation keyword names."""
    found: list[tuple[str, set[str], set[str]]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "TelemetryRecordV1":
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        event = _literal_string(keywords.get("event", ast.Constant(None)))
        if event is None:
            continue
        label_keys: set[str] = set()
        labels = keywords.get("labels")
        if isinstance(labels, ast.Dict):
            label_keys = {value for key in labels.keys if key is not None if (value := _literal_string(key))}
        correlation_keys: set[str] = set()
        correlation = keywords.get("correlation")
        if isinstance(correlation, ast.Call):
            correlation_keys = {keyword.arg for keyword in correlation.keywords if keyword.arg}
        found.append((event, label_keys, correlation_keys))
    return found


def producer_label_keys(source: str) -> set[str]:
    """Collect literal keys from direct and locally assembled label mappings."""
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        mappings: list[ast.Dict] = []
        if isinstance(node, ast.keyword) and node.arg == "labels" and isinstance(node.value, ast.Dict):
            mappings.append(node.value)
        elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "labels" for target in node.targets) and isinstance(node.value, ast.Dict):
            mappings.append(node.value)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name) and node.value.id == "labels":
            value = _literal_string(node.slice)
            if value:
                keys.add(value)
        for mapping in mappings:
            keys.update(value for key in mapping.keys if key is not None if (value := _literal_string(key)))
    return keys


def raw_route_label_expressions(source: str) -> set[str]:
    offenders: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if key is not None and _literal_string(key) == "route_template":
                expression = ast.unparse(value)
                if "url.path" in expression:
                    offenders.add(expression)
    return offenders


def unguarded_emit_calls(source: str) -> int:
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.protected = 0
            self.unguarded = 0

        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            broad = any(
                handler.type is None
                or (isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"})
                for handler in node.handlers
            )
            self.protected += int(broad)
            for statement in node.body:
                self.visit(statement)
            self.protected -= int(broad)
            for statement in (*node.handlers, *node.orelse, *node.finalbody):
                self.visit(statement)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            if isinstance(node.func, ast.Attribute) and node.func.attr == "emit" and self.protected == 0:
                self.unguarded += 1
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(ast.parse(source))
    return visitor.unguarded


def forbidden_boundary_imports(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        else:
            continue
        found.update(module for module in modules if module == "logging" or module.startswith("adapters.telemetry"))
    return found


# Task 5's own acceptance boundary: "`adapters/telemetry/` imports no
# framework -- no FastAPI, no SQLAlchemy, no PydanticAI, no Logfire, no
# OpenTelemetry." Clean today, but nothing enforced it (code review of
# story-5.1) -- the AD-1 guard above walks `application`/`domain` only.
FORBIDDEN_ADAPTER_ROOT_MODULES = (
    "fastapi", "sqlalchemy", "pydantic_ai", "pydantic_graph", "logfire", "opentelemetry",
)


def forbidden_framework_imports_in_telemetry_adapter(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        else:
            continue
        found.update(module for module in modules if module.split(".")[0] in FORBIDDEN_ADAPTER_ROOT_MODULES)
    return found


def forbidden_telemetry_field_names(record_types: tuple[type, ...]) -> set[str]:
    return {
        field.name
        for record_type in record_types
        for field in fields(record_type)
        if field.name in FORBIDDEN_TEXT_FIELDS
    }


def test_all_literal_producer_labels_are_allow_listed_and_not_identifiers() -> None:
    calls = [
        call
        for path in _python_files(*PRODUCER_ROOTS)
        for call in telemetry_calls(path.read_text(encoding="utf-8"))
    ]
    assert {event for event, _, _ in calls} == RUN_SCOPED_EVENTS | RUN_ATTRIBUTION_EXEMPT_EVENTS
    producer_sources = [
        path.read_text(encoding="utf-8")
        for path in _python_files(*PRODUCER_ROOTS)
        if "TelemetryRecordV1" in path.read_text(encoding="utf-8")
    ]
    literal_keys = {key for source in producer_sources for key in producer_label_keys(source)}
    assert literal_keys <= TELEMETRY_LABEL_KEYS
    assert not {key for key in literal_keys if key.endswith("_id")}


def test_parameterized_request_uses_the_route_template_not_the_uuid() -> None:
    records: list[TelemetryRecordV1] = []

    class Sink:
        def emit(self, record: TelemetryRecordV1) -> None:
            records.append(record)

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_telemetry_sink] = Sink
    conversation_id = uuid4()
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/conversations/{conversation_id}/messages", json={"text": "x"}
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

    assert response.status_code == 401
    record = next(record for record in records if record.event == "api.request.completed")
    assert record.labels["route_template"] == "/api/v1/conversations/{conversation_id}/messages"
    assert str(conversation_id) not in record.labels["route_template"]
    assert raw_route_label_expressions((BACKEND_ROOT / "api/main.py").read_text(encoding="utf-8")) == set()


def test_every_run_scoped_event_declares_run_attribution() -> None:
    calls = [
        call
        for path in _python_files(*PRODUCER_ROOTS)
        for call in telemetry_calls(path.read_text(encoding="utf-8"))
    ]
    for event, _, correlation_keys in calls:
        if event in RUN_ATTRIBUTION_EXEMPT_EVENTS:
            continue
        assert event in RUN_SCOPED_EVENTS
        assert {"agent_run_id", "schedule_run_id"} & correlation_keys, event


def test_application_and_domain_do_not_import_logging_or_telemetry_adapters() -> None:
    violations = {
        str(path.relative_to(BACKEND_ROOT)): forbidden_boundary_imports(path.read_text(encoding="utf-8"))
        for path in _python_files("application", "domain")
        if forbidden_boundary_imports(path.read_text(encoding="utf-8"))
    }
    assert not violations


def test_telemetry_adapter_imports_no_framework() -> None:
    violations = {
        str(path.relative_to(BACKEND_ROOT)): forbidden_framework_imports_in_telemetry_adapter(
            path.read_text(encoding="utf-8")
        )
        for path in _python_files("adapters/telemetry")
        if forbidden_framework_imports_in_telemetry_adapter(path.read_text(encoding="utf-8"))
    }
    assert not violations


def test_telemetry_contract_has_no_free_text_field() -> None:
    assert forbidden_telemetry_field_names((CorrelationV1, TelemetryRecordV1)) == set()


def test_raising_sink_cannot_block_approval_promotion_or_audit() -> None:
    runs, approvals, audit, conversations, command = pending()

    class RaisingSink:
        calls = 0

        def emit(self, _record: TelemetryRecordV1) -> None:
            self.calls += 1
            raise RuntimeError("exporter unavailable")

    sink = RaisingSink()
    result = decide_approval(
        None,
        command=DecideApprovalCommandV1(
            site_id=command.site_id,
            actor_id=command.actor_id,
            approval_id=approvals.binding.approval_id,
            decision="approve",
            expected_resource_version=approvals.binding.resource_version,
            request_id=uuid4(),
        ),
        approvals=approvals,
        schedule_runs=runs,
        baselines=type("NoBaseline", (), {"get": lambda *_args: None})(),
        baseline_writer=BaselineWriter(),
        memberships=Memberships(),
        audit_writer=audit,
        conversations=conversations,
        scheduling_baseline_enabled=True,
        clock=lambda: command and approvals.binding.created_at,
        telemetry=sink,
    )
    assert sink.calls == 1
    assert approvals.binding.state == "consumed"
    assert result.baseline is not None
    assert [item.outcome for item in audit.items] == ["approval_consumed"]


def test_every_producer_guards_emit_failures() -> None:
    violations = {
        str(path.relative_to(BACKEND_ROOT)): unguarded_emit_calls(source)
        for path in _python_files(*PRODUCER_ROOTS)
        if "TelemetryRecordV1" in (source := path.read_text(encoding="utf-8"))
        and unguarded_emit_calls(source)
    }
    assert not violations


def test_each_guard_detects_synthetic_violating_source() -> None:
    bad_call = '''TelemetryRecordV1(
        event="agent.run.completed",
        labels={"agent_run_id": "bad"},
        correlation=CorrelationV1(request_id=value),
    )'''
    [(event, labels, correlation)] = telemetry_calls(bad_call)
    assert event in RUN_SCOPED_EVENTS
    assert labels - TELEMETRY_LABEL_KEYS == {"agent_run_id"}
    assert producer_label_keys(bad_call) == {"agent_run_id"}
    assert {"agent_run_id", "schedule_run_id"}.isdisjoint(correlation)
    assert raw_route_label_expressions('labels={"route_template": request.url.path}') == {
        "request.url.path"
    }
    assert unguarded_emit_calls("telemetry.emit(record)") == 1
    assert forbidden_boundary_imports("import logging\nfrom adapters.telemetry import JsonLogTelemetrySink") == {
        "logging", "adapters.telemetry"
    }
    assert forbidden_framework_imports_in_telemetry_adapter(
        "import fastapi\nfrom sqlalchemy import text\nimport pydantic_ai"
    ) == {"fastapi", "sqlalchemy", "pydantic_ai"}

    from dataclasses import dataclass

    @dataclass
    class BadRecord:
        summary: str | None = None

    assert forbidden_telemetry_field_names((BadRecord,)) == {"summary"}
