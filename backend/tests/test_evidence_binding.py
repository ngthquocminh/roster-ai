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
    resolve_alembic_chain,
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


def _init_repo_with_commit(tmp_path):
    """A git repo with one committed file and a clean tree."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=tmp_path,
        check=True,
    )


def test_own_output_file_is_exempt_so_the_gate_can_run_twice(tmp_path):
    """The generator's own output must not lock it out of its next run.

    `gate_a_readiness.main()` writes `evidence/gate-a-readiness.json`, which
    dirtied the tree and made run 2 of 2 die on DirtyTreeError before doing any
    work. Exempting that one path removes the two-commit dance without weakening
    anything: no source change is uncommitted, so the recorded commit still
    reproduces the measurement.
    """
    _init_repo_with_commit(tmp_path)
    output = tmp_path / "evidence" / "gate-a-readiness.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}", encoding="utf-8")

    bindings = resolve_bindings(
        _DECLARED,
        repo_root=tmp_path,
        ignore_paths=frozenset({str(output)}),
        migrations_dir=REPO_ROOT / "backend" / "migrations" / "versions",
        contract_dir=REPO_ROOT / "data" / "contract",
    )

    assert bindings["code"]["working_tree_dirty"] is False
    assert "binding_override" not in bindings
    # The exemption is recorded, not silent.
    assert "evidence/gate-a-readiness.json" in bindings["binding_scope"]


def test_exempting_the_output_file_still_refuses_an_uncommitted_source_change(
    tmp_path,
):
    """The exemption is scoped to the named path and nothing else.

    Red-then-green: widen the filter in `working_tree_status()` so it drops every
    path instead of only the exempted ones and this test fails — which is the
    proof that the guard still bites. Without it the exemption would be a blanket
    `--allow-dirty` wearing a narrower name.
    """
    _init_repo_with_commit(tmp_path)
    output = tmp_path / "evidence" / "gate-a-readiness.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}", encoding="utf-8")
    # A real source change, uncommitted, beside the exempted output.
    (tmp_path / "tracked.txt").write_text("b", encoding="utf-8")

    # `migrations_dir`/`contract_dir` point at the real repo so that a widened
    # filter fails HERE, on the missing refusal, rather than tripping over an
    # unrelated MigrationGraphError further downstream. The red must name the
    # thing that broke.
    with pytest.raises(DirtyTreeError) as excinfo:
        resolve_bindings(
            _DECLARED,
            repo_root=tmp_path,
            ignore_paths=frozenset({str(output)}),
            migrations_dir=REPO_ROOT / "backend" / "migrations" / "versions",
            contract_dir=REPO_ROOT / "data" / "contract",
        )

    message = str(excinfo.value)
    assert "tracked.txt" in message
    # The exempted path must not be listed as an offender.
    assert "gate-a-readiness.json" not in message


def test_offering_an_exemption_on_a_clean_tree_records_nothing(tmp_path):
    """Offering an exemption and needing one are different things."""
    _init_repo_with_commit(tmp_path)

    bindings = resolve_bindings(
        _DECLARED,
        repo_root=tmp_path,
        ignore_paths=frozenset({str(tmp_path / "evidence" / "gate-a-readiness.json")}),
        migrations_dir=REPO_ROOT / "backend" / "migrations" / "versions",
        contract_dir=REPO_ROOT / "data" / "contract",
    )

    assert bindings["code"]["working_tree_dirty"] is False
    assert "binding_scope" not in bindings


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
    assert head == "a2b3c4d5e6f7"


def test_alembic_head_resolution_needs_no_database(tmp_path, monkeypatch):
    """Report generation must not require PostgreSQL running (file-graph walk).

    Asserted behaviourally rather than by grepping the source. The original
    version checked that the strings `create_engine`/`psycopg`/`sqlalchemy` did
    not appear in `evidence_binding.py` — but the module's own import graph
    reaches them anyway (`resolve_bindings` -> `gate_a_cutover.default_fixtures`
    -> `adapters.postgres.fixture_history`, which imports sqlalchemy at module
    level). So the grep passed while proving nothing, and would have kept
    passing if someone had added a real `create_engine(...).connect()` one
    module away.

    What actually matters is that resolving a head performs no connection, so
    that is what is asserted: any attempt to open a DBAPI connection fails the
    test.
    """
    import sqlalchemy

    def _explode(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError(
            "resolve_alembic_head opened a database connection; it must be a "
            "file-graph walk so the report can be generated with no service up"
        )

    monkeypatch.setattr(sqlalchemy, "create_engine", _explode)

    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "a.py").write_text(
        'revision: str = "aaa"\ndown_revision = None\n', encoding="utf-8"
    )
    (versions / "b.py").write_text(
        'revision: str = "bbb"\ndown_revision: str = "aaa"\n', encoding="utf-8"
    )

    assert resolve_alembic_head(versions) == "bbb"
    assert resolve_alembic_chain(versions) == ("bbb", "aaa")

    # And no `alembic` subprocess either — the other way to need a live tool.
    def _no_subprocess(*args, **kwargs):  # pragma: no cover - only on failure
        raise AssertionError("resolve_alembic_head shelled out to a subprocess")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    assert resolve_alembic_head(versions) == "bbb"


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


# ---------------------------------------------------------------------------
# the regeneration script
# ---------------------------------------------------------------------------


def test_declared_bindings_round_trip_out_of_an_existing_file():
    """The regenerator recovers prose bindings instead of re-declaring them.

    A second hand-written copy of each story's `evaluator`/`policy`/... prose
    would be a second source of truth, which is the defect `default_fixtures()`
    is imported to avoid.
    """
    from scripts.regenerate_evidence import declared_from

    source = REPO_ROOT / "evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    declared = declared_from(document)

    # Everything the caller must supply is recovered ...
    for key in DECLARED_BINDING_KEYS:
        assert key in declared, f"{key} was not recovered from the existing file"
    # ... and nothing the resolver derives is handed back to it, which it rejects.
    for key in ("dataset", "scenario", "code", "image", "schema_version"):
        assert key not in declared
    # Round-trips: the recovered block is accepted as-is.
    resolve_bindings(declared, repo_root=REPO_ROOT, allow_dirty=True)


def test_nfr35_marker_is_parsed_from_a_progress_dotted_line():
    """`pytest -q` prefixes the marker line with its progress dots.

    A regex anchored at line start never matches a real captured run; this is a
    bug the original Task 7 work hit and fixed in a script that was then not
    committed, so the fix is locked down here.
    """
    from scripts.regenerate_evidence import parse_measurements

    log = (
        "........s..NFR35_MEASUREMENTS="
        '[{"run": 1, "endpoint": "/x", "duration_ms": 12.5}]\n'
        "more output\n"
    )
    parsed = parse_measurements(log, "evidence/story-1.4/nfr35-scenario-data-load.json")
    assert parsed == [{"run": 1, "endpoint": "/x", "duration_ms": 12.5}]

    # The 1.5 marker is a distinct string and must not be matched by 1.4's.
    assert parse_measurements(
        log, "evidence/story-1.5/nfr35-evidence-target-resolution.json"
    ) is None


def test_code_binding_can_be_reused_across_a_multi_file_pass():
    """The second file in a pass reuses the first's clean-tree code block.

    Writing the first evidence file dirties the tree, so re-resolving for the
    second would either refuse or record a spurious dirty flag — while the
    commit that was measured has not changed.
    """
    donor = {"git_commit": "a" * 40, "working_tree_dirty": False}
    bindings = resolve_bindings(_DECLARED, repo_root=REPO_ROOT, code_binding=donor)
    assert bindings["code"]["git_commit"] == "a" * 40
    assert "binding_override" not in bindings


def test_a_dirty_code_binding_cannot_be_laundered_by_reuse():
    """Reusing a dirty block would hide the dirt behind an extra indirection."""
    donor = {"git_commit": "a" * 40, "working_tree_dirty": True}
    with pytest.raises(DirtyTreeError):
        resolve_bindings(_DECLARED, repo_root=REPO_ROOT, code_binding=donor)


def test_code_binding_without_a_commit_is_refused():
    with pytest.raises(ValueError, match="git_commit"):
        resolve_bindings(_DECLARED, repo_root=REPO_ROOT, code_binding={})
