"""Generate `evidence/story-2.4/nfr35-sse-reconnect-replay.json` (AC3, NFR35).

This is a **new** evidence file, so `regenerate_evidence.py` cannot bootstrap
it — that script rewrites the bindings of files that already exist. It follows
`backend/evals/report.py`'s `write_evaluation_report` instead: resolve every
binding first (which refuses a dirty tree), then write, so a half-built report
can never be mistaken for evidence. Once written, the file is registered in
`regenerate_evidence.py`'s `EVIDENCE_FILES` and `_MEASUREMENT_MARKERS` and is
re-bindable exactly like every other evidence file.

Nothing here is a literal that could have been derived. The environment block
is read from `platform`, the measurements from a captured test run, and the
bindings from the repository — the four Epic 1 files became unreproducible
precisely because those were typed by hand.

Usage — the ordering *is* the convention (`docs/EVIDENCE-CONVENTION.md`)::

    git commit code                       # 1. commit the code
    git status --porcelain                # 2. must print nothing
    cd backend
    uv run --frozen pytest -m postgres -s -q | tee postgres.log   # 3. measure
    uv run --frozen python scripts/generate_sse_replay_evidence.py \
        --measurements postgres.log                               # 4. generate
    git add ../evidence/story-2.4 && git commit                   # 5. separately
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

OUTPUT_RELATIVE = "evidence/story-2.4/nfr35-sse-reconnect-replay.json"

#: AD-26 / NFR35's threshold for reconnect replay. Not tunable from the command
#: line on purpose: a threshold a generator can lower is not a threshold.
THRESHOLD_MS = 5_000
REQUIRED_RUNS = 3

#: Anchored at line end only — `pytest -q` prefixes the line with progress dots,
#: so a start-of-line anchor never matches a real captured run. Mirrored in
#: `regenerate_evidence.py::_MEASUREMENT_MARKERS`.
MEASUREMENT_MARKER = re.compile(
    r"NFR35_SSE_REPLAY_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
)

#: The prose bindings the repository cannot infer. `dataset`, `scenario`, `code`
#: and `image` are derived by `resolve_bindings` and may not appear here.
DECLARED_BINDINGS: dict[str, str] = {
    "evaluator": (
        "pytest, @pytest.mark.postgres "
        "test_nfr35_sse_reconnect_replay_meets_five_second_threshold"
    ),
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": (
        "in-process ASGI driver over the real FastAPI app (both http middleware "
        "layers active), PostgreSQL 18 in Docker Desktop"
    ),
    "policy": (
        "NFR35/AD-26: reconnect replay to current state completes within "
        "5000 ms; a miss blocks implementation acceptance of Story 2.4"
    ),
    "application": "local backend source tree",
    "solver": "not applicable — no solver run",
}


def parse_measurements(log_text: str) -> list[dict[str, Any]]:
    match = MEASUREMENT_MARKER.search(log_text)
    if match is None:
        raise SystemExit(
            "No NFR35_SSE_REPLAY_MEASUREMENTS= marker found in the captured run. "
            "Run `uv run --frozen pytest -m postgres -s -q` with Docker "
            "PostgreSQL up and capture its stdout."
        )
    return json.loads(match.group(1))


def build_document(
    measurements: Sequence[Mapping[str, Any]],
    *,
    bindings: Mapping[str, Any],
    measurement_date: str,
) -> dict[str, Any]:
    durations = [float(item["duration_ms"]) for item in measurements]
    backlog = sorted({int(item["replay_backlog_events"]) for item in measurements})
    code = bindings["code"]
    return {
        "story": "2.4",
        "requirement": "NFR35",
        "measurement_date": measurement_date,
        "fixture": {
            # The largest Gate A fixture at its full committed size, per the
            # normative measurement protocol.
            "name": "sample_tiny_input_more_tm.json",
            "version": "v1",
        },
        "environment": {
            "description": (
                "Equivalent local developer reference environment; in-process "
                "ASGI driver over the real FastAPI app with a local Docker "
                "PostgreSQL connection pool"
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
                "reconnect request receipt to delivery of the last outstanding "
                "persisted event"
            ),
            "clock_boundary_note": (
                "Delivery is observed at the ASGI send boundary — the last "
                "point inside the application process before the socket — so "
                "the figure excludes network transit only. Starlette's "
                "TestClient buffers a streaming body to completion before "
                "returning, so it can observe neither per-frame delivery nor a "
                "stream that stays open, and was deliberately not used."
            ),
            # AC3 names no number for "the largest Gate A replay backlog", so
            # one is fixed and recorded here rather than left implied by the
            # measurement array's length.
            "replay_backlog_events": backlog[0] if len(backlog) == 1 else backlog,
            "replay_backlog_rationale": (
                "the timeline read cap in api/routers/conversations.py — the "
                "largest number of activities the product renders at once"
            ),
            "last_event_id": (
                "absent; the stalest possible cursor, replaying the entire "
                "backlog from sequence 0"
            ),
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
            f"The protocol requires {REQUIRED_RUNS} consecutive runs; the "
            f"captured run reported {len(measurements)}."
        )
    # Resolve first: a dirty tree or a missing binding must abort before the
    # output directory or file exists.
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
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    staging.replace(destination)
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measurements",
        type=Path,
        required=True,
        help="captured stdout of `pytest -m postgres -s` carrying the marker",
    )
    parser.add_argument("--measurement-date", default=None)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="resolve against a dirty tree; the override is written into the file",
    )
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
    # A threshold miss is a valid, honest outcome to record — but it must not
    # be reported as success by the process that records it.
    return 0 if not violations and document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
