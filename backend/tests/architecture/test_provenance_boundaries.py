"""Architecture guards for the read-only, allowlisted provenance surface."""
import ast
from dataclasses import fields
from pathlib import Path

from api import schemas
from application.contracts import decision_provenance


FORBIDDEN = {"tool_args_json", "turn", "payload", "content", "history", "prompt", "completion"}


def test_provenance_output_types_declare_no_sensitive_payload_field() -> None:
    contract_types = [
        value for value in vars(decision_provenance).values()
        if isinstance(value, type) and value.__module__ == decision_provenance.__name__
    ]
    api_types = [
        value for name, value in vars(schemas).items()
        if isinstance(value, type) and name.endswith("ProvenanceOut")
    ]
    for output_type in contract_types:
        assert not FORBIDDEN & {field.name for field in fields(output_type)}
    for output_type in api_types:
        assert not FORBIDDEN & set(output_type.model_fields)


def test_provenance_query_has_no_provider_or_calculator_dependency() -> None:
    source = Path(decision_provenance.__file__).parents[1] / "queries" / "decision_provenance.py"
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not {name for name in imports if name.startswith(("agent", "llm", "sqlalchemy"))}
    assert not {name for name in calls if name.startswith("calculate_")}
