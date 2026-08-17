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

#: Recorded when the dirty-tree check exempted a caller's own output file. Not
#: an override: no code was uncommitted, so the recorded commit still
#: reproduces the measurement. It is written down so the exemption is auditable
#: rather than invisible.
_OUTPUT_EXEMPT_NOTE = (
    "output path(s) exempted from the dirty-tree check: {paths}. "
    "No source change was uncommitted; the recorded commit reproduces this "
    "measurement."
)

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


def commit_date(commit: str, repo_root: Path = REPO_ROOT) -> str:
    """Committer date of ``commit`` as a strict-ISO 8601 string."""
    return _git(repo_root, "show", "-s", "--format=%cI", commit)


def _normalize_repo_path(path: str | Path, repo_root: Path = REPO_ROOT) -> str:
    """Render ``path`` the way ``git status --porcelain`` reports it.

    Porcelain prints repo-relative, forward-slashed paths. Callers hand us
    absolute `Path`s (``--output`` resolves to one), so both sides have to be
    reduced to the same shape before a set membership test means anything.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(Path(repo_root).resolve())
        except ValueError:
            # Outside the repository: it can never match a porcelain entry, so
            # returning the absolute form simply never matches. Not an error —
            # an `--output` written outside the tree does not dirty the tree.
            return candidate.as_posix()
    return candidate.as_posix()


def working_tree_status(
    repo_root: Path = REPO_ROOT,
    *,
    ignore_paths: frozenset[str] = frozenset(),
) -> tuple[bool, tuple[str, ...]]:
    """Return ``(dirty, offending_paths)`` for ``repo_root``.

    Untracked (``??``) entries count as dirty: an untracked file is state the
    recorded commit cannot describe, so a measurement taken beside one is no
    more reproducible than one taken on a modified tracked file.

    ``ignore_paths`` exempts specific repo-relative paths from the verdict. It
    exists for exactly one shape of caller: a generator whose own output file
    is what dirties the tree. `gate_a_readiness.main()` writes
    `evidence/gate-a-readiness.json`, which meant the second consecutive run
    died on :class:`DirtyTreeError` before doing any work — the tool soiling
    the very precondition it demands, and the origin of the two-commit dance.

    The distinction the exemption draws is between *dirty because code is
    uncommitted* — which must still refuse, because the recorded commit cannot
    reproduce the measurement — and *dirty because of the output file this
    command is about to overwrite*, which changes nothing about whether the
    recorded commit describes the code that was measured.

    Note there is no separate "only the output file may be dirty" guard: the
    filter provides it. Exempt entries are dropped, and anything else still
    standing keeps ``dirty`` true, so a stray edited `.py` refuses exactly as
    before.
    """
    # `--untracked-files=all` is required, not cosmetic. Plain `--porcelain`
    # collapses a wholly-untracked directory into a single `evidence/` entry, so
    # an exemption naming `evidence/gate-a-readiness.json` would never match it
    # and the first run against a fresh checkout would refuse. Expanding to one
    # entry per file also keeps the exemption honest: exempting one file inside
    # an untracked directory must not clear its siblings.
    porcelain = _git_raw(repo_root, "status", "--porcelain", "--untracked-files=all")
    if not porcelain.strip():
        return False, ()
    ignored = {_normalize_repo_path(entry, repo_root) for entry in ignore_paths}
    paths: list[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        # Porcelain v1: two status columns, then the path. Renames render as
        # `old -> new`; both halves are reported.
        entry = line[2:].strip().strip('"')
        for part in entry.split(" -> "):
            part = part.strip().strip('"')
            if part and _normalize_repo_path(part, repo_root) not in ignored:
                paths.append(part)
    return bool(paths), tuple(paths)


def resolve_code_binding(
    repo_root: Path = REPO_ROOT,
    *,
    allow_dirty: bool = False,
    ignore_paths: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], bool]:
    """Return the ``code`` binding plus whether the dirty escape hatch was used.

    ``ignore_paths`` is forwarded to :func:`working_tree_status`; see its
    docstring for what the exemption means and why it is safe.
    """
    dirty, paths = working_tree_status(repo_root, ignore_paths=ignore_paths)
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


def _revision_graph(versions_dir: Path) -> dict[str, Any]:
    """Map every migration revision to its ``down_revision``."""
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
        if revision in revisions:
            raise MigrationGraphError(
                f"Duplicate migration revision {revision!r} under {versions_dir}. "
                "Two files declaring the same revision silently drop one edge "
                "of the graph, so the head cannot be trusted."
            )
        revisions[revision] = _literal(down_match.group(1)) if down_match else None
    return revisions


def resolve_alembic_chain(versions_dir: Path) -> tuple[str, ...]:
    """Return the revision chain from the single head back to the root.

    Head first. This is the set an already-written evidence file's
    ``schema_version`` is checked against: a revision that was the head when a
    measurement was taken stays on the chain forever as history moves forward,
    so the check ages correctly. See ``audit_evidence_file``.
    """
    revisions = _revision_graph(versions_dir)
    head = resolve_alembic_head(versions_dir)
    chain: list[str] = []
    seen: set[str] = set()
    current: Any = head
    while isinstance(current, str):
        if current in seen:
            raise MigrationGraphError(
                f"Cycle in the migration graph at {current!r} under "
                f"{versions_dir}; the chain to the head is not well defined."
            )
        seen.add(current)
        chain.append(current)
        if current not in revisions:
            raise MigrationGraphError(
                f"Migration {current!r} is referenced as a down_revision under "
                f"{versions_dir} but no file declares it. The graph is broken."
            )
        current = revisions[current]
    return tuple(chain)


def resolve_alembic_head(versions_dir: Path) -> str:
    """Walk ``down_revision`` across the migration files to the single head.

    A file-graph walk on purpose: report generation must stay runnable with no
    PostgreSQL service up, so this never queries a live schema and never shells
    out to the migration tool.
    """
    revisions = _revision_graph(versions_dir)

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


def file_digest(path: Path) -> str:
    """sha256 of one file's raw bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
        # `foo.projection-v1.json` and `foo.projection-v2.json` both reduce to
        # `foo`, and a file literally named `algorithm.json` would overwrite the
        # algorithm marker. Either way the block would claim to pin more
        # artifacts than it records, so refuse rather than silently drop one.
        if fixture_id in digests:
            raise ValueError(
                f"Contract digest key collision on {fixture_id!r} at {path.name}. "
                "Two artifacts reduce to one key, so the recorded block would "
                "pin only the last of them."
            )
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


def _exercised_exemptions(
    repo_root: Path, ignore_paths: frozenset[str]
) -> tuple[str, ...]:
    """Which ``ignore_paths`` entries are actually dirty right now.

    Offering an exemption and needing one are different things, and only the
    second belongs in the artifact. Costs one extra `git status` and only when
    a caller passes a non-empty set.
    """
    if not ignore_paths:
        return ()
    _, dirty_paths = working_tree_status(repo_root)
    ignored = {_normalize_repo_path(entry, repo_root) for entry in ignore_paths}
    return tuple(
        path
        for path in dirty_paths
        if _normalize_repo_path(path, repo_root) in ignored
    )


def resolve_bindings(
    declared: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    fixtures: Iterable[Any] | None = None,
    dataset_files: Iterable[Path] | None = None,
    migrations_dir: Path | None = None,
    contract_dir: Path | None = None,
    code_extra: Mapping[str, Any] | None = None,
    code_binding: Mapping[str, Any] | None = None,
    allow_dirty: bool = False,
    ignore_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Build a complete NFR27 ``version_bindings`` block.

    ``declared`` supplies the prose bindings the repository cannot infer; every
    key in :data:`DECLARED_BINDING_KEYS` is required. Extra keys pass through
    (Story 1.10 carries `axe_core_version` and friends this way). The bindings
    in :data:`DERIVED_BINDING_KEYS` are resolved here and may not be supplied.

    Gate A callers omit ``dataset_files`` and preserve the original behavior:
    dataset and scenario both derive from the governed fixtures. Evaluation
    callers pass committed golden JSON files, which derives an independent
    dataset binding while ``fixtures`` continues to describe scenario data.

    ``ignore_paths`` exempts a caller's own output file from the dirty-tree
    refusal (see :func:`working_tree_status`). When an exemption is actually
    exercised — the path was dirty and was dropped — the resulting block records
    a ``binding_scope`` naming it, so the exemption is visible in the artifact
    rather than silent. ``working_tree_dirty`` stays ``false``, which is the
    honest answer: the recorded commit still reproduces the measurement.
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

    if code_binding is not None:
        # Reuse a `code` block resolved earlier in the same pass, on the clean
        # tree, before any file was written. This is the multi-file case: the
        # first write dirties the tree, so re-resolving for the second file
        # would either refuse or record a spurious dirty flag. The block still
        # names the commit that was measured, which is the whole contract.
        if not isinstance(code_binding, Mapping) or not code_binding.get("git_commit"):
            raise ValueError(
                "code_binding must carry `git_commit`; without it nothing ties "
                "the recorded results to a tree."
            )
        if code_binding.get("working_tree_dirty") and not allow_dirty:
            raise DirtyTreeError(
                "The supplied code_binding was itself resolved on a dirty tree. "
                "Reusing it would launder that, so it is refused."
            )
        code, used_override = dict(code_binding), False
        exempted: tuple[str, ...] = ()
    else:
        # Resolve which exempted paths were genuinely dirty BEFORE the filtered
        # call decides the verdict, so `binding_scope` reports an exemption that
        # was actually exercised rather than one merely offered. A caller that
        # passes `ignore_paths` on a clean tree records nothing.
        exempted = _exercised_exemptions(repo_root, ignore_paths)
        code, used_override = resolve_code_binding(
            repo_root, allow_dirty=allow_dirty, ignore_paths=ignore_paths
        )
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

    dataset_binding: Any
    if dataset_files is None:
        dataset_binding = (
            f"{len(identities)} governed fixtures ({', '.join(identities)}); "
            "contract sha256 digests recorded alongside"
        )
    else:
        dataset_binding = _evaluation_dataset_binding(dataset_files, repo_root)

    bindings: dict[str, Any] = {
        "dataset": dataset_binding,
        "evaluator": declared["evaluator"],
        "model": declared["model"],
        "prompt": declared["prompt"],
        "tool": declared["tool"],
        "policy": declared["policy"],
        "application": declared["application"],
        "scenario": (
            " and ".join(identities)
            if identities
            else "not applicable — no scenario fixture touched"
        ),
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

    if exempted:
        bindings["binding_scope"] = _OUTPUT_EXEMPT_NOTE.format(
            paths=", ".join(sorted(exempted))
        )

    return bindings


def _dataset_file_digest(source: Path) -> str:
    """sha256 of a golden case file with line endings normalized to LF.

    Deliberately NOT :func:`file_digest`. That hashes raw working-tree bytes,
    and under `core.autocrlf` the working tree holds CRLF on Windows while the
    committed blob holds LF — so a raw-byte digest moves on checkout and pins
    the platform rather than the dataset. Two engineers on different systems
    must derive the same binding from the same committed cases.

    Scoped to the evaluation dataset on purpose: `file_digest()`'s other call
    sites hash generated artifacts (JUnit XML) and Gate A contract fixtures,
    where raw bytes are the right identity and where changing the rule would
    retroactively unbind Story 1.4/1.5/1.9/1.10/1.11 evidence.
    """
    text = Path(source).read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _evaluation_dataset_binding(
    dataset_files: Iterable[Path], repo_root: Path
) -> dict[str, Any]:
    """Derive an evaluation dataset identity from exact committed file bytes.

    Parsing supplies the semantic identity NFR28 needs (count, versions and tag
    distributions); raw SHA-256 pins the precise artifact bytes, matching
    ``contract_digests()`` rather than fixture-payload canonicalization.
    """
    files: dict[str, dict[str, Any]] = {}
    case_versions: dict[str, str] = {}
    capabilities: dict[str, int] = {}
    risks: dict[str, int] = {}
    for source in sorted((Path(path) for path in dataset_files), key=str):
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot bind golden dataset file {source}: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"Golden dataset file {source} is not a JSON object")
        required = ("case_id", "case_version", "capability", "risk_class")
        missing = [key for key in required if not isinstance(document.get(key), str)]
        if missing:
            raise ValueError(
                f"Golden dataset file {source} lacks string field(s): "
                f"{', '.join(missing)}"
            )
        case_id = document["case_id"]
        if case_id in case_versions:
            raise ValueError(f"Duplicate golden dataset case_id {case_id!r}")
        case_versions[case_id] = document["case_version"]
        capability = document["capability"]
        risk = document["risk_class"]
        capabilities[capability] = capabilities.get(capability, 0) + 1
        risks[risk] = risks.get(risk, 0) + 1
        try:
            key = source.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            key = source.name
        if key in files:
            raise ValueError(f"Golden dataset binding path collision on {key!r}")
        files[key] = {
            "case_id": case_id,
            "case_version": document["case_version"],
            "sha256": _dataset_file_digest(source),
        }

    return {
        "kind": "version-controlled golden evaluation dataset",
        "case_count": len(case_versions),
        "case_versions": dict(sorted(case_versions.items())),
        "capability_distribution": dict(sorted(capabilities.items())),
        "risk_class_distribution": dict(sorted(risks.items())),
        "files": dict(sorted(files.items())),
    }


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

 
def _commit_touches(repo_root: Path, commit: str) -> list[str]:
    """Paths a commit changed, merge commits included.

    `git show --name-only` prints *nothing* for a merge commit, because a merge
    has no single diff. Left unqualified that reads as "touches no code file"
    and falsely unbinds any evidence generated at a merge HEAD — and this
    repository's `main` carries merge commits. `--first-parent -m` picks the
    diff against the first parent, which is the mainline change, and behaves
    identically on ordinary commits.
    """
    return _git(
        repo_root,
        "show",
        "--name-only",
        "--pretty=format:",
        "--first-parent",
        "-m",
        commit,
    ).splitlines()


def audit_evidence_file(
    evidence_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Return every *permanent* convention violation in one evidence file.

    Read-time rules only, and every one of them is monotone: once an evidence
    file satisfies this function it satisfies it forever, unless the file
    itself is edited. That is the whole contract. A rule that can flip from
    pass to fail because the *world* moved on does not belong here — it belongs
    in :func:`audit_evidence_drift`, which reports observations rather than
    verdicts.

    The distinction matters because these two questions are different:

    * "was this evidence generated correctly?"  -> evaluated when it is written
    * "is this evidence still valid now?"       -> evaluated every time it is read

    Story 1.11 originally used one rule for both, which meant a single new
    Alembic revision retroactively unbound every evidence file in the
    repository — and the cheapest way out of that would have been to hand-edit
    the very field the module exists to stop anyone hand-editing.
    """
    violations: list[str] = []
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001
        return (f"unreadable evidence file: {exc}",)

    if not isinstance(document, dict):
        return (
            "evidence file is not a JSON object; an evidence report is a "
            f"mapping, got {type(document).__name__}",
        )

    bindings = document.get("version_bindings")
    if not isinstance(bindings, dict):
        return (
            "missing `version_bindings` block; NFR27 requires all eleven "
            "bindings on every evidence report",
        )

    for key in NFR27_BINDING_KEYS:
        if key not in bindings:
            violations.append(f"missing NFR27 binding: {key}")

    # schema_version. Monotone form: the recorded revision must lie on the
    # chain of migrations leading to the current head. A revision that was the
    # head when the measurement ran stays on that chain as history moves
    # forward, so old evidence keeps passing; a fabricated or branched revision
    # never joins it, so the check still bites.
    chain = resolve_alembic_chain(repo_root / "backend" / "migrations" / "versions")
    recorded_schema = bindings.get("schema_version")
    if recorded_schema is None:
        violations.append("missing `schema_version` binding")
    elif recorded_schema not in chain:
        violations.append(
            f"schema_version {recorded_schema!r} is not on the migration chain "
            f"leading to the current head {chain[0]!r}"
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
        elif not any(_is_code_path(line) for line in _commit_touches(repo_root, commit)):
            violations.append(
                f"git_commit {commit} touches no code file — it cannot "
                "prove anything about the behaviour measured"
            )

    return tuple(violations)


def audit_evidence_drift(
    evidence_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[str, ...]:
    """Report where the repository has moved on from what an evidence file recorded.

    These observations are deliberately *not* violations. A renamed contract
    fixture or an edited artifact means the world changed since the
    measurement — useful to surface, but it says nothing about whether the
    evidence was honestly produced, and treating it as a binding failure would
    block the gate for a reason unrelated to the gate.
    """
    drift: list[str] = []
    try:
        document = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # noqa: BLE001
        return ()
    if not isinstance(document, dict):
        return ()

    for reference in _referenced_paths(document):
        if not (repo_root / reference).exists():
            drift.append(f"referenced path no longer exists: {reference}")

    recorded_digests = document.get("contract_digests")
    if isinstance(recorded_digests, dict):
        try:
            actual = contract_digests(repo_root / "data" / "contract")
        except (OSError, ValueError):  # noqa: BLE001
            return tuple(drift)
        for key, value in recorded_digests.items():
            if key not in actual:
                drift.append(f"contract artifact no longer present: {key}")
            elif actual[key] != value:
                drift.append(
                    f"contract artifact {key} has changed since it was measured"
                )

    return tuple(drift)


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
    "audit_evidence_drift",
    "audit_evidence_file",
    "DERIVED_BINDING_KEYS",
    "NFR27_BINDING_KEYS",
    "DirtyTreeError",
    "MigrationGraphError",
    "REPO_ROOT",
    "commit_date",
    "contract_digests",
    "file_digest",
    "resolve_alembic_chain",
    "resolve_alembic_head",
    "resolve_bindings",
    "resolve_code_binding",
    "working_tree_status",
]
