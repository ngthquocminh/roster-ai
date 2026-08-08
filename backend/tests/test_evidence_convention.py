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
    audit_evidence_drift,
    audit_evidence_file,
    contract_digests,
    resolve_alembic_chain,
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
def test_every_evidence_file_binds_a_schema_version_on_the_current_chain(
    evidence_path,
):
    """Monotone by construction — see `audit_evidence_file`'s contract.

    This deliberately does *not* require equality with the current head. A
    revision that was the head when a measurement was taken stays on the chain
    forever, so historical evidence keeps passing; requiring equality would
    turn every new Alembic revision into a repo-wide red suite whose cheapest
    remedy is hand-editing the very field this module exists to protect.
    """
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    bindings = document.get("version_bindings") or {}
    chain = resolve_alembic_chain(REPO_ROOT / "backend" / "migrations" / "versions")
    recorded = bindings.get("schema_version")
    assert recorded in chain, (
        f"{_relative(evidence_path)} binds schema_version {recorded!r}, which "
        f"is not on the migration chain leading to the current head {chain[0]!r}"
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


@requires_git
@pytest.mark.parametrize(
    "evidence_path", EVIDENCE_FILES, ids=[_relative(p) for p in EVIDENCE_FILES]
)
def test_every_referenced_path_exists_on_disk(evidence_path):
    """A referenced path going missing is drift, not a binding failure.

    Still asserted — a dangling reference is worth knowing about — but it is
    read from `audit_evidence_drift`, so it cannot unbind the evidence or block
    the gate. `@requires_git` because the audit shells out to git.
    """
    drift = [
        entry
        for entry in audit_evidence_drift(evidence_path, repo_root=REPO_ROOT)
        if "referenced path" in entry
    ]
    assert not drift, f"{_relative(evidence_path)}: {'; '.join(drift)}"


def _records_contract_digests(path: Path) -> bool:
    document = json.loads(path.read_text(encoding="utf-8"))
    return isinstance(document.get("contract_digests"), dict)


#: Schema A (stories 1.4/1.5) carries no `contract_digests` block by design, so
#: those files are filtered out rather than skipped inside the test. The
#: distinction matters: the Gate A report treats a skipped case as *not proven*
#: and blocks on it, and "this field does not apply to this file" is not the
#: same thing as "this check did not run". Parametrizing only over the files
#: the check applies to says exactly what is meant and leaves no skip to
#: misread.
EVIDENCE_FILES_WITH_DIGESTS = [p for p in EVIDENCE_FILES if _records_contract_digests(p)]


@pytest.mark.parametrize(
    "evidence_path",
    EVIDENCE_FILES_WITH_DIGESTS,
    ids=[_relative(p) for p in EVIDENCE_FILES_WITH_DIGESTS],
)
def test_recorded_contract_digests_match_the_real_files(evidence_path):
    document = json.loads(evidence_path.read_text(encoding="utf-8"))
    recorded = document["contract_digests"]
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


# ---------------------------------------------------------------------------
# the rule's own lifecycle
# ---------------------------------------------------------------------------


@requires_git
def test_evidence_survives_a_future_migration(tmp_path, monkeypatch):
    """Adding a migration must not retroactively unbind existing evidence.

    This is the test the story needed and did not have. Story 1.11 originally
    specified `schema_version present and equal to the current Alembic head`
    (Task 5) and implemented exactly that — so the next Alembic revision would
    have turned all five evidence files red at once, dropped four registry
    checks to unbound, and blocked Gate A for a reason with nothing to do with
    Gate A. The only cheap way out would have been hand-editing the field,
    which is the practice the whole module exists to stop.

    It asserts a property of the *rule*, not of the data: every rule applied to
    a committed artifact must be monotone — once satisfied, satisfied forever,
    unless the artifact itself changes.
    """
    versions = REPO_ROOT / "backend" / "migrations" / "versions"
    chain_before = resolve_alembic_chain(versions)

    # A synthetic successor to today's head, in a scratch copy of the versions
    # directory — the real one is never touched.
    scratch = tmp_path / "versions"
    scratch.mkdir()
    for source in versions.glob("*.py"):
        (scratch / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    (scratch / "zz_future_revision.py").write_text(
        f'revision: str = "future0000ff"\n'
        f'down_revision: str = "{chain_before[0]}"\n',
        encoding="utf-8",
    )

    chain_after = resolve_alembic_chain(scratch)
    assert chain_after[0] == "future0000ff", "the synthetic revision is the new head"

    # Every revision the existing evidence files bind must still be on it.
    for evidence_path in EVIDENCE_FILES:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
        recorded = (document.get("version_bindings") or {}).get("schema_version")
        assert recorded in chain_after, (
            f"{_relative(evidence_path)} binds schema_version {recorded!r}, "
            "which fell off the chain the moment a migration was added. The "
            "rule is not monotone and will force evidence to be hand-edited."
        )


def test_contract_drift_is_reported_but_does_not_unbind(tmp_path):
    """An edited contract artifact is drift, never a binding violation.

    The same monotonicity argument: `contract_digests` recomputes from disk, so
    treating a mismatch as a violation would unbind historical evidence every
    time a contract fixture is regenerated.
    """
    source = EVIDENCE_FILES[0]
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document.get("contract_digests"), dict):
        pytest.skip("this evidence file records no contract digests")

    forged = dict(document)
    digests = dict(document["contract_digests"])
    target = next(k for k in digests if k != "algorithm")
    digests[target] = "0" * 64
    forged["contract_digests"] = digests

    scratch = tmp_path / "forged.json"
    scratch.write_text(json.dumps(forged, indent=2), encoding="utf-8")

    drift = audit_evidence_drift(scratch, repo_root=REPO_ROOT)
    assert any(target in entry for entry in drift), "drift must be reported"

    violations = audit_evidence_file(scratch, repo_root=REPO_ROOT)
    assert not any("contract" in v for v in violations), (
        "a changed contract artifact must not unbind the evidence"
    )
