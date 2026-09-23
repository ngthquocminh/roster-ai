"""Gate a fresh live-conversation run against the committed baseline (Story 5.8).

`evals/live_conversations/` answers *how good is it right now*. The committed
baseline at `backend/evals/baselines/live-conversations.json` records what
known-good looked like. This module answers the regression question -- *is it
worse than it was* -- and is the operator-invoked half of AC4: it runs on the
machine that just ran the paid suite and exits non-zero on any tier failure or
refusal. It adds no workflow job, secret or cron entry, because the paid suite
may never run in `ci.yml` (NFR26/AD-16, `docs/CI-SECRETS-CHECKLIST.md`).

Both sides are reporting-builder documents. The baseline's side is read from the
committed file; the new run's side is the document `evals.live_conversations
.reporting.summarize_runs` returns, written through the existing
`evals.live_conversations.evidence.generate` path. The comparator never rebuilds
that rollup: a second copy of the pass-counting rule next to the one that
produced the baseline is how the two would drift.

Three tiers plus a structural check, each reported SEPARATELY so a pass on one
never masks a failure on another, and two refusal conditions. Results use the
Gate A readiness status vocabulary (`passed` / `failed` / `skipped` /
`missing`, the last three non-proving) so a future Gate B assessment consumes
them as rows; a refusal is a distinct outcome from a failure and is recorded as
`outcome: "refused"` with a non-proving `skipped` status.

Failure messages name turns and counts, never transcript text, prompts,
arguments or bodies.

Usage::

    cd backend
    uv run --frozen python scripts/live_conversation_drop_check.py \\
        --report ../evidence/story-5.7/live-conversation-journeys.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.derive_live_conversation_baseline import (  # noqa: E402
    BASELINE_PATH,
    SOURCE_EVIDENCE,
)
from scripts.evidence_binding import REPO_ROOT, dataset_file_digest  # noqa: E402

#: Tier 3's floor, chosen against the measured distribution: Poisson around the
#: baseline's 3 failures puts a drop to <= 82 at ~1.2% per run, versus ~8.4% at
#: a floor of 85. It catches BROAD degradation; a single broken turn is Tier 1's.
#: NOT derived from the baseline file at runtime -- it is a one-time judgement
#: against the CURRENT 87/90 baseline (Decision 5). If a future re-derivation
#: changes `total_passed`/`total_executed`, re-run the Poisson comparison by
#: hand and update this constant; nothing here will flag the staleness.
AGGREGATE_FLOOR = 83

#: Structural: a run that lost a whole scenario is not comparable on turn counts.
REQUIRED_CLEAN_SCENARIOS = ("A", "B", "C")

#: Minimum complete repetitions on both sides -- a budget-truncated run has fewer.
REQUIRED_REPETITIONS = 3

#: Results that prove nothing, matching `scripts.gate_a_readiness._NON_PROVING`.
NON_PROVING = ("failed", "skipped", "missing")


def _result(check_id: str, title: str, status: str, outcome: str, detail: str) -> dict:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "outcome": outcome,
        "detail": detail,
    }


def _passed(check_id: str, title: str, detail: str) -> dict:
    return _result(check_id, title, "passed", "pass", detail)


def _failed(check_id: str, title: str, detail: str) -> dict:
    return _result(check_id, title, "failed", "fail", detail)


def _refused(check_id: str, title: str, detail: str) -> dict:
    # Non-proving on purpose: a refused comparison is not a green one.
    return _result(check_id, title, "skipped", "refused", detail)


# ---------------------------------------------------------------------------
# refusals (AC3)
# ---------------------------------------------------------------------------


def _report_behavioral_digest(report: dict) -> str | None:
    configuration = report.get("measured_configuration") or {}
    return configuration.get("behavioral_digest")


def configuration_refusal(baseline: dict, report: dict) -> dict | None:
    """Refuse when the new run's BEHAVIOURAL configuration differs.

    Compared on `behavioral_digest`, never `configuration_digest`: the latter
    covers the override's comment header and per-token prices, so a gate keyed
    on it would redden when someone edits a chronology comment.
    """
    expected = baseline["configuration"]["behavioral_digest"]
    actual = _report_behavioral_digest(report)
    title = "Behavioural configuration matches the baseline"
    if actual is None:
        return _refused(
            "configuration_match",
            title,
            "the run report records no behavioral_digest, so it cannot be shown to "
            "have run the baseline's configuration",
        )
    if actual != expected:
        return _refused(
            "configuration_match",
            title,
            f"behavioral_digest {actual} does not match the baseline's {expected}; "
            "the run measured a different configuration",
        )
    return None


def document_shape_refusal(report: dict) -> dict | None:
    """Refuse when `report` is not a reporting-builder document.

    The module docstring already warns not to pass the raw `live-matrix.json`
    run report -- only the document `evals.live_conversations.evidence.generate`
    writes carries `turn_pass_rates`. Without this check, that mistake falls
    through `configuration_refusal`'s missing-`behavioral_digest` branch: an
    accurate but confusing diagnosis of the wrong problem.
    """
    if "turn_pass_rates" not in report:
        return _refused(
            "report_shape",
            "The report is a reporting-builder document",
            "the report has no turn_pass_rates; pass the document "
            "evals.live_conversations.evidence.generate writes, not a raw "
            "live-matrix.json run report",
        )
    return None


def _truncation_reasons(document: dict, side: str) -> list[str]:
    """Why `document` is not a complete run, in the suite's OWN vocabulary.

    The truncation signal on this suite is the per-execution `incomplete_reason`
    rolled up into `runs[].complete`, `complete_repetitions` and the closed
    `blocking_reasons` vocabulary -- NOT `stopped_reason`/`spend_measured`,
    which belong to the Story 5.6 multi-turn report and would never fire here.
    """
    reasons: list[str] = []
    blocking = document.get("blocking_reasons")
    if blocking:
        reasons.append(f"{side} blocking_reasons {sorted(blocking)}")
    repetitions = document.get("complete_repetitions")
    if repetitions is None or int(repetitions) < REQUIRED_REPETITIONS:
        reasons.append(
            f"{side} complete_repetitions {repetitions} < {REQUIRED_REPETITIONS}"
        )
    incomplete = sorted(
        str(run.get("run_id"))
        for run in document.get("runs", [])
        if not run.get("complete")
    )
    if incomplete:
        reasons.append(f"{side} has incomplete runs {incomplete}")
    return reasons


def truncation_refusal(baseline: dict, report: dict) -> dict | None:
    """Refuse when EITHER side was truncated (budget exhaustion included)."""
    reasons: list[str] = []
    if int(baseline.get("complete_repetitions", 0)) < REQUIRED_REPETITIONS:
        reasons.append(
            f"baseline complete_repetitions {baseline.get('complete_repetitions')} "
            f"< {REQUIRED_REPETITIONS}"
        )
    reasons.extend(_truncation_reasons(report, "run"))
    if reasons:
        return _refused(
            "run_completeness",
            "Neither side's run was truncated",
            "; ".join(reasons),
        )
    return None


# ---------------------------------------------------------------------------
# tiers (AC2)
# ---------------------------------------------------------------------------


def tier_1(baseline: dict, report: dict) -> dict:
    """Any baseline full-marks turn that now scores zero FAILS, by name.

    Turns not at full marks in the baseline (`B:5`, `B:8`, `C:3` at 2/3) are
    EXEMPT from the score-collapse check: a 2/3 turn reaching 0/3 is ~3.6%
    likely by chance, which would make a hard block a false-alarm generator.
    They are watched by Tier 3 only for a SCORE drop.

    A turn vanishing entirely from the report is a different failure mode --
    structural, not a score change -- and Decision 4 never exempted it: an
    exempt turn that simply never appears would otherwise be invisible to
    every tier as long as the aggregate stayed above Tier 3's floor. So the
    `missing` check below covers ALL baseline turns, exempt or not; only the
    score-collapse check stays scoped to the full-marks-qualifying set.
    """
    rates = report.get("turn_pass_rates") or {}
    qualifying = [
        turn
        for turn, counts in baseline["turn_pass_rates"].items()
        if counts["executed"] > 0 and counts["passed"] == counts["executed"]
    ]
    dropped = sorted(
        turn
        for turn in qualifying
        if int((rates.get(turn) or {}).get("passed", 0)) == 0
    )
    missing = sorted(turn for turn in baseline["turn_pass_rates"] if turn not in rates)
    title = f"Tier 1: no baseline full-marks turn collapsed ({len(qualifying)} watched)"
    if missing:
        return _failed(
            "tier_1_full_marks_collapse",
            title,
            f"the run does not report {len(missing)} baseline turn(s): {missing}",
        )
    if dropped:
        return _failed(
            "tier_1_full_marks_collapse",
            title,
            f"{len(dropped)} turn(s) at full marks in the baseline now pass 0 "
            f"executions: {dropped}",
        )
    return _passed(
        "tier_1_full_marks_collapse",
        title,
        f"all {len(qualifying)} watched turns still pass at least one execution",
    )


def tier_2(report: dict) -> dict:
    """Any never-accept occurrence FAILS on a single instance.

    The judgement is already made by the existing fact/effect layer, which
    `reporting.summarize_runs` records as `false_claims`: a wrong value, unit,
    entity or version, a missing or unauthorized effect, or a false success
    claim. This check READS that verdict and never re-derives it -- re-deriving
    a metric rule from adapter code is exactly what `docs/DOMAIN-MODEL.md`
    forbids.
    """
    claims = report.get("false_claims") or []
    title = "Tier 2: no never-accept occurrence"
    if claims:
        # Turn ids and failure categories only -- never transcript text.
        named = sorted(
            f"{claim.get('turn')}[{','.join(claim.get('failures') or ())}]"
            for claim in claims
        )
        return _failed(
            "tier_2_never_accept",
            title,
            f"{len(claims)} never-accept occurrence(s): {named}",
        )
    return _passed("tier_2_never_accept", title, "no false claim or effect failure")


def tier_3(report: dict) -> dict:
    """The aggregate FAILS below the floor -- broad degradation, not one turn."""
    rates = report.get("turn_pass_rates") or {}
    total_passed = sum(int(counts.get("passed", 0)) for counts in rates.values())
    total_executed = sum(int(counts.get("executed", 0)) for counts in rates.values())
    title = f"Tier 3: aggregate at or above {AGGREGATE_FLOOR} passed turns"
    detail = f"{total_passed}/{total_executed} turns passed"
    if total_passed < AGGREGATE_FLOOR:
        return _failed(
            "tier_3_aggregate",
            title,
            f"{detail}, below the floor of {AGGREGATE_FLOOR}",
        )
    return _passed("tier_3_aggregate", title, detail)


def structural_check(report: dict) -> dict:
    """`clean_scenarios` must still contain A, B and C."""
    clean = set(report.get("clean_scenarios") or ())
    missing = sorted(set(REQUIRED_CLEAN_SCENARIOS) - clean)
    title = "Structural: every scenario still has a clean run"
    if missing:
        return _failed(
            "structural_clean_scenarios",
            title,
            f"no clean run for scenario(s) {missing}",
        )
    return _passed(
        "structural_clean_scenarios", title, f"clean scenarios {sorted(clean)}"
    )


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def compare(baseline: dict, report: dict) -> dict:
    """Every tier's verdict, reported separately, plus any refusal."""
    refusals = [
        refusal
        for refusal in (
            document_shape_refusal(report),
            configuration_refusal(baseline, report),
            truncation_refusal(baseline, report),
        )
        if refusal is not None
    ]
    if refusals:
        # A refused comparison yields no tier verdict at all: reporting a tier
        # as `passed` over a configuration that was never shown to match would
        # be the masking AC2 forbids.
        skipped = [
            _refused(
                check_id,
                title,
                "not evaluated: the comparison was refused",
            )
            for check_id, title in (
                ("tier_1_full_marks_collapse", "Tier 1"),
                ("tier_2_never_accept", "Tier 2"),
                ("tier_3_aggregate", "Tier 3"),
                ("structural_clean_scenarios", "Structural"),
            )
        ]
        checks = refusals + skipped
    else:
        checks = [
            tier_1(baseline, report),
            tier_2(report),
            tier_3(report),
            structural_check(report),
        ]
    return {
        "schema_version": "1",
        "baseline_source_evidence": baseline["source_evidence_path"],
        "baseline_measured_at_commit": baseline["measured_at_commit"],
        "refused": bool(refusals),
        "refusal_reasons": [refusal["id"] for refusal in refusals],
        "checks": checks,
        "passed": not refusals
        and all(check["status"] not in NON_PROVING for check in checks),
    }


def baseline_matches_source(
    baseline: dict, source: Path = SOURCE_EVIDENCE
) -> tuple[bool, str]:
    """The free half of AC4: does the committed baseline still match its source?

    Runs in the DEFAULT pytest suite on every CI run, which is what makes
    baseline tampering or source drift visible with no credential and no spend.
    Nothing existing would notice: `audit_evidence_drift` collects path strings
    only from values under `contract`/`checklist`/`path`/`source_path` keys, so
    it never walks this relationship.

    `source` defaults to the one baseline that exists today, but a caller
    checking a DIFFERENT baseline (e.g. `--baseline` pointed elsewhere) must
    pass that baseline's own `source_evidence_path` explicitly -- the default
    is never right for someone else's baseline. `main()` always does this.
    """
    if not Path(source).is_file():
        return False, f"the baseline's source evidence {source} does not exist"
    actual = dataset_file_digest(source)
    expected = baseline["source_evidence_sha256"]
    if actual != expected:
        return False, (
            f"the committed baseline records source_evidence_sha256 {expected} but "
            f"{baseline['source_evidence_path']} now digests to {actual}; re-derive "
            "the baseline with scripts/derive_live_conversation_baseline.py"
        )
    return True, f"baseline matches {baseline['source_evidence_path']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="a reporting-builder document (evidence/**.json), NOT a raw live-matrix run report",
    )
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = compare(baseline, report)

    # Always the LOADED baseline's own declared source, never the module
    # default: a `--baseline` pointed at a different file must be checked
    # against what IT claims, not against today's one true baseline's source.
    consistent, detail = baseline_matches_source(
        baseline, REPO_ROOT / baseline["source_evidence_path"]
    )
    result["checks"].insert(
        0,
        _passed("baseline_source_consistency", "Baseline matches its source", detail)
        if consistent
        else _failed(
            "baseline_source_consistency", "Baseline matches its source", detail
        ),
    )
    result["passed"] = result["passed"] and consistent

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    for check in result["checks"]:
        print(f"{check['status']:>8}  {check['id']}: {check['detail']}", file=sys.stderr)
    # A check that can say no and still exit 0 is not a gate.
    return 0 if result["passed"] else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
