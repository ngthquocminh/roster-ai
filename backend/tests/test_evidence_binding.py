"""Shared NFR27 evidence-binding resolution tests.

Guards the module that Story 1.11 introduces to stop evidence files being
hand-typed with stale or unreproducible bindings. The rule it enforces:
a measurement recorded against a dirty tree cannot be reproduced from the
commit it names, which is exactly what AC2 calls "unbound".
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.evidence_binding import (
    DECLARED_BINDING_KEYS,
    NFR27_BINDING_KEYS,
    DirtyTreeError,
    MigrationGraphError,
    contract_digests,
    resolve_alembic_head,
    resolve_bindings,
    working_tree_status,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

# Minimum declared block a caller must supply. The module derives the rest.
_DECLARED = {
    "evaluator": "pytest 9.1.1",
    "model": "not applicable — no model invocation",
    "prompt": "not applicable — no model invocation",
    "tool": "FastAPI TestClient, PostgreSQL 18",
    "policy": "Story 1.11 AC1/AC2",
    "application": "local backend and frontend source tree",
    "solver": "not applicable — no solver run",
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _tree_is_clean() -> bool:
    return working_tree_status(REPO_ROOT)[0] is False


# --------------------------------------------------------------------------
# NFR27 key completeness
# --------------------------------------------------------------------------


def test_nfr27_declares_exactly_the_eleven_named_bindings():
    assert NFR27_BINDING_KEYS == (
        "dataset",
        "evaluator",
        "model",
        "prompt",
        "tool",
        "policy",
        "application",
        "scenario",
        "solver",
        "code",
        "image",
    )


def test_declared_keys_are_the_nfr27_keys_the_module_cannot_derive():
    derived = {"dataset", "scenario", "code", "image"}
    assert set(DECLARED_BINDING_KEYS) | derived == set(NFR27_BINDING_KEYS)
    assert set(DECLARED_BINDING_KEYS) & derived == set()


def test_resolve_bindings_rejects_a_missing_declared_key():
    incomplete = dict(_DECLARED)
    del incomplete["policy"]
    with pytest.raises(ValueError, match="policy"):
        resolve_bindings(incomplete, repo_root=REPO_ROOT, allow_dirty=True)


def test_resolve_bindings_rejects_a_declared_key_the_module_derives():
    """A caller hardcoding `code` is the exact defect being fixed."""
    with pytest.raises(ValueError, match="code"):
        resolve_bindings(
            {**_DECLARED, "code": {"git_commit": "deadbeef"}},
            repo_root=REPO_ROOT,
            allow_dirty=True,
        )


def test_resolve_bindings_emits_every_nfr27_key_plus_schema_version():
    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT, allow_dirty=True)
    for key in NFR27_BINDING_KEYS:
        assert key in bindings, f"NFR27 binding {key} missing"
    assert "schema_version" in bindings


def test_resolve_bindings_passes_extra_caller_keys_through():
    """Story 1.10 carries axe_core_version etc. inside version_bindings."""
    bindings = resolve_bindings(
        {**_DECLARED, "axe_core_version": "4.13.0"},
        repo_root=REPO_ROOT,
        allow_dirty=True,
    )
    assert bindings["axe_core_version"] == "4.13.0"


# --------------------------------------------------------------------------
# The dirty-tree refusal — the mechanical fix for the repo-wide binding defect
# --------------------------------------------------------------------------


def test_working_tree_status_reports_dirty_paths(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    assert working_tree_status(tmp_path) == (False, ())

    (tmp_path / "tracked.txt").write_text("b", encoding="utf-8")
    dirty, paths = working_tree_status(tmp_path)
    assert dirty is True
    assert "tracked.txt" in paths


def test_working_tree_status_counts_untracked_files_as_dirty(tmp_path):
    """An untracked `??` entry is uncommitted state the commit cannot describe."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "stray.txt").write_text("new", encoding="utf-8")
    dirty, paths = working_tree_status(tmp_path)
    assert dirty is True
    assert "stray.txt" in paths


def test_resolve_bindings_refuses_a_dirty_tree_and_names_the_paths(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "tracked.txt").write_text("b", encoding="utf-8")

    with pytest.raises(DirtyTreeError) as excinfo:
        resolve_bindings(_DECLARED, repo_root=tmp_path)
    assert "tracked.txt" in str(excinfo.value)


def test_allow_dirty_escape_hatch_records_its_own_use(tmp_path):
    """An override nobody can see in the output is a hole, not an override."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "tracked.txt").write_text("b", encoding="utf-8")

    bindings = resolve_bindings(
        _DECLARED,
        repo_root=tmp_path,
        allow_dirty=True,
        migrations_dir=REPO_ROOT / "backend" / "migrations" / "versions",
        contract_dir=REPO_ROOT / "data" / "contract",
    )
    assert bindings["binding_override"] == (
        "--allow-dirty; tree was dirty at generation"
    )
    assert bindings["code"]["working_tree_dirty"] is True


def test_clean_tree_emits_no_binding_override(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )
    bindings = resolve_bindings(
        _DECLARED,
        repo_root=tmp_path,
        migrations_dir=REPO_ROOT / "backend" / "migrations" / "versions",
        contract_dir=REPO_ROOT / "data" / "contract",
    )
    assert "binding_override" not in bindings
    assert bindings["code"]["working_tree_dirty"] is False


# --------------------------------------------------------------------------
# Derived bindings — never hardcoded
# --------------------------------------------------------------------------


def test_code_binding_is_derived_live_not_copied():
    """`working_tree_dirty` must be computed, not the stale literal `true`."""
    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT, allow_dirty=True)
    assert bindings["code"]["git_commit"] == _git("rev-parse", "HEAD")
    expected_dirty = working_tree_status(REPO_ROOT)[0]
    assert bindings["code"]["working_tree_dirty"] is expected_dirty


def test_schema_version_walks_the_migration_graph_to_the_single_head():
    head = resolve_alembic_head(REPO_ROOT / "backend" / "migrations" / "versions")
    assert head == "5e2a4c9d1f70"


def test_alembic_head_resolution_needs_no_database():
    """Report generation must not require PostgreSQL running (file-graph walk)."""
    source = (REPO_ROOT / "backend" / "scripts" / "evidence_binding.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("alembic heads", "create_engine", "psycopg", "sqlalchemy"):
        assert forbidden not in source, f"{forbidden} would need a live database"


def test_alembic_head_fails_loudly_on_a_branched_graph(tmp_path):
    (tmp_path / "a.py").write_text(
        'revision: str = "aaa"\ndown_revision = None\n', encoding="utf-8"
    )
    (tmp_path / "b.py").write_text(
        'revision: str = "bbb"\ndown_revision: str = "aaa"\n', encoding="utf-8"
    )
    (tmp_path / "c.py").write_text(
        'revision: str = "ccc"\ndown_revision: str = "aaa"\n', encoding="utf-8"
    )
    with pytest.raises(MigrationGraphError, match="bbb|ccc"):
        resolve_alembic_head(tmp_path)


def test_alembic_head_fails_loudly_on_an_empty_graph(tmp_path):
    with pytest.raises(MigrationGraphError):
        resolve_alembic_head(tmp_path)


def test_dataset_and_scenario_come_from_default_fixtures_not_a_second_copy():
    from scripts.gate_a_cutover import default_fixtures

    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT, allow_dirty=True)
    for spec in default_fixtures():
        assert f"{spec.fixture_id}:{spec.version}" in bindings["scenario"]
    assert "sample_tiny_input" in bindings["dataset"]


def test_contract_digests_match_raw_file_sha256():
    digests = contract_digests(REPO_ROOT / "data" / "contract")
    assert digests["algorithm"] == "sha256"
    for path in sorted((REPO_ROOT / "data" / "contract").glob("*.json")):
        key = path.name.split(".")[0]
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digests[key] == expected


def test_contract_digests_reproduce_the_already_recorded_values():
    """Locks the algorithm against the value Story 1.9 committed."""
    digests = contract_digests(REPO_ROOT / "data" / "contract")
    recorded = json.loads(
        (
            REPO_ROOT
            / "evidence"
            / "story-1.9"
            / "gate-a-viewer-parity-and-mutation-denial.json"
        ).read_text(encoding="utf-8")
    )["contract_digests"]
    assert digests == recorded


def test_image_binding_is_honest_about_the_absent_registry():
    """No ECR, no Dockerfile pipeline — a fabricated digest would be a lie."""
    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT, allow_dirty=True)
    assert bindings["image"] == {
        "api": "local source tree",
        "web": "local source tree",
        "database": "postgres:18",
    }


def test_module_hardcodes_neither_the_alembic_head_nor_a_commit():
    source = (REPO_ROOT / "backend" / "scripts" / "evidence_binding.py").read_text(
        encoding="utf-8"
    )
    assert "5e2a4c9d1f70" not in source
    assert '"working_tree_dirty": true' not in source.lower()


@pytest.mark.skipif(
    not _tree_is_clean(), reason="binding realism check needs a clean tree"
)
def test_bindings_on_a_clean_tree_name_a_reproducible_commit():
    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT)
    assert bindings["code"]["working_tree_dirty"] is False
    subprocess.run(
        ["git", "cat-file", "-e", f"{bindings['code']['git_commit']}^{{commit}}"],
        cwd=REPO_ROOT,
        check=True,
    )
