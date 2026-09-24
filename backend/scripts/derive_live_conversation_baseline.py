"""Derive `backend/evals/baselines/live-conversations.json` (Story 5.8 AC1).

The baseline is a PROJECTION of one measurement -- the committed Story 5.7
evidence -- not a second, independent one. It is ordinary tracked config, so it
deliberately lives outside `evidence/`: membership in the NFR27 regime is
decided by `evidence/**/*.json` location alone (`tests/test_evidence_convention
.py::_evidence_files`), and writing it here is what keeps it out. The
tamper-evidence the regime would otherwise supply comes from
`source_evidence_sha256`, which the default pytest suite re-checks on every run.

It is therefore NOT named `generate_<what>_evidence.py` like this directory's
evidence producers: it produces config, and borrowing that name would assert
exactly the membership the placement denies.

Usage::

    cd backend
    uv run --frozen python scripts/derive_live_conversation_baseline.py

Re-run it whenever the Story 5.7 evidence is regenerated; the source digest
covers the WHOLE evidence file, so any regeneration requires re-deriving.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evals.live_conversations.configuration import (  # noqa: E402
    DEFAULT_OVERRIDE_FILE,
    behavioral_digest,
)
from scripts.evidence_binding import REPO_ROOT, dataset_file_digest  # noqa: E402

#: The one measurement this baseline projects.
SOURCE_EVIDENCE = REPO_ROOT / "evidence" / "story-5.7" / "live-conversation-journeys.json"

#: Tracked config, NOT evidence. See the module docstring.
BASELINE_PATH = BACKEND_ROOT / "evals" / "baselines" / "live-conversations.json"

BASELINE_SCHEMA_VERSION = "1"

#: Mirrors `live_conversation_drop_check.REQUIRED_REPETITIONS`. Not imported from
#: there: that module already imports `BASELINE_PATH`/`SOURCE_EVIDENCE` from this
#: one, and importing back would be circular. Kept equal by
#: `test_required_repetitions_matches_the_drop_check`.
REQUIRED_REPETITIONS = 3


def derive_baseline(
    source: Path = SOURCE_EVIDENCE, *, override_file: Path = DEFAULT_OVERRIDE_FILE
) -> dict:
    """Build the baseline document from a committed Story 5.7 evidence file."""
    evidence = json.loads(Path(source).read_text(encoding="utf-8"))
    _ensure_source_is_clean(evidence, source=source)
    configuration = evidence["measured_configuration"]
    turn_pass_rates = {
        turn: {"executed": int(counts["executed"]), "passed": int(counts["passed"])}
        for turn, counts in sorted(evidence["turn_pass_rates"].items())
    }
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "note": (
            "A projection of the committed Story 5.7 measurement, not a second "
            "measurement. Tracked config, deliberately outside evidence/."
        ),
        "source_evidence_path": Path(source)
        .resolve()
        .relative_to(REPO_ROOT)
        .as_posix(),
        # Normalized to LF: under `core.autocrlf` the working tree holds CRLF on
        # Windows while the committed blob holds LF, so a raw-byte digest would
        # pin the platform rather than the file.
        "source_evidence_sha256": dataset_file_digest(source),
        "measured_at_commit": evidence["measured_at_commit"],
        "configuration": {
            "agent_model": configuration["agent"]["model"],
            "judge_model": configuration["judge"]["model"],
            "reasoning_effort": configuration["reasoning_effort"],
            "configuration_digest": configuration["configuration_digest"],
            # The 5.7 evidence predates `behavioral_digest`, so it is computed
            # from the override AS MEASURED -- the blob at `measured_at_commit`,
            # whose digest must equal the recorded `override_sha256`. A committed
            # blob never changes, so this stays derivable after the tracked
            # file moves on (Story 5.9 Decision 13).
            "behavioral_digest": _baseline_behavioral_digest(
                configuration,
                measured_at_commit=evidence["measured_at_commit"],
                override_file=override_file,
            ),
        },
        "clean_scenarios": list(evidence["clean_scenarios"]),
        "complete_repetitions": int(evidence["complete_repetitions"]),
        "turn_pass_rates": turn_pass_rates,
        "total_executed": sum(c["executed"] for c in turn_pass_rates.values()),
        "total_passed": sum(c["passed"] for c in turn_pass_rates.values()),
    }


def _ensure_source_is_clean(evidence: dict, *, source: Path) -> None:
    """Refuse to derive a baseline from evidence that was itself truncated.

    The baseline doc carries only `complete_repetitions` forward (§ `compare`'s
    `truncation_refusal`); it has no `blocking_reasons` or `runs[]` fields of its
    own, so a not-fully-clean source would otherwise pass through silently and
    no downstream check could ever catch it (Story 5.8 review). Raised here,
    at the one place a bad baseline could be created, the same way
    `_baseline_behavioral_digest` already refuses on a digest mismatch.
    """
    blocking = evidence.get("blocking_reasons") or []
    if blocking:
        raise ValueError(
            f"{source} carries blocking_reasons {sorted(blocking)}; a baseline "
            "cannot be derived from a run that was not fully clean"
        )
    repetitions = int(evidence.get("complete_repetitions", 0))
    if repetitions < REQUIRED_REPETITIONS:
        raise ValueError(
            f"{source} recorded complete_repetitions {repetitions} < "
            f"{REQUIRED_REPETITIONS}; a baseline cannot be derived from a "
            "truncated run"
        )
    incomplete = sorted(
        str(run.get("run_id"))
        for run in evidence.get("runs", [])
        if not run.get("complete")
    )
    if incomplete:
        raise ValueError(
            f"{source} has incomplete runs {incomplete}; a baseline cannot be "
            "derived from a run that did not finish"
        )


def _measured_override_text(commit: str, override_file: Path) -> str:
    relative = Path(override_file).resolve().relative_to(REPO_ROOT).as_posix()
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def _baseline_behavioral_digest(
    configuration: dict, *, measured_at_commit: str, override_file: Path
) -> str:
    text = _measured_override_text(measured_at_commit, override_file)
    recorded = configuration["override_sha256"]
    # Same LF normalisation as `configuration._file_digest`.
    measured = hashlib.sha256(
        text.encode("utf-8").replace(b"\r\n", b"\n")
    ).hexdigest()
    if recorded != measured:
        raise ValueError(
            f"the compose override at {measured_at_commit} does not match the "
            f"override_sha256 the measurement recorded ({measured} != {recorded}); "
            "the baseline's behavioral_digest cannot be computed"
        )
    return behavioral_digest(
        model=configuration["agent"]["model"],
        judge_model=configuration["judge"]["model"],
        reasoning_effort=configuration["reasoning_effort"],
        override_text=text,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_EVIDENCE)
    parser.add_argument("--output", type=Path, default=BASELINE_PATH)
    args = parser.parse_args(argv)

    baseline = derive_baseline(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # LF and a trailing newline, so the committed bytes match on every platform.
    args.output.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"wrote {args.output} "
        f"({baseline['total_passed']}/{baseline['total_executed']} turns)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
