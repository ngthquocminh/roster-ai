"""Shared NFR27 version-binding resolution for evidence reports.

Deliberately generic, not Gate-A-specific. `epics.md:1612-1623` already names
`evidence/story-5.10/rollback-drill-report.json` and
`evidence/epic-5/release-gate-report.json` as future consumers, so anything
that knows about Gate A belongs in the caller, not here.

The rule this module mechanises
------------------------------
An evidence file's `git_commit` must name *the tree that was measured*. That
holds only when the working tree is clean at generation time::

    loop: write/fix code -> run tests freely   # dirty tree fine, this is dev
    git commit code                            # tree becomes clean
    run the measurement                        # THIS run gets recorded
    generate evidence (this module)            # HEAD names exactly that tree
    git commit evidence                        # separate commit

Every binding below is *derived live*. None is a literal. The repo's four
pre-existing evidence files each hand-typed a dirty-tree flag of `true` beside
the parent commit hash, which is what made all four unreproducible.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

#: The eleven bindings NFR27 requires on every evidence report, in the order
#: the requirement lists them. A binding that does not apply keeps its key and
#: states the reason; it is never omitted.
NFR27_BINDING_KEYS: tuple[str, ...] = (
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

#: Derived here from the repository itself. A caller supplying one of these is
#: reintroducing exactly the hand-typed-literal defect this module exists to
#: remove, so it is rejected rather than silently overridden.
DERIVED_BINDING_KEYS: tuple[str, ...] = ("dataset", "scenario", "code", "image")

#: Prose the repository cannot infer; the caller must supply all of them.
DECLARED_BINDING_KEYS: tuple[str, ...] = tuple(
    key for key in NFR27_BINDING_KEYS if key not in DERIVED_BINDING_KEYS
)

_ALLOW_DIRTY_NOTE = "--allow-dirty; tree was dirty at generation"

# There is no container registry, no image build pipeline and no `.github/` in
# this repository. AD-17/AD-24's immutable-digest requirement is Epic 5 work
# (Stories 5.5-5.7). Fabricating a digest here would be a false binding, so the
# honest value is the one Stories 1.4/1.5/1.9/1.10 already recorded.
_LOCAL_IMAGE_BINDING: dict[str, str] = {
    "api": "local source tree",
    "web": "local source tree",
    "database": "postgres:18",
}


class DirtyTreeError(RuntimeError):
    """Raised when bindings are requested against uncommitted changes."""


class MigrationGraphError(RuntimeError):
    """Raised when the migration files do not resolve to exactly one head."""


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    return _git_raw(repo_root, *args).strip()


def _git_ok(repo_root: Path, *args: str) -> bool:
    """Run git for its exit status only (0 -> True)."""
    return (
        subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _git_raw(repo_root: Path, *args: str) -> str:
    """Unstripped stdout.

    `git status --porcelain` encodes the status in the first two columns, so
    the leading space of an unstaged change (` M path`) is significant. A blunt
    `.strip()` on the whole output eats it and shifts every parsed path by one
    character.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def working_tree_status(repo_root: Path = REPO_ROOT) -> tuple[bool, tuple[str, ...]]:
    """Return ``(dirty, offending_paths)`` for ``repo_root``.

    Untracked (``??``) entries count as dirty: an untracked file is state the
    recorded commit cannot describe, so a measurement taken beside one is no
    more reproducible than one taken on a modified tracked file.
    """
    porcelain = _git_raw(repo_root, "status", "--porcelain")
    if not porcelain.strip():
        return False, ()
    paths: list[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        # Porcelain v1: two status columns, then the path. Renames render as
        # `old -> new`; both halves are reported.
        entry = line[2:].strip().strip('"')
        for part in entry.split(" -> "):
            part = part.strip().strip('"')
            if part:
                paths.append(part)
    return True, tuple(paths)


def resolve_code_binding(
    repo_root: Path = REPO_ROOT,
    *,
    allow_dirty: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Return the ``code`` binding plus whether the dirty escape hatch was used."""
    dirty, paths = working_tree_status(repo_root)
    if dirty and not allow_dirty:
        listed = "\n  ".join(paths)
        raise DirtyTreeError(
            "Refusing to resolve version bindings against a dirty working tree.\n"
            "A measurement taken on uncommitted changes cannot be reproduced "
            "from the commit it records, which is what NFR27/AC2 calls "
            "'unbound'. Commit the code first, then re-run the measurement.\n"
            f"Offending paths:\n  {listed}\n"
            "Override with allow_dirty=True / --allow-dirty; the override is "
            "written into the report."
        )
    return (
        {
            "git_commit": _git(repo_root, "rev-parse", "HEAD"),
            # Computed live on every generation. Never a literal.
            "working_tree_dirty": dirty,
        },
        dirty,
    )


# ---------------------------------------------------------------------------
# schema version
# ---------------------------------------------------------------------------

_REVISION_RE = re.compile(r"^revision(?:\s*:[^=]*)?\s*=\s*(.+?)\s*$", re.MULTILINE)
_DOWN_REVISION_RE = re.compile(
    r"^down_revision(?:\s*:[^=]*)?\s*=\s*(.+?)\s*$", re.MULTILINE
)


def _literal(raw: str) -> Any:
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def resolve_alembic_head(versions_dir: Path) -> str:
    """Walk ``down_revision`` across the migration files to the single head.

    A file-graph walk on purpose: report generation must stay runnable with no
    PostgreSQL service up, so this never queries a live schema and never shells
    out to the migration tool.
    """
    revisions: dict[str, Any] = {}
    for path in sorted(versions_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        revision_match = _REVISION_RE.search(source)
        if revision_match is None:
            continue
        revision = _literal(revision_match.group(1))
        if not isinstance(revision, str):
            continue
        down_match = _DOWN_REVISION_RE.search(source)
        revisions[revision] = _literal(down_match.group(1)) if down_match else None

    if not revisions:
        raise MigrationGraphError(
            f"No migration revisions found under {versions_dir}. "
            "schema_version cannot be bound."
        )

    referenced: set[str] = set()
    for down in revisions.values():
        if isinstance(down, str):
            referenced.add(down)
        elif isinstance(down, (list, tuple)):
            referenced.update(item for item in down if isinstance(item, str))

    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise MigrationGraphError(
            f"Expected exactly one migration head under {versions_dir}, "
            f"found {len(heads)}: {', '.join(heads) or '(none)'}. "
            "A branched or empty graph cannot bind a single schema_version."
        )
    return heads[0]


# ---------------------------------------------------------------------------
# contract digests
# ---------------------------------------------------------------------------


def contract_digests(contract_dir: Path) -> dict[str, str]:
    """sha256 of each contract fixture, keyed by fixture id.

    This is a *raw file* hash, matching what Story 1.9 recorded. It is
    deliberately NOT the RFC 8785 canonical-JSON rule used by
    `adapters/postgres/fixture_history.py`: that rule hashes fixture *payloads*
    to establish database identity, which is a different thing from pinning the
    exact bytes of a committed contract artifact. Do not "fix" one to match the
    other.
    """
    digests: dict[str, str] = {"algorithm": "sha256"}
    for path in sorted(contract_dir.glob("*.json")):
        fixture_id = path.name.split(".")[0]
        digests[fixture_id] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def _fixture_specs() -> Sequence[Any]:
    # Imported, never re-declared: `default_fixtures()` already pins the
    # governed fixture identities and versions. A second copy would be a
    # second source of truth.
    from scripts.gate_a_cutover import default_fixtures

    return default_fixtures()


def resolve_bindings(
    declared: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    fixtures: Iterable[Any] | None = None,
    migrations_dir: Path | None = None,
    contract_dir: Path | None = None,
    code_extra: Mapping[str, Any] | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    """Build a complete NFR27 ``version_bindings`` block.

    ``declared`` supplies the prose bindings the repository cannot infer; every
    key in :data:`DECLARED_BINDING_KEYS` is required. Extra keys pass through
    (Story 1.10 carries `axe_core_version` and friends this way). The bindings
    in :data:`DERIVED_BINDING_KEYS` are resolved here and may not be supplied.
    """
    missing = [key for key in DECLARED_BINDING_KEYS if key not in declared]
    if missing:
        raise ValueError(
            "Missing required NFR27 binding(s): "
            f"{', '.join(missing)}. A binding that does not apply keeps its "
            "key and states the reason; it is never omitted."
        )
    supplied_derived = [key for key in DERIVED_BINDING_KEYS if key in declared]
    if supplied_derived:
        raise ValueError(
            "Binding(s) resolved from the repository may not be supplied by the "
            f"caller: {', '.join(supplied_derived)}. Hardcoding these is the "
            "defect this module exists to prevent."
        )

    code, used_override = resolve_code_binding(repo_root, allow_dirty=allow_dirty)
    if code_extra:
        clashes = [key for key in code_extra if key in code]
        if clashes:
            raise ValueError(
                f"code_extra may not override derived key(s): {', '.join(clashes)}"
            )
        code.update(code_extra)

    versions_dir = migrations_dir or (repo_root / "backend" / "migrations" / "versions")
    contracts = contract_dir or (repo_root / "data" / "contract")

    specs = list(fixtures) if fixtures is not None else list(_fixture_specs())
    identities = [f"{spec.fixture_id}:{spec.version}" for spec in specs]

    bindings: dict[str, Any] = {
        "dataset": (
            f"{len(identities)} governed fixtures ({', '.join(identities)}); "
            "contract sha256 digests recorded alongside"
        ),
        "evaluator": declared["evaluator"],
        "model": declared["model"],
        "prompt": declared["prompt"],
        "tool": declared["tool"],
        "policy": declared["policy"],
        "application": declared["application"],
        "scenario": " and ".join(identities),
        "solver": declared["solver"],
        "code": code,
        "image": dict(_LOCAL_IMAGE_BINDING),
        "schema_version": resolve_alembic_head(versions_dir),
    }

    # Caller extras (axe_core_version, enabled_rule_delta, ...) pass through.
    for key, value in declared.items():
        if key not in bindings:
            bindings[key] = value

    if used_override:
        bindings["binding_override"] = _ALLOW_DIRTY_NOTE

    return bindings


# ---------------------------------------------------------------------------
# auditing an already-written evidence file
# ---------------------------------------------------------------------------

#: Paths that carry no product code. A commit touching only these proves
#: nothing about the behaviour an evidence file claims to have measured —
#: `evidence/story-1.10` recorded a `docs(1-10): create story context` commit,
#: which is exactly the failure this catches.
_NON_CODE_PREFIXES = ("_bmad-output/", "docs/", "evidence/", ".planning/")
_NON_CODE_SUFFIXES = (".md",)


def _is_code_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return False
    if normalized.startswith(_NON_CODE_PREFIXES):
        return False
    return not normalized.endswith(_NON_CODE_SUFFIXES)


def audit_evidence_file(
    evidence_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Return every convention violation in one evidence JSON file.

    An empty tuple means the file is fully bound: its bindings are complete,
    its `schema_version` matches the current migration head, and its
    `git_commit` names a real ancestor commit that actually touched code.
    """
    violations: list[str] = []
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001
        return (f"unreadable evidence file: {exc}",)

    bindings = document.get("version_bindings")
    if not isinstance(bindings, dict):
        return (
            "missing `version_bindings` block; NFR27 requires all eleven "
            "bindings on every evidence report",
        )

    for key in NFR27_BINDING_KEYS:
        if key not in bindings:
            violations.append(f"missing NFR27 binding: {key}")

    # schema_version
    head = resolve_alembic_head(repo_root / "backend" / "migrations" / "versions")
    recorded_schema = bindings.get("schema_version")
    if recorded_schema is None:
        violations.append("missing `schema_version` binding")
    elif recorded_schema != head:
        violations.append(
            f"schema_version {recorded_schema!r} is not the current "
            f"migration head {head!r}"
        )

    # code binding
    code = bindings.get("code")
    if not isinstance(code, dict):
        violations.append("missing `code` binding block")
    else:
        if code.get("working_tree_dirty") and not bindings.get("binding_override"):
            violations.append(
                "recorded on a dirty working tree with no `binding_override` "
                "explaining why"
            )
        commit = code.get("git_commit")
        if not isinstance(commit, str) or not commit:
            violations.append("missing `code.git_commit`")
        elif not _git_ok(repo_root, "cat-file", "-e", f"{commit}^{{commit}}"):
            violations.append(f"git_commit {commit} is not a real commit object")
        elif not _git_ok(repo_root, "merge-base", "--is-ancestor", commit, "HEAD"):
            violations.append(f"git_commit {commit} is not an ancestor of HEAD")
        else:
            touched = _git(
                repo_root, "show", "--name-only", "--pretty=format:", commit
            ).splitlines()
            if not any(_is_code_path(line) for line in touched):
                violations.append(
                    f"git_commit {commit} touches no code file — it cannot "
                    "prove anything about the behaviour measured"
                )

    # referenced paths
    for reference in _referenced_paths(document):
        if not (repo_root / reference).exists():
            violations.append(f"referenced path does not exist: {reference}")

    # contract digests
    recorded_digests = document.get("contract_digests")
    if isinstance(recorded_digests, dict):
        actual = contract_digests(repo_root / "data" / "contract")
        for key, value in recorded_digests.items():
            if key not in actual:
                violations.append(f"contract_digests names unknown artifact: {key}")
            elif actual[key] != value:
                violations.append(
                    f"contract_digests[{key}] does not match the real sha256"
                )

    return tuple(violations)


_PATH_HINT_KEYS = ("contract", "checklist", "path", "source_path")


def _referenced_paths(node: Any, _seen: set[str] | None = None) -> tuple[str, ...]:
    """Collect repo-relative paths referenced anywhere in an evidence document."""
    found: set[str] = set() if _seen is None else _seen
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _PATH_HINT_KEYS and isinstance(value, str) and "/" in value:
                found.add(value)
            else:
                _referenced_paths(value, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _referenced_paths(item, found)
    return tuple(sorted(found))


__all__ = [
    "DECLARED_BINDING_KEYS",
    "audit_evidence_file",
    "DERIVED_BINDING_KEYS",
    "NFR27_BINDING_KEYS",
    "DirtyTreeError",
    "MigrationGraphError",
    "REPO_ROOT",
    "contract_digests",
    "resolve_alembic_head",
    "resolve_bindings",
    "resolve_code_binding",
    "working_tree_status",
]
