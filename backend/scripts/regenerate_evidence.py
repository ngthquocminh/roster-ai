"""Regenerate the Story 1.1-1.10 evidence files through the binding resolver.

Story 1.11 Task 7 re-measured and rebound four evidence files, but shipped no
script to do it — the work was done by an ephemeral one, which made the
regeneration itself unreproducible. That is the same defect Task 7 existed to
close, one level up: `docs/EVIDENCE-CONVENTION.md` says *"generate the evidence
file through `resolve_bindings()` — never by hand"*, and nothing in the
repository could.

What this preserves and what it replaces
----------------------------------------
**Preserved verbatim**: every semantic field. The story-specific guards assert
them and must keep passing — `test_scenario_projection.py` checks 1.4/1.5's
`fixture.name`, `protocol`, measurement counts and `passed`;
`test_gate_a_mutation_audit.py` checks all six of 1.9's `results` strings
including `legacy_route_live_flag_state`.

**Replaced**: `version_bindings` (and Schema A's parallel `code_versions`), plus
`measurement_date`. The declared prose bindings are read back out of each file's
existing block rather than re-declared here — a second copy would be a second
source of truth, the same reason `default_fixtures()` is imported and never
restated.

**Optionally replaced**: 1.4/1.5's `measurements` and `maximum_duration_ms`,
when a captured postgres run is supplied with `--measurements`.

Usage::

    git commit code                       # the tree must be clean
    cd backend
    uv run --frozen pytest -m postgres -s -q | tee /tmp/postgres.log
    uv run --frozen python scripts/regenerate_evidence.py \
        --measurements /tmp/postgres.log

Every binding set is resolved *before* the first file is written, because
writing one dirties the tree and `resolve_bindings()` refuses a dirty tree.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import (  # noqa: E402
    DERIVED_BINDING_KEYS,
    REPO_ROOT,
    audit_evidence_file,
    resolve_bindings,
)

#: Keys `resolve_bindings()` derives itself and rejects from a caller, plus the
#: two it writes on its own account.
_NOT_DECLARED = set(DERIVED_BINDING_KEYS) | {"schema_version", "binding_override"}

EVIDENCE_FILES: tuple[str, ...] = (
    "evidence/story-1.4/nfr35-scenario-data-load.json",
    "evidence/story-1.5/nfr35-evidence-target-resolution.json",
    "evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json",
    "evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json",
)

#: Anchored at line end only. `pytest -q` prefixes the line with its progress
#: dots, so a start-of-line anchor never matches in a real captured run.
_MEASUREMENT_MARKERS = {
    "evidence/story-1.4/nfr35-scenario-data-load.json": re.compile(
        r"NFR35_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
    ),
    "evidence/story-1.5/nfr35-evidence-target-resolution.json": re.compile(
        r"NFR35_EVIDENCE_MEASUREMENTS=(\[.*\])\s*$", re.MULTILINE
    ),
}

_STORY_FILES = {
    "evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json": (
        "_bmad-output/implementation-artifacts/"
        "1-10-prove-scenario-data-accessibility-and-responsiveness.md"
    ),
}

_BASELINE_RE = re.compile(r"^baseline_commit:\s*(\S+)\s*$", re.MULTILINE)


def declared_from(document: dict[str, Any]) -> dict[str, Any]:
    """Recover the prose bindings a file already carries."""
    existing = document.get("version_bindings") or {}
    return {k: v for k, v in existing.items() if k not in _NOT_DECLARED}


def baseline_commit_for(relative: str, repo_root: Path) -> str | None:
    """Read a story's `baseline_commit` from its own frontmatter.

    Story 1.10 carried this inside `version_bindings.code` and lost it in the
    Task 7 rebind, leaving its prose ("47 files passed ... at f27bafd") as the
    only surviving trace — a 7-character abbreviation inside a sentence, which
    no audit can resolve. Read from the story file so it is derived rather than
    restored as a literal here.
    """
    story_file = _STORY_FILES.get(relative)
    if not story_file:
        return None
    path = repo_root / story_file
    if not path.is_file():
        return None
    match = _BASELINE_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def parse_measurements(log_text: str, relative: str) -> list[Any] | None:
    """Pull one story's NFR35 measurements out of a captured pytest run."""
    marker = _MEASUREMENT_MARKERS.get(relative)
    if marker is None:
        return None
    match = marker.search(log_text)
    if match is None:
        return None
    return json.loads(match.group(1))


def regenerate(
    *,
    repo_root: Path = REPO_ROOT,
    measurements_log: str | None = None,
    measurement_date: str | None = None,
    allow_dirty: bool = False,
) -> dict[str, list[str]]:
    """Rewrite every evidence file's bindings in place. Returns per-file notes."""
    stamp = measurement_date or date.today().isoformat()

    # Resolve every binding set FIRST. Writing the first file makes the tree
    # dirty, and `resolve_bindings()` refuses a dirty tree — correctly, since a
    # measurement taken beside uncommitted changes is not reproducible.
    documents: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    for relative in EVIDENCE_FILES:
        path = repo_root / relative
        document = json.loads(path.read_text(encoding="utf-8"))
        documents[relative] = document
        baseline = baseline_commit_for(relative, repo_root)
        bindings[relative] = resolve_bindings(
            declared_from(document),
            repo_root=repo_root,
            code_extra={"baseline_commit": baseline} if baseline else None,
            allow_dirty=allow_dirty,
        )

    notes: dict[str, list[str]] = {}
    for relative in EVIDENCE_FILES:
        path = repo_root / relative
        document = documents[relative]
        entry: list[str] = []

        document["measurement_date"] = stamp
        document["version_bindings"] = bindings[relative]

        # Schema A (1.4, 1.5) carries a parallel `code_versions` block that
        # predates `version_bindings`. Keep its shape — the story-specific
        # guards read it — but stop it drifting into a second, stale truth.
        code_versions = document.get("code_versions")
        if isinstance(code_versions, dict):
            code = bindings[relative]["code"]
            for key in ("git_commit", "working_tree_dirty"):
                if key in code_versions:
                    code_versions[key] = code[key]
            entry.append("code_versions realigned with version_bindings.code")

        if measurements_log:
            fresh = parse_measurements(measurements_log, relative)
            if fresh:
                document["measurements"] = fresh
                durations = [
                    m["duration_ms"] for m in fresh if isinstance(m, dict)
                    and "duration_ms" in m
                ]
                if durations:
                    document["maximum_duration_ms"] = max(durations)
                entry.append(f"{len(fresh)} measurements re-read from the run")

        staging = path.with_suffix(path.suffix + ".tmp")
        staging.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        staging.replace(path)
        notes[relative] = entry

    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate Story 1.4/1.5/1.9/1.10 evidence bindings"
    )
    parser.add_argument(
        "--measurements",
        type=Path,
        help=(
            "captured stdout of `pytest -m postgres -s`, used to refresh "
            "1.4/1.5's NFR35 measurements; bindings alone are rewritten without it"
        ),
    )
    parser.add_argument("--measurement-date", default=None)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="resolve against a dirty tree; the override is written into each file",
    )
    args = parser.parse_args(argv)

    log_text = (
        args.measurements.read_text(encoding="utf-8", errors="replace")
        if args.measurements
        else None
    )
    if args.measurements and not log_text:
        print(f"warning: {args.measurements} is empty", file=sys.stderr)

    notes = regenerate(
        measurements_log=log_text,
        measurement_date=args.measurement_date,
        allow_dirty=args.allow_dirty,
    )

    failures = 0
    for relative, entry in notes.items():
        violations = audit_evidence_file(REPO_ROOT / relative, repo_root=REPO_ROOT)
        status = "ok" if not violations else "UNBOUND"
        print(f"{status:8s} {relative}")
        for line in entry:
            print(f"         - {line}")
        for violation in violations:
            print(f"         ! {violation}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
