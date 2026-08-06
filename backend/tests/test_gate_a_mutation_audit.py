"""Structural mutation-denial proof for the governed Gate A read surface."""
from __future__ import annotations

import ast
from pathlib import Path

from api.main import app


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_READ_ADAPTERS = (
    BACKEND_ROOT / "adapters" / "postgres" / "scenario_projection.py",
    BACKEND_ROOT / "adapters" / "postgres" / "scenario_catalogue.py",
)
MUTATING_SQL_VERBS = ("INSERT", "UPDATE", "DELETE")
EVIDENCE_PATH = (
    BACKEND_ROOT.parent
    / "evidence"
    / "story-1.9"
    / "gate-a-viewer-parity-and-mutation-denial.json"
)


def test_gate_a_scenario_openapi_surface_is_get_only() -> None:
    scenario_paths = {
        path: operations
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/scenarios")
    }

    assert scenario_paths
    for path, operations in scenario_paths.items():
        methods = set(operations) - {"parameters"}
        assert methods == {"get"}, f"{path} exposes {sorted(methods)}"


def test_gate_a_postgres_read_adapters_contain_no_mutating_sql_literals() -> None:
    findings: list[str] = []
    for path in SCENARIO_READ_ADAPTERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            upper = node.value.upper()
            for verb in MUTATING_SQL_VERBS:
                if verb in upper:
                    findings.append(f"{path.name}:{node.lineno} contains {verb}")

    assert findings == []


def test_gate_a_viewer_parity_evidence_separates_mechanism_from_live_state() -> None:
    import json

    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))

    assert evidence["fixtures"] == [
        {
            "fixture_id": "sample_tiny_input",
            "version": "v1",
            "contract": "data/contract/sample_tiny_input.projection-v1.json",
        },
        {
            "fixture_id": "sample_tiny_input_more_tm",
            "version": "v1",
            "contract": "data/contract/sample_tiny_input_more_tm.projection-v1.json",
        },
    ]
    assert evidence["results"]["api_parity"] == "passed"
    assert evidence["results"]["frontend_parity"] == "passed"
    assert evidence["results"]["backend_mutation_audit"] == "passed"
    assert evidence["results"]["frontend_mutation_audit"] == "passed"
    assert evidence["results"]["legacy_route_mechanism"] == "proven (isolated settings)"
    assert evidence["results"]["legacy_route_live_flag_state"] == (
        "not verified by this story — operational fact, owned by Story 1.11 / release runbook"
    )
