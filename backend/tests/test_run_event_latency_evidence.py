from __future__ import annotations

import pytest

from scripts.generate_run_event_latency_evidence import (
    REQUIRED_RUNS,
    THRESHOLD_MS,
    build_document,
    parse_measurements,
)


def test_run_event_generator_parses_the_exact_measurement_marker() -> None:
    measurements = parse_measurements(
        '...NFR35_RUN_EVENT_LATENCY_MEASUREMENTS=[{"run":1,"duration_ms":12.5}]\n'
    )
    assert measurements == [{"run": 1, "duration_ms": 12.5}]


def test_run_event_evidence_requires_three_runs_and_blocks_a_miss() -> None:
    assert REQUIRED_RUNS == 3
    assert THRESHOLD_MS == 5_000
    document = build_document(
        [
            {"run": 1, "duration_ms": 10.0},
            {"run": 2, "duration_ms": 20.0},
            {"run": 3, "duration_ms": 5_001.0},
        ],
        bindings={"code": {"git_commit": "a" * 40, "working_tree_dirty": False}},
        measurement_date="2026-08-21",
    )
    assert document["passed"] is False
    assert document["maximum_duration_ms"] == 5_001.0
