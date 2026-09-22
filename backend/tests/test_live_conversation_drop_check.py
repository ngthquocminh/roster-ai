"""The live-conversation regression gate (Story 5.8).

Every assertion here runs offline with no network access and no spend, using the
COMMITTED Story 5.7 evidence as its fixture. The baseline is read from the
committed file and never recomputed from the report under test: a check that
compares something with itself cannot fail.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evals.live_conversations.configuration import (
    DEFAULT_OVERRIDE_FILE,
    behavioral_digest,
    behavioral_environment,
    measured_configuration,
)
from scripts.derive_live_conversation_baseline import (
    BASELINE_PATH,
    SOURCE_EVIDENCE,
    derive_baseline,
)
from scripts.evidence_binding import REPO_ROOT, dataset_file_digest
from scripts.live_conversation_drop_check import (
    AGGREGATE_FLOOR,
    baseline_matches_source,
    compare,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed_evidence() -> dict:
    return json.loads(SOURCE_EVIDENCE.read_text(encoding="utf-8"))


@pytest.fixture
def green_report(committed_evidence: dict, baseline: dict) -> dict:
    """The committed measurement as a run a fresh suite would produce.

    The only edit is the `behavioral_digest` the 5.7 evidence predates; a run
    under this story's code records it itself.
    """
    report = copy.deepcopy(committed_evidence)
    report["measured_configuration"]["behavioral_digest"] = baseline["configuration"][
        "behavioral_digest"
    ]
    return report


# ---------------------------------------------------------------------------
# AC1 -- the committed baseline
# ---------------------------------------------------------------------------


def test_baseline_is_not_in_the_evidence_tree():
    """Decision 1's whole mechanism: membership is decided by LOCATION alone."""
    assert BASELINE_PATH.is_file()
    assert (REPO_ROOT / "evidence") not in BASELINE_PATH.parents
    assert BASELINE_PATH.parent == BACKEND_ROOT / "evals" / "baselines"


def test_committed_baseline_is_exactly_what_the_script_derives(baseline: dict):
    """AC1's "derived by a committed script, never hand-typed"."""
    assert derive_baseline() == baseline


def test_baseline_records_the_measurement_it_projects(baseline: dict):
    assert baseline["source_evidence_path"] == (
        "evidence/story-5.7/live-conversation-journeys.json"
    )
    assert baseline["measured_at_commit"]
    assert baseline["total_passed"] == 87
    assert baseline["total_executed"] == 90
    assert len(baseline["turn_pass_rates"]) == 30
    configuration = baseline["configuration"]
    assert set(configuration) == {
        "agent_model",
        "judge_model",
        "reasoning_effort",
        "configuration_digest",
        "behavioral_digest",
    }


def test_baseline_source_digest_is_line_ending_normalised(baseline: dict):
    """The Story 1.9/1.10/1.11 CRLF defect, guarded in a new place.

    `core.autocrlf` leaves the working tree CRLF on Windows while the committed
    blob is LF, so a raw-byte digest would give one answer here and another on
    the Linux CI runner.
    """
    import hashlib

    raw = SOURCE_EVIDENCE.read_bytes()
    normalised = dataset_file_digest(SOURCE_EVIDENCE)
    assert baseline["source_evidence_sha256"] == normalised
    assert (
        hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == normalised
    ), "the normalising routine must agree with an LF-normalised hash of the bytes"


# ---------------------------------------------------------------------------
# AC4 (free half) -- the default-suite consistency check
# ---------------------------------------------------------------------------


def test_committed_baseline_still_matches_the_committed_evidence(baseline: dict):
    """Runs in the DEFAULT suite on every CI run -- no credential, no spend."""
    consistent, detail = baseline_matches_source(baseline)
    assert consistent, detail


def test_consistency_check_names_the_drift_when_the_source_moves(
    baseline: dict, tmp_path: Path, committed_evidence: dict
):
    moved = tmp_path / "live-conversation-journeys.json"
    drifted = copy.deepcopy(committed_evidence)
    drifted["turn_pass_rates"]["A:1"]["passed"] = 0
    moved.write_text(json.dumps(drifted), encoding="utf-8")
    consistent, detail = baseline_matches_source(baseline, moved)
    assert not consistent
    assert "re-derive the baseline" in detail


def test_consistency_check_fails_when_the_source_is_absent(
    baseline: dict, tmp_path: Path
):
    consistent, detail = baseline_matches_source(baseline, tmp_path / "gone.json")
    assert not consistent
    assert "does not exist" in detail


# ---------------------------------------------------------------------------
# AC2 -- the three tiers and the structural check
# ---------------------------------------------------------------------------


def test_the_baseline_run_compares_green_against_itself(
    baseline: dict, green_report: dict
):
    result = compare(baseline, green_report)
    assert result["passed"], result
    assert result["refused"] is False
    assert [check["status"] for check in result["checks"]] == ["passed"] * 4


def test_tier_1_names_a_collapsed_full_marks_turn(baseline: dict, green_report: dict):
    green_report["turn_pass_rates"]["A:1"] = {"executed": 3, "passed": 0}
    result = compare(baseline, green_report)
    tier1 = _check(result, "tier_1_full_marks_collapse")
    assert tier1["status"] == "failed"
    assert "'A:1'" in tier1["detail"]
    assert result["passed"] is False


def test_tier_1_exempts_the_three_turns_the_baseline_never_scored_full(
    baseline: dict, green_report: dict
):
    """`B:5`, `B:8` and `C:3` sit at 2/3; Tier 3 watches them, Tier 1 does not."""
    partial = [
        turn
        for turn, counts in baseline["turn_pass_rates"].items()
        if counts["passed"] != counts["executed"]
    ]
    assert sorted(partial) == ["B:5", "B:8", "C:3"]
    for turn in partial:
        green_report["turn_pass_rates"][turn] = {"executed": 3, "passed": 0}
    result = compare(baseline, green_report)
    assert _check(result, "tier_1_full_marks_collapse")["status"] == "passed"
    # 87 - 6 = 81, which is below the floor: Tier 3 is what catches them.
    assert _check(result, "tier_3_aggregate")["status"] == "failed"


def test_tier_1_fails_when_a_watched_turn_is_missing_from_the_run(
    baseline: dict, green_report: dict
):
    green_report["turn_pass_rates"].pop("A:1")
    tier1 = _check(compare(baseline, green_report), "tier_1_full_marks_collapse")
    assert tier1["status"] == "failed"
    assert "does not report" in tier1["detail"]


def test_tier_2_fails_on_a_single_never_accept_occurrence(
    baseline: dict, green_report: dict
):
    green_report["false_claims"] = [
        {"run_id": "r1", "turn": "C:2", "failures": ["wrong_value"]}
    ]
    tier2 = _check(compare(baseline, green_report), "tier_2_never_accept")
    assert tier2["status"] == "failed"
    assert "C:2[wrong_value]" in tier2["detail"]


def test_tier_2_failure_names_turns_and_categories_only(
    baseline: dict, green_report: dict
):
    """Redaction discipline survives the failure path."""
    green_report["false_claims"] = [
        {
            "run_id": "r1",
            "turn": "C:2",
            "failures": ["wrong_value"],
            "rendered": "the agent said 412 hours",
            "prompt": "do not leak me",
        }
    ]
    tier2 = _check(compare(baseline, green_report), "tier_2_never_accept")
    assert "412" not in tier2["detail"]
    assert "do not leak me" not in tier2["detail"]


def test_tier_3_fails_one_turn_below_the_floor(baseline: dict, green_report: dict):
    # 87 passed; drop 5 whole turns' worth of passes to reach 82.
    for turn in ["A:1", "A:2"]:
        green_report["turn_pass_rates"][turn] = {"executed": 3, "passed": 1}
    green_report["turn_pass_rates"]["A:3"] = {"executed": 3, "passed": 2}
    result = compare(baseline, green_report)
    tier3 = _check(result, "tier_3_aggregate")
    assert tier3["status"] == "failed"
    assert f"{AGGREGATE_FLOOR - 1}/90" in tier3["detail"]


def test_tier_3_passes_exactly_at_the_floor(baseline: dict, green_report: dict):
    for turn in ["A:1", "A:2"]:
        green_report["turn_pass_rates"][turn] = {"executed": 3, "passed": 1}
    tier3 = _check(compare(baseline, green_report), "tier_3_aggregate")
    assert tier3["status"] == "passed"
    assert f"{AGGREGATE_FLOOR}/90" in tier3["detail"]


def test_structural_check_fails_when_a_scenario_lost_its_clean_run(
    baseline: dict, green_report: dict
):
    green_report["clean_scenarios"] = ["A", "C"]
    structural = _check(compare(baseline, green_report), "structural_clean_scenarios")
    assert structural["status"] == "failed"
    assert "'B'" in structural["detail"]


def test_a_pass_on_one_tier_never_masks_a_failure_on_another(
    baseline: dict, green_report: dict
):
    green_report["false_claims"] = [
        {"run_id": "r1", "turn": "C:2", "failures": ["unauthorized_effect"]}
    ]
    result = compare(baseline, green_report)
    statuses = {check["id"]: check["status"] for check in result["checks"]}
    assert statuses["tier_2_never_accept"] == "failed"
    assert statuses["tier_1_full_marks_collapse"] == "passed"
    assert statuses["tier_3_aggregate"] == "passed"
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# AC3 -- refusals, distinct from failures
# ---------------------------------------------------------------------------


def test_a_changed_behavioural_configuration_is_refused_not_compared(
    baseline: dict, green_report: dict
):
    green_report["measured_configuration"]["behavioral_digest"] = "0" * 64
    result = compare(baseline, green_report)
    assert result["refused"] is True
    assert result["refusal_reasons"] == ["configuration_match"]
    refusal = _check(result, "configuration_match")
    assert refusal["outcome"] == "refused"
    assert refusal["status"] == "skipped"
    assert "different configuration" in refusal["detail"]
    # No tier may report a verdict over a configuration never shown to match.
    for check_id in ("tier_1_full_marks_collapse", "tier_3_aggregate"):
        assert _check(result, check_id)["outcome"] == "refused"
    assert result["passed"] is False


def test_a_report_without_a_behavioural_digest_is_refused(
    baseline: dict, green_report: dict
):
    green_report["measured_configuration"].pop("behavioral_digest")
    result = compare(baseline, green_report)
    assert result["refused"] is True
    assert "records no behavioral_digest" in _check(result, "configuration_match")[
        "detail"
    ]


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (
            lambda report: report.update({"blocking_reasons": ["unaccepted_turn_failure"]}),
            "blocking_reasons",
        ),
        (
            lambda report: report.update({"complete_repetitions": 2}),
            "complete_repetitions 2 < 3",
        ),
        (
            lambda report: report["runs"].append(
                {"run_id": "truncated", "repetition": 4, "complete": False}
            ),
            "incomplete runs",
        ),
    ],
)
def test_a_truncated_run_is_refused_using_the_suites_own_vocabulary(
    baseline: dict, green_report: dict, mutate, fragment: str
):
    """Budget exhaustion surfaces here, via `incomplete_reason`'s rollups.

    NOT via `stopped_reason`/`spend_measured`: those are the Story 5.6
    multi-turn report's fields and a check naming them would silently never fire.
    """
    mutate(green_report)
    result = compare(baseline, green_report)
    assert result["refused"] is True
    assert "run_completeness" in result["refusal_reasons"]
    assert fragment in _check(result, "run_completeness")["detail"]


def test_refusal_is_a_distinct_outcome_from_failure(baseline: dict, green_report: dict):
    green_report["turn_pass_rates"]["A:1"] = {"executed": 3, "passed": 0}
    failure = compare(baseline, green_report)
    assert failure["refused"] is False
    assert _check(failure, "tier_1_full_marks_collapse")["outcome"] == "fail"

    green_report["complete_repetitions"] = 1
    refused = compare(baseline, green_report)
    assert refused["refused"] is True
    assert _check(refused, "run_completeness")["outcome"] == "refused"


# ---------------------------------------------------------------------------
# AC4 -- Gate-B-shaped result, exits non-zero
# ---------------------------------------------------------------------------


def test_every_check_uses_the_gate_a_status_vocabulary(
    baseline: dict, green_report: dict
):
    from scripts.gate_a_readiness import _NON_PROVING

    from scripts.live_conversation_drop_check import NON_PROVING

    assert NON_PROVING == _NON_PROVING
    allowed = {"passed", *_NON_PROVING}
    for report in (green_report, {**green_report, "complete_repetitions": 1}):
        for check in compare(baseline, report)["checks"]:
            assert check["status"] in allowed
            assert set(check) == {"id", "title", "status", "outcome", "detail"}


def _run_cli(report_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(BACKEND_ROOT / "scripts" / "live_conversation_drop_check.py"),
            "--report",
            str(report_path),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )


def test_the_drop_check_exits_zero_on_a_green_run(green_report: dict, tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(green_report), encoding="utf-8")
    completed = _run_cli(path)
    assert completed.returncode == 0, completed.stderr


def test_the_drop_check_exits_non_zero_on_a_tier_failure(
    green_report: dict, tmp_path: Path
):
    green_report["turn_pass_rates"]["A:1"] = {"executed": 3, "passed": 0}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(green_report), encoding="utf-8")
    completed = _run_cli(path)
    assert completed.returncode == 1
    assert "tier_1_full_marks_collapse" in completed.stderr


def test_the_drop_check_exits_non_zero_on_a_refusal(green_report: dict, tmp_path: Path):
    green_report["blocking_reasons"] = ["three_complete_repetitions_missing"]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(green_report), encoding="utf-8")
    completed = _run_cli(path)
    assert completed.returncode == 1
    assert "run_completeness" in completed.stderr


def test_the_drop_check_carries_the_consistency_row(green_report: dict, tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(green_report), encoding="utf-8")
    out = tmp_path / "result.json"
    assert _run_cli(path, "--output", str(out)).returncode == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["checks"][0]["id"] == "baseline_source_consistency"
    assert result["checks"][0]["status"] == "passed"


def test_a_drifted_baseline_makes_the_drop_check_exit_non_zero(
    baseline: dict, green_report: dict, tmp_path: Path
):
    """A green comparison must not survive a baseline that no longer matches.

    Guards the coupling, not just the row: tampering with the committed baseline
    is itself a gate failure, however well the new run scored.
    """
    path = tmp_path / "report.json"
    path.write_text(json.dumps(green_report), encoding="utf-8")
    tampered = tmp_path / "baseline.json"
    tampered.write_text(
        json.dumps({**baseline, "source_evidence_sha256": "0" * 64}), encoding="utf-8"
    )
    completed = _run_cli(path, "--baseline", str(tampered))
    assert completed.returncode == 1
    assert "baseline_source_consistency" in completed.stderr


# ---------------------------------------------------------------------------
# AC3/Decision 7 -- behavioral_digest
# ---------------------------------------------------------------------------


def test_behavioral_digest_excludes_only_the_price_keys():
    environment = behavioral_environment(DEFAULT_OVERRIDE_FILE)
    assert set(environment) == {"api", "worker"}
    for service in environment.values():
        assert not [key for key in service if key.endswith("_USD_PER_MTOK")]
        assert "AGENT_RUNTIME_REASONING_EFFORT" in service
        assert "AGENT_RUNTIME_TOOL_CALLS_LIMIT" in service


def test_behavioral_digest_is_stable_across_a_price_or_comment_edit(tmp_path: Path):
    """A gate that reddens when someone edits a chronology comment is unusable."""
    original = DEFAULT_OVERRIDE_FILE.read_text(encoding="utf-8")
    edited = tmp_path / "compose.override.yml"
    edited.write_text(
        "# an added chronology note\n"
        + original.replace("'1.20'", "'2.40'"),
        encoding="utf-8",
    )
    kwargs = dict(
        model="openrouter:openai/gpt-5.6-luna",
        judge_model="openrouter:google/gemini-2.5-flash",
        reasoning_effort="low",
    )
    assert behavioral_digest(override_file=edited, **kwargs) == behavioral_digest(
        override_file=DEFAULT_OVERRIDE_FILE, **kwargs
    )


def test_behavioral_digest_moves_on_a_behavioural_edit(tmp_path: Path):
    edited = tmp_path / "compose.override.yml"
    edited.write_text(
        DEFAULT_OVERRIDE_FILE.read_text(encoding="utf-8").replace(
            "AGENT_RUNTIME_TOOL_CALLS_LIMIT: '12'",
            "AGENT_RUNTIME_TOOL_CALLS_LIMIT: '40'",
        ),
        encoding="utf-8",
    )
    kwargs = dict(
        model="openrouter:openai/gpt-5.6-luna",
        judge_model="openrouter:google/gemini-2.5-flash",
        reasoning_effort="low",
    )
    assert behavioral_digest(override_file=edited, **kwargs) != behavioral_digest(
        override_file=DEFAULT_OVERRIDE_FILE, **kwargs
    )


def test_a_newly_added_environment_key_is_included_by_default(tmp_path: Path):
    """The rule is an EXCLUSION of price keys, so a new key fails closed."""
    edited = tmp_path / "compose.override.yml"
    edited.write_text(
        DEFAULT_OVERRIDE_FILE.read_text(encoding="utf-8").replace(
            "      DEMONSTRATION_ENABLED: ${DEMONSTRATION_ENABLED:-false}",
            "      DEMONSTRATION_ENABLED: ${DEMONSTRATION_ENABLED:-false}\n"
            "      AGENT_RUNTIME_BRAND_NEW_KNOB: 'on'",
        ),
        encoding="utf-8",
    )
    kwargs = dict(
        model="openrouter:openai/gpt-5.6-luna",
        judge_model="openrouter:google/gemini-2.5-flash",
        reasoning_effort="low",
    )
    assert behavioral_digest(override_file=edited, **kwargs) != behavioral_digest(
        override_file=DEFAULT_OVERRIDE_FILE, **kwargs
    )


def test_adding_behavioral_digest_left_configuration_digest_untouched(
    committed_evidence: dict,
):
    """AC7: `configuration_digest` and every committed evidence file keep values."""
    recorded = committed_evidence["measured_configuration"]
    fresh = measured_configuration(
        model=recorded["agent"]["model"],
        judge_model=recorded["judge"]["model"],
        reasoning_effort=recorded["reasoning_effort"],
        override_file=DEFAULT_OVERRIDE_FILE,
    )
    assert fresh["configuration_digest"] == recorded["configuration_digest"]
    assert fresh["override_sha256"] == recorded["override_sha256"]
    assert "behavioral_digest" not in recorded
    assert fresh["behavioral_digest"]


def _check(result: dict, check_id: str) -> dict:
    (found,) = [check for check in result["checks"] if check["id"] == check_id]
    return found
