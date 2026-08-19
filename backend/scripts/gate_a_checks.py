"""Declarative registry of the checks that decide Gate A.

AC2 requires "the pass/fail result of each contributing Story 1.1-1.10 check".
Only four of the ten stories produced an evidence file, and those four cover
just two of AR28's six invariants — so a rollup limited to evidence files
cannot satisfy AC2. The remaining stories are represented by the test suites
that are their proof, read from JUnit XML.

Every entry carries the invariant it serves, so the report can answer
"is site membership proven?" rather than only showing a flat list. AC1 is
stated in terms of invariants.

Provenance
----------
Test-file lists are transcribed from each story's own `### File List`
section, not guessed. One correction was necessary: Story 1.9's Task 5 legacy
sweep *deleted* a large part of the surface that Stories 1.3 and 1.9 list
(`components/editor/*`, `components/results/*`, `components/runs/*`,
`components/scenarios/*`, the `useRun*` hooks, `routes/Editor|ResultsView|
RunHistory`, `api/scenarios|constraints|runs`). Those files are gone by
design, so they are not registered. The Task 3 ingestion fails loudly on any
registered id missing from the XML, which is what keeps this list honest from
here on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Runner = Literal["pytest", "vitest", "playwright"]
Authority = Literal["AR28", "NFR29", "AC2"]


@dataclass(frozen=True)
class Invariant:
    """A Gate A invariant that contributing checks roll up into."""

    key: str
    title: str
    authority: Authority


#: AR28 names exactly six invariants, verbatim: "PostgreSQL/site membership,
#: immutable fixtures, the normalized scenario read service, authenticated
#: read-only Scenario Data, parity tests, and negative mutation tests".
AR28_INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        "postgresql_site_membership",
        "PostgreSQL / site membership",
        "AR28",
    ),
    Invariant("immutable_fixtures", "Immutable fixtures", "AR28"),
    Invariant(
        "normalized_scenario_reads",
        "Normalized scenario read service",
        "AR28",
    ),
    Invariant(
        "authenticated_readonly_scenario_data",
        "Authenticated read-only Scenario Data",
        "AR28",
    ),
    Invariant("parity_tests", "Parity tests", "AR28"),
    Invariant("negative_mutation_tests", "Negative mutation tests", "AR28"),
)

#: Accessibility is NOT one of AR28's six. It reaches the gate through AC1's
#: Given clause ("all Gate A viewer, isolation, parity, mutation-denial, and
#: accessibility checks") and through NFR29, which blocks release on
#: accessibility regressions regardless of aggregate helpfulness. Modelled
#: separately so the report does not misattribute it to AR28, while still
#: letting it block the gate.
NFR29_GATES: tuple[Invariant, ...] = (
    Invariant(
        "accessibility_and_responsiveness",
        "Accessibility / responsiveness",
        "NFR29",
    ),
)

#: Neither AR28's nor NFR29's, but AC2's: "any missing or unbound contributing
#: result blocks the gate". The machinery that decides *that* has to be held to
#: its own standard, or the gate's verdict rests on unverified plumbing. The
#: originally shipped report is the argument for this: it was computed from a
#: pytest run in which thirteen `test_evidence_convention.py` cases were
#: failing, and because those tests were not registered, the report could not
#: see them and reported every invariant green.
AC2_GATES: tuple[Invariant, ...] = (
    Invariant(
        "measurement_integrity",
        "Measurement integrity (evidence convention and gate machinery)",
        "AC2",
    ),
)

ALL_INVARIANTS: tuple[Invariant, ...] = AR28_INVARIANTS + NFR29_GATES + AC2_GATES


@dataclass(frozen=True)
class GateACheck:
    """One contributing check: a story's proof of part of one invariant."""

    check: str
    story: str
    invariant: str
    description: str
    #: Repo-relative test files whose results prove this check.
    test_files: tuple[str, ...] = ()
    runner: Runner | None = None
    #: Repo-relative evidence JSON whose `passed` flag proves this check.
    evidence_path: str | None = None
    #: Browser projects this check claims proof on. Playwright records the
    #: project in the JUnit `hostname`, so a check asserting Chromium+Edge
    #: coverage is verified rather than assumed — a chromium-only run used to
    #: satisfy it silently.
    required_projects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.test_files and not self.evidence_path:
            raise ValueError(
                f"check {self.check!r} has no proving artifact"
            )
        if self.test_files and self.runner is None:
            raise ValueError(
                f"check {self.check!r} declares test files but no runner"
            )
        if self.test_files and self.evidence_path:
            # The report reads the evidence branch first and never looks at the
            # test results, while the declared files still have to be present
            # in the XML — a check whose tests must run but whose outcome is
            # discarded. Refuse the combination rather than half-honour it.
            raise ValueError(
                f"check {self.check!r} declares both an evidence_path and "
                "test_files; the evidence branch would silently discard the "
                "test results. Split it into two checks."
            )
        if self.required_projects and self.runner != "playwright":
            raise ValueError(
                f"check {self.check!r} declares required_projects but its "
                "runner is not playwright; only Playwright records a project."
            )


GATE_A_CHECKS: tuple[GateACheck, ...] = (
    # ---------------------------------------------------------------- 1.1
    GateACheck(
        check="immutable_fixture_history",
        story="1.1",
        invariant="immutable_fixtures",
        description=(
            "Checksummed fixture import, append-only versioned history, and "
            "the one-way Gate A cutover."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_fixture_history_import.py",
            "backend/tests/test_gate_a_cutover.py",
            "backend/tests/test_postgres_schema.py",
            "backend/tests/test_postgres_toolchain.py",
        ),
    ),
    # ---------------------------------------------------------------- 1.2
    GateACheck(
        check="site_membership_and_authentication",
        story="1.2",
        invariant="postgresql_site_membership",
        description=(
            "Seeded site identity, role boundaries, and site-scoped session "
            "resolution on PostgreSQL."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_auth_api.py",
            "backend/tests/test_identity_schema.py",
            "backend/tests/test_identity_provider.py",
            "backend/tests/test_identity_role_boundaries.py",
            "backend/tests/test_seed_planner.py",
            "backend/tests/test_postgres_integration.py",
        ),
    ),
    GateACheck(
        check="session_client_boundary",
        story="1.2",
        invariant="postgresql_site_membership",
        description="Browser session handling and the authenticated API client.",
        runner="vitest",
        test_files=(
            "frontend/src/api/client.test.ts",
            "frontend/src/hooks/useSession.test.tsx",
            "frontend/src/components/layout/AppBar.test.tsx",
        ),
    ),
    # ---------------------------------------------------------------- 1.3
    GateACheck(
        check="immutable_fixture_selection_api",
        story="1.3",
        invariant="authenticated_readonly_scenario_data",
        description="Site-scoped fixture catalogue read API.",
        runner="pytest",
        test_files=(
            "backend/tests/test_scenario_catalogue_adapter.py",
            "backend/tests/test_scenario_catalogue_api.py",
        ),
    ),
    GateACheck(
        check="immutable_fixture_selection_ui",
        story="1.3",
        invariant="authenticated_readonly_scenario_data",
        description="Fixture catalogue route, version pinning, and routing.",
        runner="vitest",
        test_files=(
            "frontend/src/api/scenarioCatalogue.test.ts",
            "frontend/src/features/fixture-catalogue/FixtureCatalogueView.test.tsx",
            "frontend/src/features/scenario-workspace/ScenarioVersionContext.test.tsx",
            "frontend/src/hooks/useFixtureCatalogue.test.tsx",
            "frontend/src/routes/FixtureCatalogue.test.tsx",
            "frontend/src/routes/router.test.tsx",
        ),
    ),
    # ---------------------------------------------------------------- 1.4
    GateACheck(
        check="normalized_projection_contract",
        story="1.4",
        invariant="normalized_scenario_reads",
        description="Normalized scenario projection read contract and paging.",
        runner="pytest",
        test_files=("backend/tests/test_scenario_projection.py",),
    ),
    GateACheck(
        check="normalized_projection_nfr35_latency",
        story="1.4",
        invariant="normalized_scenario_reads",
        description="NFR35 initial-window latency under the 2s threshold.",
        evidence_path="evidence/story-1.4/nfr35-scenario-data-load.json",
    ),
    # ---------------------------------------------------------------- 1.5
    GateACheck(
        check="exact_evidence_target_resolution",
        story="1.5",
        invariant="normalized_scenario_reads",
        description="Exact evidence-reference resolution and de-duplication.",
        runner="pytest",
        test_files=(
            "backend/tests/test_evidence_ref.py",
            "backend/tests/test_resolve_dedup.py",
        ),
    ),
    GateACheck(
        check="evidence_target_nfr35_latency",
        story="1.5",
        invariant="normalized_scenario_reads",
        description="NFR35 evidence-target resolution under the 2s threshold.",
        evidence_path="evidence/story-1.5/nfr35-evidence-target-resolution.json",
    ),
    # ---------------------------------------------------------------- 1.6
    GateACheck(
        check="design_tokens_and_primitives",
        story="1.6",
        invariant="authenticated_readonly_scenario_data",
        description=(
            "ShiftMind design tokens and the shared accessible primitives the "
            "read-only workspace is built from."
        ),
        runner="vitest",
        test_files=(
            "frontend/src/index.test.ts",
            "frontend/src/components/primitives/EmptyState.test.tsx",
            "frontend/src/components/primitives/EvidenceHighlight.test.tsx",
            "frontend/src/components/primitives/EvidenceLink.test.tsx",
            "frontend/src/components/primitives/InlineAlert.test.tsx",
            "frontend/src/components/primitives/ReconnectBanner.test.tsx",
            "frontend/src/components/primitives/StatusBadge.test.tsx",
            "frontend/src/components/primitives/fixtures.test.tsx",
        ),
    ),
    # ---------------------------------------------------------------- 1.7
    GateACheck(
        check="read_only_scenario_data_workspace",
        story="1.7",
        invariant="authenticated_readonly_scenario_data",
        description="Scenario Data workspace shell and the seven data groups.",
        runner="vitest",
        test_files=(
            "frontend/src/api/scenarioProjection.test.ts",
            "frontend/src/features/scenario-data/ScenarioDataView.test.tsx",
            "frontend/src/features/scenario-data/groups/BaselineAssignmentsPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/ConstraintsPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/DemandPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/LocksPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/OverviewPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/WorkAreasAndTasksPanel.test.tsx",
            "frontend/src/features/scenario-data/groups/WorkersPanel.test.tsx",
            "frontend/src/features/scenario-workspace/WorkspaceTabs.test.tsx",
            "frontend/src/hooks/useScenarioProjection.test.tsx",
            "frontend/src/lib/formatShiftWindow.test.ts",
            "frontend/src/routes/ScenarioWorkspace.test.tsx",
        ),
    ),
    # ---------------------------------------------------------------- 1.8
    GateACheck(
        check="scenario_data_table_controls",
        story="1.8",
        invariant="authenticated_readonly_scenario_data",
        description=(
            "Server-side sort/filter/paging and the table control surface."
        ),
        runner="vitest",
        test_files=(
            "frontend/src/components/primitives/IdentifierCopyButton.test.tsx",
            "frontend/src/features/scenario-data/ColumnChooser.test.tsx",
            "frontend/src/features/scenario-data/FilterBar.test.tsx",
            "frontend/src/features/scenario-data/PaginationControls.test.tsx",
            "frontend/src/features/scenario-data/ScenarioDataTable.test.tsx",
            "frontend/src/features/scenario-data/columns.test.ts",
            "frontend/src/features/scenario-data/filters.test.ts",
            "frontend/src/features/scenario-data/useColumnVisibility.test.tsx",
            "frontend/src/features/scenario-data/useGroupControls.test.tsx",
        ),
    ),
    # ---------------------------------------------------------------- 1.9
    GateACheck(
        check="viewer_parity",
        story="1.9",
        invariant="parity_tests",
        description="API and frontend parity against the pinned contract fixtures.",
        runner="vitest",
        test_files=(
            "frontend/src/features/scenario-data/ScenarioDataParity.test.tsx",
        ),
    ),
    # Replaced `viewer_parity_evidence` on 2026-08-18. That check read the
    # `passed` field of `evidence/story-1.9/gate-a-viewer-parity-and-mutation-
    # denial.json` as a PRESENT-TENSE verdict, and its only guard asserted
    # string literals inside the same file — circular. The evidence file is
    # untouched and still on disk; it remains a true record of commit
    # `e2ecdb6`, just no longer consulted about today.
    #
    # Of the four things that file claimed, three already had live checks
    # (`viewer_parity`, `backend_mutation_denial`, `frontend_mutation_denial`).
    # `api_parity` was the one that did not, and the test proving it was
    # already written — it simply was not registered.
    GateACheck(
        check="api_parity",
        story="1.9",
        invariant="parity_tests",
        description=(
            "Live projection API parity against the pinned contract fixtures."
        ),
        runner="pytest",
        test_files=("backend/tests/test_postgres_integration.py",),
    ),
    GateACheck(
        check="backend_mutation_denial",
        story="1.9",
        invariant="negative_mutation_tests",
        description="Server refuses every write path at Gate A.",
        runner="pytest",
        test_files=(
            "backend/tests/test_gate_a_mutation_audit.py",
            "backend/tests/test_export_contract_fixture.py",
        ),
    ),
    GateACheck(
        check="frontend_mutation_denial",
        story="1.9",
        invariant="negative_mutation_tests",
        description=(
            "No mutating affordance or reachable legacy route in the client."
        ),
        runner="vitest",
        test_files=(
            "frontend/src/test/scenarioDataBoundaries.test.ts",
            "frontend/src/test/legacyReachability.test.ts",
        ),
    ),
    # --------------------------------------------------------------- 1.10
    GateACheck(
        check="accessibility_component_layer",
        story="1.10",
        invariant="accessibility_and_responsiveness",
        description="jsdom/axe accessibility contract over the Gate A surface.",
        runner="vitest",
        test_files=(
            "frontend/src/test/accessibility.test.tsx",
            "frontend/src/test/accessibility-contract.test.tsx",
            "frontend/src/features/scenario-data/usePhoneViewport.test.tsx",
        ),
    ),
    GateACheck(
        check="accessibility_browser_layer",
        story="1.10",
        invariant="accessibility_and_responsiveness",
        description=(
            "Real-browser zoom, reflow, text spacing, touch targets, keyboard "
            "journey, and reduced motion on Chromium and Edge."
        ),
        runner="playwright",
        test_files=(
            "frontend/e2e/accessibility.spec.ts",
            "frontend/e2e/gate-a-fixture-coverage.spec.ts",
            "frontend/e2e/harness.spec.ts",
            "frontend/e2e/keyboard-journey.spec.ts",
            "frontend/e2e/layout-accessibility.spec.ts",
            "frontend/e2e/reduced-motion.spec.ts",
            "frontend/e2e/responsive.spec.ts",
        ),
        # The description says "on Chromium and Edge"; make the report prove it.
        required_projects=("chromium", "msedge"),
    ),
    GateACheck(
        check="accessibility_evidence",
        story="1.10",
        invariant="accessibility_and_responsiveness",
        description=(
            "Recorded accessibility evidence from automated coverage. Manual "
            "assistive-technology verification is explicitly descoped for "
            "this portfolio MVP (see EXPERIENCE.md's Accessibility Floor and "
            "docs/GATE-A-RUNBOOK.md)."
        ),
        evidence_path=(
            "evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json"
        ),
    ),
    # ---------------------------------------------------------------- 1.11
    GateACheck(
        check="evidence_convention_and_gate_machinery",
        story="1.11",
        invariant="measurement_integrity",
        description=(
            "The repo-wide evidence convention sweep, the binding resolver, "
            "and the readiness generator itself. Registered so a broken "
            "convention blocks the gate instead of being invisible to it."
        ),
        runner="pytest",
        test_files=(
            "backend/tests/test_evidence_binding.py",
            "backend/tests/test_evidence_convention.py",
            "backend/tests/test_gate_a_readiness.py",
        ),
    ),
)


def invariant_keys() -> tuple[str, ...]:
    return tuple(inv.key for inv in ALL_INVARIANTS)


def checks_for(invariant_key: str) -> tuple[GateACheck, ...]:
    return tuple(c for c in GATE_A_CHECKS if c.invariant == invariant_key)


def contributing_stories() -> tuple[str, ...]:
    # Sorted by (major, minor) as integers. `float("1.10") == float("1.1")`, so
    # a float key made stories 1.1 and 1.10 tie and fall back to set-iteration
    # order, and any non-numeric story key raised.
    def _key(story: str) -> tuple[int, ...]:
        parts: list[int] = []
        for segment in story.split("."):
            digits = "".join(ch for ch in segment if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    return tuple(sorted({c.story for c in GATE_A_CHECKS}, key=_key))


def validate_registry() -> None:
    """Fail loudly on a registry that cannot satisfy AC1/AC2 by construction."""
    known = set(invariant_keys())
    for check in GATE_A_CHECKS:
        if check.invariant not in known:
            raise ValueError(
                f"check {check.check!r} names unknown invariant "
                f"{check.invariant!r}"
            )
    ids = [c.check for c in GATE_A_CHECKS]
    duplicates = {name for name in ids if ids.count(name) > 1}
    if duplicates:
        raise ValueError(f"duplicate check ids: {', '.join(sorted(duplicates))}")
    uncovered = [key for key in known if not checks_for(key)]
    if uncovered:
        raise ValueError(
            f"invariant(s) with no contributing check: {', '.join(uncovered)}"
        )


__all__ = [
    "AR28_INVARIANTS",
    "ALL_INVARIANTS",
    "GATE_A_CHECKS",
    "NFR29_GATES",
    "GateACheck",
    "Invariant",
    "checks_for",
    "contributing_stories",
    "invariant_keys",
    "validate_registry",
]
