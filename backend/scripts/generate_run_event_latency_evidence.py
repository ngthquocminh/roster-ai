"""Generate Story 3.5's NFR35 first-run-event latency evidence.

The code must be committed and the tree clean before this script is run. See
``docs/EVIDENCE-CONVENTION.md``.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import (  # noqa: E402
    REPO_ROOT,
    audit_evidence_file,
    resolve_bindings,
)

OUTPUT_RELATIVE = "evidence/story-3.5/nfr35-first-run-event.json"
THRESHOLD_MS = 5_000
REQUIRED_RUNS = 3
MEASUREMENT_MARKER = re.compile(
    r"NFR35_RUN_EVENT_LATENCY_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
)
DECLARED_BINDINGS: dict[str, str] = {
    "evaluator": (
        "pytest, @pytest.mark.postgres "
        "test_nfr35_first_run_event_meets_five_second_threshold"
    ),
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": (
        "direct committed enqueue_compute bundle plus in-process ASGI driver "
        "over the real FastAPI app and PostgreSQL 18 in Docker Desktop"
    ),
    "policy": (
        "NFR35/AD-26: the first persisted schedule-run event reaches the "
        "connected client within 5000 ms; every measured run must pass"
    ),
    "application": "local backend source tree",
    "solver": "not applicable — the queued event precedes solver execution",
}


def parse_measurements(log_text: str) -> list[dict[str, Any]]:
    match = MEASUREMENT_MARKER.search(log_text)
    if match is None:
        raise SystemExit(
            "No NFR35_RUN_EVENT_LATENCY_MEASUREMENTS= marker found in the "
            "captured PostgreSQL test run."
        )
    return json.loads(match.group(1))


def build_document(
    measurements: Sequence[Mapping[str, Any]],
    *,
    bindings: Mapping[str, Any],
    measurement_date: str,
) -> dict[str, Any]:
    durations = [float(item["duration_ms"]) for item in measurements]
    code = bindings["code"]
    return {
        "story": "3.5",
        "requirement": "NFR35",
        "measurement_date": measurement_date,
        "fixture": {
            "name": "sample_tiny_input_more_tm.json",
            "version": "v1",
        },
        "environment": {
            "description": (
                "Equivalent local developer reference environment; in-process "
                "ASGI client boundary with a local Docker PostgreSQL pool"
            ),
            "operating_system": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "database": "PostgreSQL 18 in Docker Desktop",
            "network_transit": "none; in-process ASGI application driver",
        },
        "protocol": {
            "process_state": "warm",
            "database_pool_state": "warm",
            "warmup_requests_discarded": 1,
            "consecutive_runs": REQUIRED_RUNS,
            "all_runs_must_pass": True,
            "threshold_ms": THRESHOLD_MS,
            "clock_boundary": (
                "committed enqueue_compute acknowledgement to the ASGI send "
                "carrying the first persisted run_progress frame"
            ),
            "clock_boundary_note": (
                "Story 3.6 has not shipped the HTTP creation command, so the "
                "direct transaction commit is the acknowledgement boundary. "
                "Delivery is observed at ASGI send; network transit is excluded."
            ),
            "first_event": "run.queued.v1",
        },
        "code_versions": {
            "git_commit": code["git_commit"],
            "working_tree_dirty": code["working_tree_dirty"],
            "api_image": "local source tree",
            "database_image": "postgres:18",
        },
        "measurements": [dict(item) for item in measurements],
        "maximum_duration_ms": max(durations),
        "passed": all(duration <= THRESHOLD_MS for duration in durations),
        "version_bindings": dict(bindings),
    }


def generate(
    *,
    log_text: str,
    repo_root: Path = REPO_ROOT,
    measurement_date: str | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    measurements = parse_measurements(log_text)
    if len(measurements) != REQUIRED_RUNS:
        raise SystemExit(
            f"The protocol requires {REQUIRED_RUNS} consecutive runs; got "
            f"{len(measurements)}."
        )
    bindings = resolve_bindings(
        DECLARED_BINDINGS, repo_root=repo_root, allow_dirty=allow_dirty
    )
    document = build_document(
        measurements,
        bindings=bindings,
        measurement_date=measurement_date or date.today().isoformat(),
    )
    destination = repo_root / OUTPUT_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(destination.suffix + ".tmp")
    staging.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    staging.replace(destination)
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--measurement-date", default=None)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    document = generate(
        log_text=args.measurements.read_text(encoding="utf-8", errors="replace"),
        measurement_date=args.measurement_date,
        allow_dirty=args.allow_dirty,
    )
    violations = audit_evidence_file(REPO_ROOT / OUTPUT_RELATIVE, repo_root=REPO_ROOT)
    print(f"{'ok' if not violations else 'UNBOUND':8s} {OUTPUT_RELATIVE}")
    print(f"         - passed: {document['passed']}")
    print(f"         - maximum_duration_ms: {document['maximum_duration_ms']}")
    for violation in violations:
        print(f"         ! {violation}")
    return 0 if not violations and document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
