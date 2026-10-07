"""Generate `evidence/epic-5/release-gate-report.json` (Story 5.13).

Composes, without copying:

* :mod:`scripts.gate_b_checks`    — which checks decide each Gate B row
* :mod:`scripts.junit_ingest`     — what the test runners actually reported
* :mod:`scripts.evidence_binding` — NFR27 bindings and the evidence audit
* :mod:`scripts.gate_a_readiness` — XML provenance and Gate A's evidence rule,
  for the checks Gate B imports from Gate A

Usage (order matters, see docs/EVIDENCE-CONVENTION.md and docs/TESTING.md)::

    git commit code                         # clean tree before measuring
    # live evidence, NFR35 regeneration, then JUnit at the bound commit:
    uv run --frozen pytest --junitxml=../_bmad-output/test-artifacts/gate-b/pytest.xml
    uv run --frozen pytest -m postgres -s --junitxml=../_bmad-output/test-artifacts/gate-b/postgres.xml
    uv run --frozen python scripts/gate_b_readiness.py \\
        --pytest-xml ../_bmad-output/test-artifacts/gate-b/pytest.xml \\
        --postgres-xml ../_bmad-output/test-artifacts/gate-b/postgres.xml \\
        --vitest-xml ../_bmad-output/test-artifacts/gate-b/vitest.xml \\
        --playwright-xml ../_bmad-output/test-artifacts/gate-b/playwright.xml \\
        --code-from ../evidence/story-1.4/nfr35-scenario-data-load.json

`--code-from` names evidence regenerated at HEAD (here, an NFR35 file written
just before); it is refused unless its commit is HEAD and only `evidence/` is
uncommitted. Never a live file: those are measured at an ancestor commit.

Each row's result is decided per Story 5.13 D2: an evidence-backed check reads
its declared verdict key and nothing else, and must also be audit-clean and
fresh (D12); a test-backed check needs its cases present, passed and unskipped.
Exits 0 only if Gate B passed. A report recording "not passed" is still a valid
artifact (AC5): never tune the registry or soften a result to reach `true`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.evidence_binding import (  # noqa: E402
    REPO_ROOT,
    audit_evidence_file,
    file_digest,
    nearest_code_commit,
    resolve_bindings,
    working_tree_status,
)
from scripts.gate_a_checks import GATE_A_CHECKS  # noqa: E402
from scripts.gate_a_readiness import (  # noqa: E402
    _evidence_result as gate_a_evidence_result,
    _validate_supplied_bindings,
    _xml_provenance,
)
from scripts.gate_b_checks import (  # noqa: E402
    BLOCKING_REGRESSION_CATEGORIES,
    GATE_B_CHECKS,
    GATE_B_ROWS,
    GOLDEN_CASE_FLOOR,
    LIVE_FRESHNESS_PATHS,
    PER_CAPABILITY_FLOOR,
    PROTECTED_CASE_FLOOR,
    PROTECTED_RISK_CLASSES,
    GateBCheck,
    GateBRow,
    validate_registry,
)
from scripts.junit_ingest import (  # noqa: E402
    RunnerReport,
    file_outcomes,
    missing_pytest_cases,
    parse_junit,
)

DEFAULT_OUTPUT = REPO_ROOT / "evidence" / "epic-5" / "release-gate-report.json"
LIVE_CONVERSATION_BASELINE = REPO_ROOT / "backend" / "evals" / "baselines" / "live-conversations.json"

#: Results that do not prove a check. `excepted` is deliberately absent: it is
#: a blocked live verdict waived by a complete, unexpired release exception,
#: which the report lists under `release_exceptions` (AC5).
_NON_PROVING = ("failed", "skipped", "missing")

_DECLARED_BINDINGS = {
    "evaluator": (
        "pytest, Vitest and Playwright results read from JUnit XML; live "
        "single-turn routing and multi-turn evidence read by verdict key; "
        "in-process dataset-floor and freshness checks (scripts/gate_b_checks.py)"
    ),
    "model": (
        "deterministic double for every JUnit-backed check; the live models are "
        "bound in each registered live evidence file"
    ),
    "prompt": "versioned golden prompts; live prompts bound in each live evidence file",
    "tool": "every installed capability module (application/capabilities/installed.py)",
    "policy": (
        "Release Gate table, Gate B rows (epics.md); NFR28 floors amended by "
        "Story 5.13 D4-D6; AD-16 live-conversation verdict; NFR27 bindings"
    ),
    "application": "local backend and frontend source tree at the bound commit",
    "solver": "OR-Tools CP-SAT as exercised by the registered PostgreSQL proof suites",
}

HONEST_GAPS: tuple[str, ...] = (
    "NFR35 with tracing on is unmeasured: every measurement and CI run is keyless "
    "(LOGFIRE_TOKEN unset), so Story 5.9's tracing is not installed (D7; "
    "deferred-work.md, revisit at the first hosted measurement or Story 6.4).",
    "NFR35 1.4/1.5 tests time around TestClient.get (client-side clock), not the "
    "protocol's server-side request receipt (D7).",
    "Hosted latency (NFR17) is not a Gate B row and is not measured here.",
    "grounding-supported (scheduling_compute) grounds in fixture rows d-outbound-0/1 "
    "tagged unit=headcount, which docs/DOMAIN-MODEL.md §1 forbids (outbound is "
    "always volume). It is an eval-projection defect, not a production one; its "
    "routing verdict is unaffected and its grounding half stays as measured (D11).",
    "Blocking-regressions categories are assigned by judgement; whether a "
    "registered file is topically relevant to its category is not machine-checked (D13).",
    "Consequential behaviour with no model-facing surface (Story 4.5's stale, "
    "expired and replayed approvals) is proven by PostgreSQL proof nodes, not "
    "golden cases, so it is outside the dataset floors (D6).",
)


# ---------------------------------------------------------------------------
# dataset (D4-D6)
# ---------------------------------------------------------------------------


def _manifest_risk_by_capability() -> dict[str, str]:
    from application.capabilities.installed import installed_modules

    return {m.manifest.capability_name: m.manifest.risk_class for m in installed_modules()}


#: A golden case's `capability` tag is not always the registered tool name.
_TAG_TO_CAPABILITY = {"demonstration": "shiftmind_demonstration"}


def tag_integrity_violations(
    cases: Sequence[Any],
    manifest_risk: Mapping[str, str],
    *,
    counted_tags: Collection[str] | None = None,
) -> list[str]:
    """D6: a protected tag must be backed by what the case actually expects.

    * `consequential` needs an expected call to a capability whose manifest is
      `consequential`;
    * `prohibited` needs the deterministic `expected_outcome: "refuse"` (F9:
      not the live expectation, which may legitimately be `allow`);
    * and the converse (Story 5.13 review): a case expecting a call to a
      `consequential` capability must carry a protected tag, or it would escape
      the protected population and the 100% bar. Applied to the cases on
      `counted_tags` (every case when None): an excluded capability's cases
      count toward no floor.
    """
    violations: list[str] = []
    for case in cases:
        called = [call.tool_name for call in case.expected_tool_calls]
        if (
            case.risk_class not in PROTECTED_RISK_CLASSES
            and (counted_tags is None or case.capability in counted_tags)
            and any(manifest_risk.get(name) == "consequential" for name in called)
        ):
            violations.append(
                f"{case.case_id}: expects a call to a consequential capability "
                f"({called}) but is tagged {case.risk_class!r}, not consequential/prohibited"
            )
        if case.risk_class == "consequential":
            if not any(manifest_risk.get(name) == "consequential" for name in called):
                violations.append(
                    f"{case.case_id}: tagged consequential but expects no call to a "
                    f"consequential capability (expected {called or 'no call'})"
                )
        elif case.risk_class == "prohibited" and case.expected_outcome != "refuse":
            violations.append(
                f"{case.case_id}: tagged prohibited but its deterministic "
                f"expected_outcome is {case.expected_outcome!r}, not 'refuse'"
            )
    return violations


def golden_dataset_summary(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Counts, floors, per-capability and protected tallies, and integrity."""
    from evals.cases import load_cases, load_multi_turn_cases
    from evals.release_configuration import release_allowed_capabilities

    single = load_cases(repo_root / "backend" / "evals" / "golden")
    multi = load_multi_turn_cases(repo_root / "backend" / "evals" / "golden_multi_turn")
    allowed = release_allowed_capabilities()
    allowed_tags = {
        tag for tag in {case.capability for case in single}
        if _TAG_TO_CAPABILITY.get(tag, tag) in allowed
    }
    per_capability = {
        capability: sum(1 for case in single if case.capability == capability)
        for capability in sorted(allowed)
    }
    protected = sorted(
        case.case_id for case in single
        if case.risk_class in PROTECTED_RISK_CLASSES and case.capability in allowed_tags
    )
    return {
        "single_turn_cases": len(single),
        "multi_turn_cases": len(multi),
        "total_cases": len(single) + len(multi),
        "golden_case_floor": GOLDEN_CASE_FLOOR,
        "release_allowed_capabilities": sorted(allowed),
        "per_capability_floor": PER_CAPABILITY_FLOOR,
        "per_capability": per_capability,
        "per_capability_shortfalls": sorted(
            name for name, count in per_capability.items() if count < PER_CAPABILITY_FLOOR
        ),
        "excluded_capabilities": sorted({case.capability for case in single} - allowed_tags),
        "protected_case_floor": PROTECTED_CASE_FLOOR,
        "protected_cases": protected,
        "protected_case_count": len(protected),
        "tag_integrity_violations": tag_integrity_violations(
            single, _manifest_risk_by_capability(), counted_tags=allowed_tags
        ),
    }


# ---------------------------------------------------------------------------
# per-check evaluation
# ---------------------------------------------------------------------------


@dataclass
class _Context:
    repo_root: Path
    gate_commit: str
    tree_dirty: bool
    now: datetime
    dataset: dict[str, Any]
    outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    reports: dict[str, RunnerReport] = field(default_factory=dict)
    release_exceptions: list[dict[str, Any]] = field(default_factory=list)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )


def code_ancestor_staleness(bound: str | None, gate_commit: str, repo_root: Path) -> str | None:
    """D12: why `bound` is stale for `gate_commit`, or None when it is fresh."""
    if not bound:
        return "the evidence records no code.git_commit"
    if bound == gate_commit:
        return None
    if _git(repo_root, "merge-base", "--is-ancestor", bound, gate_commit).returncode != 0:
        return f"measured at {bound}, which is not an ancestor of the Gate B commit {gate_commit}"
    diff = _git(
        repo_root, "diff", "-z", "--name-only", bound, gate_commit, "--", *LIVE_FRESHNESS_PATHS
    )
    if diff.returncode != 0:
        # Fail closed: an unreadable diff is not proof that nothing changed.
        return f"could not diff {bound} against {gate_commit}: {diff.stderr.strip()}"
    changed = [name for name in diff.stdout.split("\0") if name]
    if changed:
        listed = ", ".join(changed[:3]) + (", …" if len(changed) > 3 else "")
        return (
            f"measured at {bound}; {len(changed)} file(s) under the live-freshness "
            f"paths changed before {gate_commit} ({listed})"
        )
    return None


def _exception_problems(document: Mapping[str, Any], now: datetime) -> list[str]:
    """AC5: owner, rationale, scope, expiry and user-facing limitation, unexpired."""
    record = document.get("exception")
    if not isinstance(record, dict):
        return ["no exception record"]
    problems = [
        f"exception.{key} is missing or empty"
        for key in ("owner", "rationale", "scope", "expires_at", "compensating_limitation")
        if not isinstance(record.get(key), str) or not record[key].strip()
    ]
    if not problems:
        try:
            expires = datetime.fromisoformat(record["expires_at"])
        except ValueError:
            return ["exception.expires_at is not an ISO timestamp"]
        if expires.tzinfo is None:
            problems.append("exception.expires_at is not timezone-aware")
        elif expires <= now:
            problems.append(f"exception expired at {record['expires_at']}")
    return problems


def _evidence_result(check: GateBCheck, ctx: _Context) -> tuple[str, bool, str, dict[str, Any]]:
    """`(result, bound, detail, artifact)` for an evidence-backed check."""
    path = ctx.repo_root / str(check.evidence_path)
    artifact: dict[str, Any] = {"evidence": check.evidence_path}
    if check.gate_a_check:
        # Reused, not re-implemented: Gate A's own reading of its own files,
        # manual-gate rule included.
        source = next(c for c in GATE_A_CHECKS if c.check == check.gate_a_check)
        result, bound, detail = gate_a_evidence_result(source, repo_root=ctx.repo_root)
        if path.is_file():
            artifact["sha256"] = file_digest(path)
        return result, bound, detail, artifact
    if not path.is_file():
        return "missing", False, f"evidence file not found: {check.evidence_path}", artifact
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "missing", False, f"unreadable evidence file: {exc}", artifact
    if not isinstance(document, dict):
        return "missing", False, "evidence file is not a JSON object", artifact
    artifact["sha256"] = file_digest(path)
    code = ((document.get("version_bindings") or {}).get("code") or {})
    artifact["git_commit"] = code.get("git_commit")

    details: list[str] = []
    if check.verdict_key not in document:
        result = "missing"
        details.append(f"evidence records no `{check.verdict_key}` verdict")
    else:
        verdict = document[check.verdict_key]
        artifact["verdict"] = verdict
        if verdict in check.verdict_pass_values:
            result = "passed"
        elif check.exception_value is not None and verdict == check.exception_value:
            problems = _exception_problems(document, ctx.now)
            if problems:
                result = "failed"
                details.append(
                    f"`{check.verdict_key}: {verdict}` but the release exception is "
                    "incomplete: " + "; ".join(problems)
                )
            else:
                result = "excepted"
        else:
            result = "failed"
            reasons = document.get("blocking_reasons")
            details.append(
                f"recorded `{check.verdict_key}: {verdict!r}`"
                + (f" ({', '.join(map(str, reasons))})" if reasons else "")
            )

    violations = audit_evidence_file(path, repo_root=ctx.repo_root)
    bound = not violations
    if violations:
        details.append("unbound: " + "; ".join(violations))
    if check.freshness == "code_ancestor":
        stale = code_ancestor_staleness(code.get("git_commit"), ctx.gate_commit, ctx.repo_root)
        if stale:
            # D12: stale evidence makes its row missing and blocking.
            if result in ("passed", "excepted"):
                result = "missing"
            details.append(f"stale: {stale}")
    if result == "excepted":
        # Recorded only once the waived evidence is known to be fresh; a stale
        # exception must not appear to cover anything.
        ctx.release_exceptions.append({
            "check": check.check, "row": check.row,
            "blocking_reasons": document.get("blocking_reasons", []),
            **{key: document["exception"][key] for key in (
                "owner", "rationale", "scope", "expires_at", "compensating_limitation")},
        })
    return result, bound, "; ".join(details), artifact


def _test_cases_result(check: GateBCheck, ctx: _Context) -> tuple[str, dict[str, Any]]:
    report = ctx.reports.get(str(check.runner))
    statuses: dict[str, str] = {}
    for path, name in check.test_cases:
        if report is None:
            statuses[f"{path}::{name}"] = "missing"
            continue
        matching = [
            case for case in report.cases
            if case.file == path and (case.name == name or case.name.startswith(name + "["))
        ]
        if not matching:
            statuses[f"{path}::{name}"] = "missing"
        elif any(case.status == "failed" for case in matching):
            statuses[f"{path}::{name}"] = "failed"
        elif any(case.status == "skipped" for case in matching):
            statuses[f"{path}::{name}"] = "skipped"
        else:
            statuses[f"{path}::{name}"] = "passed"
    values = set(statuses.values())
    for candidate in ("failed", "missing", "skipped"):
        if candidate in values:
            return candidate, {"runner": check.runner, "cases": statuses}
    return "passed", {"runner": check.runner, "cases": statuses}


def _tests_result(check: GateBCheck, ctx: _Context) -> tuple[str, bool, str, dict[str, Any]]:
    if check.test_cases:
        result, source = _test_cases_result(check, ctx)
        detail = "; ".join(f"{key}: {status}" for key, status in source["cases"].items()
                           if status != "passed")
    else:
        outcomes = ctx.outcomes.get(str(check.runner), {})
        per_file = {path: outcomes.get(path) for path in check.test_files}
        details = []
        statuses = []
        for path, outcome in per_file.items():
            status = outcome.status if outcome is not None else "missing"
            if outcome is not None and status == "passed" and outcome.total == 0:
                status = "missing"
            statuses.append(status)
            if status != "passed":
                details.append(
                    f"{path}: {status}"
                    + (f" ({outcome.detail})" if outcome is not None and outcome.detail else "")
                )
        result = "passed"
        for candidate in ("failed", "missing", "skipped"):
            if candidate in statuses:
                result = candidate
                break
        detail = "; ".join(details)
        source = {
            "runner": check.runner,
            "cases": {
                path: (
                    {"status": o.status, "total": o.total, "passed": o.passed,
                     "skipped": o.skipped, "failed": o.failed}
                    if o is not None else {"status": "missing"}
                )
                for path, o in per_file.items()
            },
        }
        if check.required_projects:
            for path, outcome in per_file.items():
                covered = set(outcome.projects) if outcome is not None else set()
                absent = [p for p in check.required_projects if p not in covered]
                if absent and result == "passed":
                    result = "missing"
                if absent:
                    detail = "; ".join(filter(None, [
                        detail,
                        f"{path} ran under {sorted(covered) or 'no'} project(s); claims "
                        f"{', '.join(check.required_projects)}",
                    ]))
    bound = not ctx.tree_dirty
    if ctx.tree_dirty:
        detail = "; ".join(filter(None, [
            detail, "unbound: measured on a dirty tree, so the recorded commit does "
            "not describe what ran"]))
    report = ctx.reports.get(str(check.runner))
    artifact = {"runner": check.runner}
    if report is not None:
        try:
            artifact["junit_sha256"] = file_digest(Path(report.xml_path))
        except OSError:
            artifact["junit_sha256"] = "unavailable"
    return result, bound, detail, {"source": source, "artifact": artifact}


def _computed_result(check: GateBCheck, ctx: _Context) -> tuple[str, str, dict[str, Any]]:
    """`(result, detail, artifact)` for a computed check."""
    name = check.computed
    if name in ("live_conversation_inventory_fresh", "live_conversation_configuration_fresh"):
        return _live_conversation_freshness(name, ctx)
    result, detail = _dataset_result(str(name), ctx)
    return result, detail, {}


def _dataset_result(name: str, ctx: _Context) -> tuple[str, str]:
    data = ctx.dataset
    if name == "golden_case_floor":
        if data["total_cases"] >= GOLDEN_CASE_FLOOR:
            return "passed", ""
        return "failed", (
            f"{data['total_cases']} versioned golden cases "
            f"({data['single_turn_cases']} single-turn + {data['multi_turn_cases']} "
            f"multi-turn) is below the floor of {GOLDEN_CASE_FLOOR}"
        )
    if name == "per_capability_floor":
        short = data["per_capability_shortfalls"]
        if not short:
            return "passed", ""
        return "failed", "below four cases: " + ", ".join(
            f"{c} ({data['per_capability'][c]})" for c in short)
    if name == "protected_floor_and_tag_integrity":
        problems = list(data["tag_integrity_violations"])
        if data["protected_case_count"] < PROTECTED_CASE_FLOOR:
            problems.insert(0, (
                f"{data['protected_case_count']} consequential/prohibited cases on "
                f"release-allowed capabilities, below the floor of {PROTECTED_CASE_FLOOR}"
            ))
        return ("failed", "; ".join(problems)) if problems else ("passed", "")
    return "missing", f"no implementation for computed check {name!r}"


def _live_conversation_document(ctx: _Context) -> dict[str, Any] | None:
    check = next(
        (c for c in GATE_B_CHECKS if c.check == "live_conversation_journeys_evidence"), None
    )
    if check is None:
        return None
    path = ctx.repo_root / str(check.evidence_path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _live_conversation_freshness(
    name: str, ctx: _Context
) -> tuple[str, str, dict[str, Any]]:
    """AD-16 freshness, with both digests recorded so a reader can see what was compared."""
    document = _live_conversation_document(ctx)
    if document is None:
        return "missing", "live-conversation evidence is absent or unreadable", {}
    if name == "live_conversation_inventory_fresh":
        from evals.live_conversations.inventory import capability_inventory

        inventory = capability_inventory()
        current = inventory["digest"]
        recorded = document.get("inventory_digest")
        # AD-16: the report binds the installed-tool/operation inventory it judged.
        artifact = {
            "current_inventory_digest": current,
            "evidence_inventory_digest": recorded,
        }
        if recorded == current:
            return "passed", "", artifact
        return "missing", (
            f"stale: inventory_digest {recorded} differs from the current capability "
            f"inventory {current} (AD-16)"
        ), artifact
    try:
        baseline = json.loads(LIVE_CONVERSATION_BASELINE.read_text(encoding="utf-8"))
        expected = baseline["configuration"]["behavioral_digest"]
    except (OSError, ValueError, KeyError) as exc:
        return "missing", f"the live-conversation baseline is unreadable: {exc}", {}
    recorded = (document.get("measured_configuration") or {}).get("behavioral_digest")
    artifact = {"baseline_behavioral_digest": expected, "evidence_behavioral_digest": recorded}
    if recorded == expected:
        return "passed", "", artifact
    return "missing", (
        f"stale: measured behavioral_digest {recorded} differs from the committed "
        f"baseline's {expected}"
    ), artifact


def live_routing_disclosure(ctx: _Context) -> dict[str, Any] | None:
    """What the live routing evidence recorded beside the verdict (D8), derived.

    Grounding and policy decide nothing in the Tool routing row, and a case the
    chat path never offers is not run. All of that is true and was invisible in
    the report (Story 5.13 review): read here from the evidence itself, never
    hand-typed, so it cannot drift from what was measured.
    """
    check = next((c for c in GATE_B_CHECKS if c.check == "live_golden_routing"), None)
    if check is None:
        return None
    try:
        document = json.loads((ctx.repo_root / str(check.evidence_path)).read_text(encoding="utf-8"))
        runs = list(document["runs"])
    except (OSError, ValueError, KeyError, TypeError):
        return None

    def _failures(field_name: str) -> list[dict[str, Any]]:
        failed: dict[str, dict[str, Any]] = {}
        for run in runs:
            for item in run.get("results", ()):
                if item.get(field_name) is False:
                    entry = failed.setdefault(item["case_id"], {
                        "case_id": item["case_id"], "risk_class": item.get("risk_class"),
                        "counted": item.get("counted"), "runs_failed": 0,
                    })
                    entry["runs_failed"] += 1
        return sorted(failed.values(), key=lambda entry: entry["case_id"])

    first = runs[0].get("results", ()) if runs else ()
    counted_capabilities = {item.get("capability") for item in first if item.get("counted")}
    allowed = ctx.dataset.get("release_allowed_capabilities", [])
    return {
        "label": (
            "recorded beside routing in the live single-turn evidence; grounding and "
            "policy decide nothing in the Tool routing row (D8)"
        ),
        "evidence": check.evidence_path,
        "runs": len(runs),
        "policy_failures": _failures("policy_passed"),
        "grounding_failures": _failures("grounding_passed"),
        "not_offered_on_chat_path": sorted(
            item["case_id"] for item in first
            if item.get("not_run_reason") == "not_offered_on_chat_path"
        ),
        "release_allowed_capabilities_without_a_counted_live_case": sorted(
            set(allowed) - counted_capabilities
        ),
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def build_report(
    reports: Mapping[str, RunnerReport],
    *,
    repo_root: Path = REPO_ROOT,
    allow_dirty: bool = False,
    strict_missing: bool = True,
    bindings: dict[str, Any] | None = None,
    ignore_paths: frozenset[str] = frozenset(),
    checks: tuple[GateBCheck, ...] = GATE_B_CHECKS,
    rows: tuple[GateBRow, ...] = GATE_B_ROWS,
    dataset: dict[str, Any] | None = None,
    deterministic_coverage: dict[str, Any] | None = None,
    measurement_date: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate every registered check and compose the Gate B report.

    `reports` maps runner → parsed JUnit: `pytest` (default suite),
    `pytest-postgres` (the `-m postgres -s` run), `vitest`, `playwright`.
    """
    validate_registry(checks, rows)
    if bindings is None:
        golden = sorted((repo_root / "backend" / "evals" / "golden").rglob("*.json"))
        multi = sorted((repo_root / "backend" / "evals" / "golden_multi_turn").rglob("*.json"))
        bindings = resolve_bindings(
            _DECLARED_BINDINGS,
            repo_root=repo_root,
            dataset_files=golden + multi,
            allow_dirty=allow_dirty,
            ignore_paths=ignore_paths,
        )
    else:
        _validate_supplied_bindings(bindings)
    gate_commit = str(bindings["code"]["git_commit"])
    tree_dirty = bool(bindings["code"].get("working_tree_dirty"))
    ctx = _Context(
        repo_root=repo_root,
        gate_commit=gate_commit,
        tree_dirty=tree_dirty,
        now=now or datetime.now(timezone.utc),
        dataset=dataset if dataset is not None else golden_dataset_summary(repo_root),
        reports=dict(reports),
    )

    for runner in ("pytest", "vitest", "playwright"):
        declared = sorted({
            path for check in checks if check.runner == runner for path in check.test_files
        })
        if not declared:
            continue
        report = reports.get(runner)
        ctx.outcomes[runner] = file_outcomes(
            [report] if report is not None else [], declared, strict=strict_missing
        )

    contributing: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for check in checks:
        artifact: dict[str, Any] = {}
        source: Any
        if check.evidence_path:
            result, bound, detail, artifact = _evidence_result(check, ctx)
            source = check.evidence_path
        elif check.computed:
            result, detail, artifact = _computed_result(check, ctx)
            bound = True
            source = check.computed
        else:
            result, bound, detail, extra = _tests_result(check, ctx)
            source, artifact = extra["source"], extra["artifact"]
        entry: dict[str, Any] = {
            "check": check.check,
            "row": check.row,
            "category": check.category,
            "story": check.story,
            "description": check.description,
            "source_kind": check.source_kind,
            "source": source,
            "result": result,
            "bound": bound,
            "artifact": artifact,
        }
        if check.gate_a_check:
            entry["gate_a_check"] = check.gate_a_check
        if check.verdict_key:
            entry["verdict_key"] = check.verdict_key
        if detail:
            entry["detail"] = detail
        contributing.append(entry)
        if result in _NON_PROVING or not bound:
            reason = detail or f"result: {result}"
            blocking.append({
                "check": check.check,
                "row": check.row,
                "category": check.category,
                "story": check.story,
                "result": result,
                "bound": bound,
                "reason": reason,
                "gate_b_commit": gate_commit,
                "artifact": artifact,
            })

    # Run-level gates: a deselected default-suite test, and a stale XML.
    pytest_declared = sorted({
        path for check in checks if check.runner == "pytest" for path in check.test_files
    })
    if "pytest" in reports:
        for path, absent in sorted(
            missing_pytest_cases([reports["pytest"]], pytest_declared, repo_root=repo_root).items()
        ):
            blocking.append({
                "check": "pytest_case_coverage", "row": "report_version_binding",
                "category": None, "story": "5.13", "result": "missing", "bound": False,
                "reason": (
                    f"{path}: {len(absent)} test function(s) in source produced no case "
                    f"in the JUnit XML ({', '.join(absent[:3])}{', …' if len(absent) > 3 else ''})"
                ),
                "gate_b_commit": gate_commit, "artifact": {},
            })
    provenance = {
        runner: _xml_provenance(report, bindings, repo_root)
        for runner, report in reports.items()
    }
    for runner, entry_ in provenance.items():
        if entry_.get("stale"):
            blocking.append({
                "check": f"{runner}_xml_provenance", "row": "report_version_binding",
                "category": None, "story": "5.13", "result": "missing", "bound": False,
                "reason": entry_["stale"], "gate_b_commit": gate_commit,
                "artifact": {"junit_sha256": entry_.get("sha256")},
            })

    rolled: dict[str, Any] = {}
    for row in rows:
        entries = [e for e in contributing if e["row"] == row.key]
        names = [e["check"] for e in entries]
        row_blocking = [b["check"] for b in blocking if b["row"] == row.key]
        results = {e["result"] for e in entries}
        if "failed" in results:
            status = "failed"
        elif results & {"missing", "skipped"}:
            status = "missing" if "missing" in results else "skipped"
        elif row_blocking:
            status = "unbound"
        elif "excepted" in results:
            status = "excepted"
        else:
            status = "passed"
        record: dict[str, Any] = {
            "title": row.title,
            "result": status,
            "checks": names,
            "blocking": list(dict.fromkeys(row_blocking)),
        }
        if row.key == "blocking_regressions":
            record["categories"] = {
                category: {
                    "checks": [e["check"] for e in entries if e["category"] == category],
                    "blocking": [
                        b["check"] for b in blocking
                        if b["row"] == row.key and b["category"] == category
                    ],
                }
                for category in BLOCKING_REGRESSION_CATEGORIES
            }
        rolled[row.key] = record

    gate_b_passed = not blocking
    return {
        "story": "5.13",
        "gate": "B",
        "requirements": ["Release Gate (epics.md) Gate B rows", "NFR27", "NFR28", "NFR35", "AD-16"],
        "measurement_date": measurement_date or date.today().isoformat(),
        "accountable_owner": "Evaluation/QA",
        "rows": rolled,
        "contributing_checks": contributing,
        "test_evidence": provenance,
        "dataset": ctx.dataset,
        "deterministic_regression_coverage": deterministic_coverage,
        "honest_gaps": list(HONEST_GAPS),
        "live_recorded_results": live_routing_disclosure(ctx),
        "release_exceptions": ctx.release_exceptions,
        "version_bindings": bindings,
        "blocking": blocking,
        "gate_b_passed": gate_b_passed,
        "passed": gate_b_passed,
    }


def deterministic_regression_coverage() -> dict[str, Any]:
    """D8: the deterministic routing pass rate, labelled for what it is.

    A property of the authored cases (each double replays its own script), so
    it is regression coverage for the "Deterministic-first CI" half and never
    a model-quality measure. The Tool routing row reads only live evidence.
    """
    from application.capabilities.installed import installed_modules
    from evals.cases import load_cases
    from evals.report import (
        CaseEvaluation,
        _evaluate_case,
        _run_runtime_case,
        _runtime_for_case,
        build_evaluation_report,
    )

    evaluations = []
    for case in load_cases(REPO_ROOT / "backend" / "evals" / "golden"):
        results: list[object] = []
        runtime = _runtime_for_case(case, installed_modules(), results)
        outcome = _run_runtime_case(runtime, case)
        verdict, outcome = _evaluate_case(case, runtime, outcome, results, run_source="double")
        evaluations.append(CaseEvaluation(case=case, verdict=verdict, outcome=outcome))
    metrics = build_evaluation_report(evaluations, bindings={})["metrics"]
    return {
        "label": (
            "regression coverage of the authored golden cases on the deterministic "
            "double; not a model-quality measure and not the Tool routing verdict (D8)"
        ),
        **metrics,
    }


def donor_code_binding(
    donor_path: Path, *, repo_root: Path = REPO_ROOT, allow_dirty: bool = False
) -> dict[str, Any]:
    """The `code` block `--code-from` reuses, refused unless it describes HEAD.

    The donor exists because writing evidence dirties the tree. Its commit
    becomes the Gate B commit, so it must BE the code the JUnit runs and the
    dataset count ran at: HEAD, or `nearest_code_commit(HEAD)` when HEAD is a
    docs- or evidence-only commit (provably the same code), with nothing but
    `evidence/**` uncommitted. Without this check a donor measured at an older
    commit bound the report to code the tests never ran on.
    """
    try:
        donor = json.loads(Path(donor_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"--code-from {donor_path}: unreadable: {exc}") from None
    code = (donor.get("version_bindings") or {}).get("code") if isinstance(donor, dict) else None
    if not isinstance(code, dict) or not code.get("git_commit"):
        raise SystemExit(f"--code-from {donor_path}: records no version_bindings.code.git_commit")
    head = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    try:
        code_head = nearest_code_commit(repo_root, head)
    except ValueError as exc:
        raise SystemExit(f"--code-from: {exc}") from None
    if code["git_commit"] not in (head, code_head):
        raise SystemExit(
            f"--code-from {donor_path}: measured at {code['git_commit']}, but HEAD is {head}"
            + (f" (code commit {code_head})" if code_head != head else "")
            + "; use evidence regenerated at HEAD (the NFR35 files, for instance)"
        )
    _dirty, paths = working_tree_status(repo_root)
    code_paths = [path for path in paths if not path.startswith("evidence/")]
    if code_paths and not allow_dirty:
        raise SystemExit(
            "--code-from: the tree has uncommitted changes outside evidence/ ("
            + ", ".join(code_paths[:5]) + "); commit them and re-measure"
        )
    return dict(code)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Gate B release-gate report")
    parser.add_argument("--pytest-xml", type=Path, required=True)
    parser.add_argument("--postgres-xml", type=Path, required=True,
                        help="JUnit of `pytest -m postgres -s` (the NFR35 row)")
    parser.add_argument("--vitest-xml", type=Path, required=True)
    parser.add_argument("--playwright-xml", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-dirty", action="store_true",
                        help="resolve bindings against a dirty tree; recorded, and blocks")
    parser.add_argument(
        "--code-from", type=Path, default=None,
        help=("reuse the `version_bindings.code` block of an evidence file measured "
              "at HEAD on a clean tree (writing evidence dirties the tree); refused "
              "unless it names HEAD and only evidence/ is uncommitted"),
    )
    parser.add_argument("--allow-missing", action="store_true",
                        help="report a registry-declared test file absent from the XML "
                             "instead of aborting (it still blocks)")
    args = parser.parse_args(argv)

    reports = {
        "pytest": parse_junit(args.pytest_xml, runner="pytest"),
        "pytest-postgres": parse_junit(args.postgres_xml, runner="pytest"),
        "vitest": parse_junit(args.vitest_xml, runner="vitest"),
        "playwright": parse_junit(args.playwright_xml, runner="playwright"),
    }
    output_exemptions = frozenset(
        {str(args.output), str(args.output.with_suffix(args.output.suffix + ".tmp"))}
    )
    bindings = None
    if args.code_from:
        donor_code = donor_code_binding(args.code_from, allow_dirty=args.allow_dirty)
        golden = sorted((REPO_ROOT / "backend" / "evals" / "golden").rglob("*.json"))
        multi = sorted((REPO_ROOT / "backend" / "evals" / "golden_multi_turn").rglob("*.json"))
        bindings = resolve_bindings(
            _DECLARED_BINDINGS,
            repo_root=REPO_ROOT,
            dataset_files=golden + multi,
            code_binding=donor_code,
            allow_dirty=args.allow_dirty,
            ignore_paths=output_exemptions,
        )
    report = build_report(
        reports,
        allow_dirty=args.allow_dirty,
        strict_missing=not args.allow_missing,
        bindings=bindings,
        ignore_paths=output_exemptions,
        deterministic_coverage=deterministic_regression_coverage(),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = args.output.with_suffix(args.output.suffix + ".tmp")
    staging.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    staging.replace(args.output)
    print(f"Wrote {args.output}")

    # Audit our OWN output (Gate A's precedent): a report bound to a non-code
    # commit, or otherwise unbound, must not be read as a verdict.
    self_violations = audit_evidence_file(args.output, repo_root=REPO_ROOT)
    if self_violations:
        print("\nUNBOUND — this report violates docs/EVIDENCE-CONVENTION.md:")
        for violation in self_violations:
            print(f"  ! {violation}")
        print("\nThe report was written but must not be committed as-is.")
        return 1

    for key, rolled in report["rows"].items():
        print(f"  [{key}] {rolled['result']}")
    if report["gate_b_passed"]:
        print("\ngate_b_passed: true")
        return 0
    print("\ngate_b_passed: false — blocked by:")
    for entry in report["blocking"]:
        where = entry["row"] + (f"/{entry['category']}" if entry.get("category") else "")
        print(f"  - {entry['check']} ({where}): {entry['reason']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_OUTPUT",
    "HONEST_GAPS",
    "build_report",
    "code_ancestor_staleness",
    "deterministic_regression_coverage",
    "donor_code_binding",
    "golden_dataset_summary",
    "live_routing_disclosure",
    "main",
    "tag_integrity_violations",
]
