"""Declarative registry of the checks that decide Gate B (Story 5.13).

Mirrors `gate_a_checks.py`: a registry only, with no I/O. `gate_b_readiness.py`
reads it, evaluates every check and writes `evidence/epic-5/release-gate-report.json`.

The seven rows are the Gate B rows of the Release Gate table in
`_bmad-output/planning-artifacts/epics.md`, which is the only place their
thresholds live. This module registers what proves each row; it does not
restate or redefine a threshold (Story 5.13 F1). The dataset floors below are
the one exception, and only because AC3 amends that row through D4–D6.

Three kinds of check, exactly one source each (D1):

* **tests** — JUnit-backed. A declared file must appear in the XML with every
  case passed; skipped is not passed (Gate A's rule, reused through
  `junit_ingest.py`). `test_cases` narrows a check to named test functions,
  which is how the NFR35 row reads exactly its four threshold tests (D7).
* **evidence** — a version-bound JSON file whose declared `verdict_key` must
  hold one of `verdict_pass_values`. Nothing else in the file counts as the
  verdict (D2; F3: the live-conversation file has no top-level `passed`). The
  file must also pass `audit_evidence_file` and its `freshness` rule (D12).
  `exception_value`, where set, is the value a live generator writes when a
  complete, unexpired release exception waived a blocked verdict (AC5).
* **computed** — a named in-process check `gate_b_readiness.py` implements
  (dataset floors, tag integrity, live-conversation freshness).

Where Gate B needs a check Gate A already holds, it is imported from
`gate_a_checks.GATE_A_CHECKS` by name rather than re-declared (D1, D13).

Provenance of the Blocking-regressions files (D13): transcribed from each
story's own `### File List`, never guessed. Category assignment is a judgement
the registry records in each check's description; whether a registered file is
topically relevant is not machine-checked (the same open weakness Gate A's
ledger records for its `authenticated_readonly_scenario_data` bucket).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from scripts.gate_a_checks import GATE_A_CHECKS, GateACheck

Runner = Literal["pytest", "pytest-postgres", "vitest", "playwright"]
Freshness = Literal["code_ancestor"]

#: Story 5.13 D4 — the golden-dataset ratchet floor, replacing NFR28's 50.
#: Reason (recorded verbatim in prd.md §7, requirements-inventory.md NFR28 and
#: epics.md): the 50 assumed golden-case contributions from Stories 3.10–3.12
#: and 4.5, and those stories deliberately added none, because their invariants
#: are not model-reachable and are proven as PostgreSQL proof nodes (4.5
#: Decision 11). Multi-turn cases are versioned and graded by the same
#: evaluators, so counting them puts them under the ratchet instead of leaving
#: them ungated.
#:
#: Counts single-turn (`evals/golden/`) plus multi-turn (`evals/golden_multi_turn/`)
#: cases at the Gate B commit: 39 + 6 = 45. It may rise as cases are added; it
#: may fall only in a diff that also states the reviewed reason here.
GOLDEN_CASE_FLOOR = 45

#: D5 — at least four single-turn cases per capability the release allows.
PER_CAPABILITY_FLOOR = 4

#: D6 — at least ten single-turn consequential/prohibited cases on release-
#: allowed capabilities, counted by case tag with tag integrity enforced.
PROTECTED_CASE_FLOOR = 10
PROTECTED_RISK_CLASSES = ("consequential", "prohibited")

#: D12 — code paths whose change between a live measurement and the Gate B
#: commit makes that measurement stale.
LIVE_FRESHNESS_PATHS = (
    "backend/agent/",
    "backend/application/capabilities/",
    "backend/evals/golden/",
    "backend/evals/golden_multi_turn/",
)


@dataclass(frozen=True)
class GateBRow:
    """One Gate B row of the Release Gate table."""

    key: str
    title: str


GATE_B_ROWS: tuple[GateBRow, ...] = (
    GateBRow("deterministic_and_live_readiness", "Deterministic-first CI and live AI readiness"),
    GateBRow("live_conversation_journeys", "Required live conversation journeys"),
    GateBRow("report_version_binding", "Report version binding"),
    GateBRow("golden_dataset_size", "Golden dataset size"),
    GateBRow("tool_routing", "Tool routing"),
    GateBRow("nfr35_internal_thresholds", "NFR35 internal thresholds"),
    GateBRow("blocking_regressions", "Blocking regressions"),
)

#: The categories the Blocking-regressions row names, verbatim, in order.
BLOCKING_REGRESSION_CATEGORIES: tuple[str, ...] = (
    "authorization",
    "approval",
    "isolation",
    "hard_constraints",
    "grounding",
    "idempotency",
    "authoritative_audit",
    "viewer_parity",
    "recovery",
    "accessibility",
)

#: The in-process checks `gate_b_readiness.py` implements, by name.
COMPUTED_CHECKS: tuple[str, ...] = (
    "golden_case_floor",
    "per_capability_floor",
    "protected_floor_and_tag_integrity",
    "live_conversation_inventory_fresh",
    "live_conversation_configuration_fresh",
)


@dataclass(frozen=True)
class GateBCheck:
    """One contributing check, with exactly one proving source."""

    check: str
    row: str
    story: str
    description: str
    #: Blocking-regressions only: which named category this check proves.
    category: str | None = None
    test_files: tuple[str, ...] = ()
    #: `(repo-relative file, test function name)` pairs. When set, only these
    #: cases are read; each must be present and passed (parametrized ids too).
    test_cases: tuple[tuple[str, str], ...] = ()
    runner: Runner | None = None
    required_projects: tuple[str, ...] = ()
    evidence_path: str | None = None
    verdict_key: str | None = None
    verdict_pass_values: tuple[object, ...] = ()
    exception_value: str | None = None
    freshness: Freshness | None = None
    computed: str | None = None
    #: The Gate A check this one was imported from, when it was.
    gate_a_check: str | None = None

    def __post_init__(self) -> None:
        sources = [
            bool(self.test_files or self.test_cases),
            bool(self.evidence_path),
            bool(self.computed),
        ]
        if sum(sources) != 1:
            raise ValueError(
                f"check {self.check!r} must declare exactly one source: tests, "
                "evidence, or computed"
            )
        if self.test_files and self.test_cases:
            raise ValueError(
                f"check {self.check!r} declares both test_files and test_cases; "
                "a whole-file check would mask which named cases it claims"
            )
        if (self.test_files or self.test_cases) and self.runner is None:
            raise ValueError(f"check {self.check!r} declares tests but no runner")
        if self.evidence_path and (self.verdict_key is None or not self.verdict_pass_values):
            raise ValueError(
                f"check {self.check!r} reads evidence but declares no verdict key "
                "and pass value; a stored file is not a verdict on its own (D2)"
            )
        if self.exception_value is not None and self.exception_value in self.verdict_pass_values:
            raise ValueError(
                f"check {self.check!r}: the exception value cannot also be a pass value"
            )
        if self.freshness and not self.evidence_path:
            raise ValueError(f"check {self.check!r}: freshness applies to evidence only")
        if self.required_projects and self.runner != "playwright":
            raise ValueError(
                f"check {self.check!r} declares required_projects but its runner "
                "is not playwright"
            )

    @property
    def source_kind(self) -> str:
        if self.computed:
            return "computed"
        if self.evidence_path:
            return "evidence"
        return "tests"


def _gate_a(name: str) -> GateACheck:
    for check in GATE_A_CHECKS:
        if check.check == name:
            return check
    raise KeyError(f"Gate A has no check named {name!r}")


def from_gate_a(name: str, *, row: str, category: str | None = None) -> GateBCheck:
    """A Gate B check that reuses a Gate A check's proof by import (D1, D13).

    An evidence-backed Gate A check reads that file's `passed`, which is the
    verdict key those files were generated with; the readiness module evaluates
    it through Gate A's own `_evidence_result`, so its manual-gate rule holds.
    """
    source = _gate_a(name)
    common = dict(
        check=f"gate_a.{source.check}",
        row=row,
        story=source.story,
        description=source.description,
        category=category,
        gate_a_check=source.check,
    )
    if source.evidence_path:
        return GateBCheck(
            **common,
            evidence_path=source.evidence_path,
            verdict_key="passed",
            verdict_pass_values=(True,),
        )
    return GateBCheck(
        **common,
        test_files=source.test_files,
        runner=source.runner,
        required_projects=source.required_projects,
    )


_NFR35_FILE = "backend/tests/test_postgres_integration.py"

GATE_B_CHECKS: tuple[GateBCheck, ...] = (
    # ------------------------------------------- Deterministic-first CI and live AI readiness
    GateBCheck(
        check="deterministic_evaluation_harness",
        row="deterministic_and_live_readiness",
        story="2.2",
        description=(
            "The authoritative deterministic suite: every golden case on the "
            "deterministic double, the NFR28 per-capability floor test, and the "
            "multi-turn history suite (Stories 2.2, 5.5, 5.6)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_evaluation_harness.py",
            "backend/tests/test_capability_conformance.py",
        ),
    ),
    GateBCheck(
        check="live_multi_turn_release_configuration",
        row="deterministic_and_live_readiness",
        story="5.13",
        description=(
            "Every release-eligible live multi-turn case passes in each of three "
            "recorded runs on the pinned provider/model and budget, spend "
            "measured (D3)."
        ),
        evidence_path="evidence/story-5.13/live-multi-turn-evaluation.json",
        verdict_key="live_multi_turn",
        verdict_pass_values=("passed",),
        exception_value="excepted",
        freshness="code_ancestor",
    ),
    GateBCheck(
        check="live_evaluation_machinery",
        row="deterministic_and_live_readiness",
        story="5.13",
        description=(
            "The live generators' own fail-closed guards, run keyless in CI: a "
            "live pass is held to the same rule the recorded evidence was (D2)."
        ),
        runner="pytest",
        test_files=("backend/tests/test_live_golden_routing.py",),
    ),
    # ------------------------------------------------ Required live conversation journeys
    GateBCheck(
        check="live_conversation_journeys_evidence",
        row="live_conversation_journeys",
        story="5.12",
        description=(
            "The recorded live-conversation verdict. AD-16: no release exception "
            "marks this verdict passed, so no exception value is accepted."
        ),
        evidence_path="evidence/story-5.12/live-conversation-journeys.json",
        verdict_key="live_conversation_journeys",
        verdict_pass_values=("passed",),
    ),
    GateBCheck(
        check="live_conversation_inventory_fresh",
        row="live_conversation_journeys",
        story="5.13",
        description=(
            "AD-16 / D12: the evidence's inventory_digest equals the current "
            "capability_inventory() digest."
        ),
        computed="live_conversation_inventory_fresh",
    ),
    GateBCheck(
        check="live_conversation_configuration_fresh",
        row="live_conversation_journeys",
        story="5.13",
        description=(
            "D12: the evidence's measured behavioral_digest equals the committed "
            "baseline's configuration.behavioral_digest."
        ),
        computed="live_conversation_configuration_fresh",
    ),
    GateBCheck(
        check="live_conversation_machinery",
        row="live_conversation_journeys",
        story="5.12",
        description=(
            "The suite's reporting, inventory, case and drop-check logic, keyless "
            "(Stories 5.7, 5.12 File Lists)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_live_conversation_reporting.py",
            "backend/tests/test_live_conversation_inventory.py",
            "backend/tests/test_live_conversation_cases.py",
            "backend/tests/test_live_conversation_drop_check.py",
        ),
    ),
    # ------------------------------------------------------------ Report version binding
    from_gate_a("evidence_convention_and_gate_machinery", row="report_version_binding"),
    GateBCheck(
        check="gate_b_machinery",
        row="report_version_binding",
        story="5.13",
        description=(
            "This registry and its readiness generator, held to the gate for the "
            "reason Gate A's are: broken plumbing must block, not vanish."
        ),
        runner="pytest",
        test_files=("backend/tests/test_gate_b_readiness.py",),
    ),
    GateBCheck(
        check="local_image_binding",
        row="report_version_binding",
        story="5.3",
        description=(
            "The locally built image digest that satisfies every report's image "
            "binding (Story 5.3 File List)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/architecture/test_local_composition.py",
            "backend/tests/test_bootstrap_local.py",
        ),
    ),
    # ---------------------------------------------------------------- Golden dataset size
    GateBCheck(
        check="golden_case_floor",
        row="golden_dataset_size",
        story="5.13",
        description="D4: single-turn plus multi-turn case count >= GOLDEN_CASE_FLOOR.",
        computed="golden_case_floor",
    ),
    GateBCheck(
        check="per_capability_floor",
        row="golden_dataset_size",
        story="5.13",
        description="D5: >= 4 single-turn cases per release-allowed capability.",
        computed="per_capability_floor",
    ),
    GateBCheck(
        check="protected_floor_and_tag_integrity",
        row="golden_dataset_size",
        story="5.13",
        description=(
            "D6: >= 10 consequential/prohibited single-turn cases on release-"
            "allowed capabilities, with every protected tag backed by its case."
        ),
        computed="protected_floor_and_tag_integrity",
    ),
    # ----------------------------------------------------------------------- Tool routing
    GateBCheck(
        check="live_golden_routing",
        row="tool_routing",
        story="5.13",
        description=(
            "Live single-turn routing: >= 90% overall and 100% consequential/"
            "prohibited in each of three recorded passes (D8, D9)."
        ),
        evidence_path="evidence/story-5.13/live-golden-routing.json",
        verdict_key="tool_routing",
        verdict_pass_values=("passed",),
        exception_value="excepted",
        freshness="code_ancestor",
    ),
    GateBCheck(
        check="live_routing_machinery",
        row="tool_routing",
        story="5.13",
        description="The routing generator's population, threshold and redaction guards.",
        runner="pytest",
        test_files=("backend/tests/test_live_golden_routing.py",),
    ),
    # ---------------------------------------------------------- NFR35 internal thresholds
    GateBCheck(
        check="nfr35_threshold_tests",
        row="nfr35_internal_thresholds",
        story="1.4, 1.5, 2.4, 3.5",
        description=(
            "D7: the four NFR35 threshold assertions, passed (not skipped) in the "
            "`-m postgres` run at the bound commit. The regenerated evidence files "
            "carry the published numbers; these tests are the verdict."
        ),
        runner="pytest-postgres",
        test_cases=(
            (_NFR35_FILE, "test_nfr35_projection_initial_windows_meet_two_second_threshold"),
            (_NFR35_FILE, "test_nfr35_exact_evidence_targets_meet_two_second_threshold"),
            (_NFR35_FILE, "test_nfr35_sse_reconnect_replay_meets_five_second_threshold"),
            (_NFR35_FILE, "test_nfr35_first_run_event_meets_five_second_threshold"),
        ),
    ),
    # ---------------------------------------------------------------- Blocking regressions
    from_gate_a("site_membership_and_authentication", row="blocking_regressions",
                category="authorization"),
    from_gate_a("backend_mutation_denial", row="blocking_regressions", category="authorization"),
    from_gate_a("frontend_mutation_denial", row="blocking_regressions", category="authorization"),
    GateBCheck(
        check="authority_boundaries",
        row="blocking_regressions",
        category="authorization",
        story="2.9",
        description=(
            "The model cannot authorize: application-owned authority boundaries "
            "(Story 2.9 File List)."
        ),
        runner="pytest",
        test_files=("backend/tests/architecture/test_authority_boundaries.py",),
    ),
    from_gate_a("approval_and_audit_invariants_proof", row="blocking_regressions",
                category="approval"),
    from_gate_a("approval_audit_report_machinery", row="blocking_regressions",
                category="approval"),
    GateBCheck(
        check="conversation_site_isolation",
        row="blocking_regressions",
        category="isolation",
        story="2.7",
        description=(
            "Another site can neither read nor write a conversation, and is denied "
            "indistinguishably from absence (Story 2.7 File List)."
        ),
        runner="pytest",
        test_files=("backend/tests/test_conversations_postgres.py",),
    ),
    from_gate_a("content_minimization_evidence", row="blocking_regressions",
                category="isolation"),
    from_gate_a("content_minimization_report_machinery", row="blocking_regressions",
                category="isolation"),
    GateBCheck(
        check="repair_hard_constraints",
        row="blocking_regressions",
        category="hard_constraints",
        story="3.10",
        description=(
            "Repair correctness against hard constraints on PostgreSQL, with its "
            "fixture and report guards (Story 3.10 File List)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_repair_correctness_postgres.py",
            "backend/tests/test_repair_correctness_report.py",
            "backend/tests/test_repair_correctness_fixture.py",
        ),
    ),
    GateBCheck(
        check="exact_evidence_grounding",
        row="blocking_regressions",
        category="grounding",
        story="2.7",
        description="Claims grounded in exact evidence (Story 2.7 File List).",
        runner="pytest",
        test_files=(
            "backend/tests/test_grounding_gate.py",
            "backend/tests/test_grounding_contracts.py",
            "backend/tests/test_grounding_on_shipped_fixture.py",
        ),
    ),
    GateBCheck(
        check="clarify_refuse_fail_safely",
        row="blocking_regressions",
        category="grounding",
        story="2.9",
        description="Clarify, refuse and fail safely (Story 2.9 File List).",
        runner="pytest",
        test_files=(
            "backend/tests/test_clarification_resolution.py",
            "backend/tests/test_dialogue_contracts.py",
        ),
    ),
    from_gate_a("recovery_and_idempotency_proof", row="blocking_regressions",
                category="idempotency"),
    from_gate_a("recovery_idempotency_report_machinery", row="blocking_regressions",
                category="idempotency"),
    GateBCheck(
        check="draft_lifecycle",
        row="blocking_regressions",
        category="idempotency",
        story="5.11",
        description=(
            "One working draft per conversation: versioned, replay-safe draft and "
            "discard commands (Story 5.11 File List)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_draft_lifecycle_postgres.py",
            "backend/tests/test_scheduling_draft_discard.py",
            "backend/tests/test_proposal_persistence.py",
        ),
    ),
    GateBCheck(
        check="approval_audit_invariants",
        row="blocking_regressions",
        category="authoritative_audit",
        story="4.5",
        description=(
            "Authoritative audit and decision provenance on PostgreSQL (Story 4.5 "
            "File List)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_approval_audit_invariants_postgres.py",
            "backend/tests/test_approval_governance_postgres.py",
            "backend/tests/test_decision_provenance.py",
        ),
    ),
    from_gate_a("viewer_parity", row="blocking_regressions", category="viewer_parity"),
    from_gate_a("api_parity", row="blocking_regressions", category="viewer_parity"),
    GateBCheck(
        check="worker_recovery",
        row="blocking_regressions",
        category="recovery",
        story="3.11",
        description=(
            "Worker kill, lease expiry and cancellation race on PostgreSQL (Story "
            "3.11 File List)."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_worker_process_recovery_postgres.py",
            "backend/tests/test_job_leasing_postgres.py",
            "backend/tests/test_cancellation_race_postgres.py",
            "backend/tests/test_worker_main.py",
        ),
    ),
    from_gate_a("accessibility_component_layer", row="blocking_regressions",
                category="accessibility"),
    from_gate_a("accessibility_browser_layer", row="blocking_regressions",
                category="accessibility"),
    from_gate_a("accessibility_evidence", row="blocking_regressions", category="accessibility"),
    from_gate_a("state_semantics_matrix", row="blocking_regressions", category="accessibility"),
    from_gate_a("journey_accessibility_browser_layer", row="blocking_regressions",
                category="accessibility"),
    from_gate_a("state_semantics_evidence", row="blocking_regressions",
                category="accessibility"),
    from_gate_a("state_semantics_report_machinery", row="blocking_regressions",
                category="accessibility"),
)


def row_keys() -> tuple[str, ...]:
    return tuple(row.key for row in GATE_B_ROWS)


def checks_for(row_key: str, checks: tuple[GateBCheck, ...] = GATE_B_CHECKS) -> tuple[GateBCheck, ...]:
    return tuple(check for check in checks if check.row == row_key)


def validate_registry(
    checks: tuple[GateBCheck, ...] = GATE_B_CHECKS,
    rows: tuple[GateBRow, ...] = GATE_B_ROWS,
) -> None:
    """Fail loudly on a registry that cannot decide every Gate B row."""
    known = {row.key for row in rows}
    for check in checks:
        if check.row not in known:
            raise ValueError(f"check {check.check!r} names unregistered row {check.row!r}")
        if check.row == "blocking_regressions":
            if check.category not in BLOCKING_REGRESSION_CATEGORIES:
                raise ValueError(
                    f"check {check.check!r} names unknown blocking-regression "
                    f"category {check.category!r}"
                )
        elif check.category is not None:
            raise ValueError(f"check {check.check!r}: only blocking regressions take a category")
        if check.computed and check.computed not in COMPUTED_CHECKS:
            raise ValueError(f"check {check.check!r} names unknown computed check {check.computed!r}")
    ids = [check.check for check in checks]
    duplicates = {name for name in ids if ids.count(name) > 1}
    if duplicates:
        raise ValueError(f"duplicate check ids: {', '.join(sorted(duplicates))}")
    uncovered = [row.key for row in rows if not checks_for(row.key, checks)]
    if uncovered:
        raise ValueError(f"row(s) with no contributing check: {', '.join(uncovered)}")
    covered_categories = {c.category for c in checks if c.row == "blocking_regressions"}
    missing = [c for c in BLOCKING_REGRESSION_CATEGORIES if c not in covered_categories]
    if missing:
        raise ValueError(f"blocking-regression category(ies) with no check: {', '.join(missing)}")


def registered_evidence_paths(checks: tuple[GateBCheck, ...] = GATE_B_CHECKS) -> tuple[str, ...]:
    return tuple(sorted({c.evidence_path for c in checks if c.evidence_path}))


__all__ = [
    "BLOCKING_REGRESSION_CATEGORIES",
    "COMPUTED_CHECKS",
    "GATE_B_CHECKS",
    "GATE_B_ROWS",
    "GOLDEN_CASE_FLOOR",
    "GateBCheck",
    "GateBRow",
    "LIVE_FRESHNESS_PATHS",
    "PER_CAPABILITY_FLOOR",
    "PROTECTED_CASE_FLOOR",
    "PROTECTED_RISK_CLASSES",
    "checks_for",
    "from_gate_a",
    "registered_evidence_paths",
    "row_keys",
    "validate_registry",
]
