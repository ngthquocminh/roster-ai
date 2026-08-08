"""Repo-wide evidence convention guard.

Walks **every** `evidence/**/*.json`, not just this story's. Two deliberate
choices:

* It walks the tree rather than naming files, so a new evidence file in Epic 2
  is covered automatically and cannot reintroduce the binding defect that hit
  all four Epic 1 files.
* It is a repo-wide *convention* sweep, not a replacement for the story-specific
  guards. `test_scenario_projection.py:64-75` (Stories 1.4/1.5) and
  `test_gate_a_mutation_audit.py:16-21` (Story 1.9) assert semantic content
  this sweep deliberately does not; they stay as they are.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.evidence_binding import (
    NFR27_BINDING_KEYS,
    audit_evidence_file,
    contract_digests,
    resolve_alembic_head,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "evidence"


def _git_available() -> bool:
    if shutil.which("git") is None:
        return False
    return (
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=REPO_ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


requires_git = pytest.mark.skipif(
    not _git_available(),
    reason="git is unavailable; commit-binding assertions cannot be evaluated",
)


def _evidence_files() -> list[Path]:
    if not EVIDENCE_ROOT.is_dir():
        return []
    return sorted(EVIDENCE_ROOT.rglob("*.json"))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


EVIDENCE_FILES = _evidence_files()


def test_the_evidence_tree_is_not_empty():
    """A silently empty sweep would pass while proving nothing."""
    assert EVIDENCE_FILES, "no evidence/**/*.json files found to audit"


@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_every_evidence_file_declares_all_eleven_nfr27_bindings(evidence_path):
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    bindings = document.get("version_bindings")
    assert isinstance(bindings, dict), (
        f"{_relative(evidence_path)} has no `version_bindings` block; NFR27 "
        "requires all eleven bindings on every evidence report"
    )
    missing = [key for key in NFR27_BINDING_KEYS if key not in bindings]
    assert not missing, (
        f"{_relative(evidence_path)} is missing NFR27 binding(s): "
        f"{', '.join(missing)}"
    )


@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_every_evidence_file_binds_the_current_schema_version(evidence_path):
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    bindings = document.get("version_bindings") or {}
    head = resolve_alembic_head(REPO_ROOT / "backend" / "migrations" / "versions")
    assert bindings.get("schema_version") == head, (
        f"{_relative(evidence_path)} must bind schema_version to the current "
        f"migration head {head!r}"
    )


@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_no_evidence_file_was_recorded_on_a_dirty_tree(evidence_path):
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    bindings = document.get("version_bindings") or {}
    code = bindings.get("code") or {}
    if code.get("working_tree_dirty"):
        assert bindings.get("binding_override"), (
            f"{_relative(evidence_path)} was recorded on a dirty tree with no "
            "`binding_override` explaining why. The uncommitted diff it refers "
            "to is not recorded anywhere, so the binding is unusable."
        )


@requires_git
@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_every_recorded_commit_is_a_real_ancestor_that_touched_code(evidence_path):
    """Catches Story 1.10's case: a docs-only commit proves nothing."""
    violations = [
        violation
        for violation in audit_evidence_file(evidence_path, repo_root=REPO_ROOT)
        if "git_commit" in violation
    ]
    assert not violations, f"{_relative(evidence_path)}: {'; '.join(violations)}"


@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_every_referenced_path_exists_on_disk(evidence_path):
    violations = [
        violation
        for violation in audit_evidence_file(evidence_path, repo_root=REPO_ROOT)
        if "referenced path" in violation
    ]
    assert not violations, f"{_relative(evidence_path)}: {'; '.join(violations)}"


@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_recorded_contract_digests_match_the_real_files(evidence_path):
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    recorded = document.get("contract_digests")
    if not isinstance(recorded, dict):
        pytest.skip("this evidence file records no contract digests")
    actual = contract_digests(REPO_ROOT / "data" / "contract")
    assert recorded == actual, (
        f"{_relative(evidence_path)} records contract digests that do not "
        "match the files on disk"
    )


@requires_git
@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_evidence_file_is_fully_bound(evidence_path):
    """The whole convention in one assertion, for a readable failure."""
    violations = audit_evidence_file(evidence_path, repo_root=REPO_ROOT)
    assert not violations, (
        f"{_relative(evidence_path)} violates the evidence convention "
        f"(docs/EVIDENCE-CONVENTION.md):\n  - " + "\n  - ".join(violations)
    )
