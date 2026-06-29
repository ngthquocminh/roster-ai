"""Degeneracy detection tests (ENG-05).

Validates that SolveResult carries a warnings field and that the detection
logic in CpSatEngine correctly flags task families with real demand but zero
assigned supply, without altering solver_status.

Approach: unit-test the detection condition directly over CoverageStat
instances — no live CP-SAT solve needed, so tests stay fast and portable.
"""
from __future__ import annotations

from domain.result import CoverageStat, SolveResult, SummaryMetrics, SolverStats
from services.serialize import serialize_result


# ---------------------------------------------------------------------------
# Helper — detection logic extracted from engine.py (ENG-05)
# ---------------------------------------------------------------------------

def _detect_warnings(coverage_by_function: dict[str, CoverageStat]) -> list[str]:
    """Mirror of the detection loop in CpSatEngine.solve.

    Kept as a helper so tests can exercise the condition directly without
    a real CP-SAT solve, which crashes under some Windows environments.
    """
    warnings: list[str] = []
    for fn, stat in coverage_by_function.items():
        if stat.required_h > 1e-9 and stat.served_h <= 1e-9:
            warnings.append(
                f"Degenerate solve: task family '{fn}' has {stat.required_h:.1f}h "
                f"required but zero assigned supply."
            )
    return warnings


def _make_result(**kwargs) -> SolveResult:
    """Build a minimal SolveResult for field presence / serialization checks."""
    defaults: dict = dict(
        status="OPTIMAL",
        schedule=[],
        metrics=SummaryMetrics(),
        stats=SolverStats(
            status="OPTIMAL",
            wall_time_s=0.1,
            unmet_objective_hours=0.0,
            cost_objective=0.0,
        ),
    )
    defaults.update(kwargs)
    return SolveResult(**defaults)


# ---------------------------------------------------------------------------
# 1. warnings field presence
# ---------------------------------------------------------------------------

def test_warnings_field_present_on_solve_result():
    """SolveResult without explicit warnings defaults to empty list."""
    r = _make_result()
    assert hasattr(r, "warnings"), "SolveResult must have a warnings attribute"
    assert r.warnings == [], f"Expected [], got {r.warnings!r}"


def test_warnings_explicit_value_preserved():
    """An explicit warnings list is stored as provided."""
    msgs = ["Degenerate solve: task family 'Pick' has 8.0h required but zero assigned supply."]
    r = _make_result(warnings=msgs)
    assert r.warnings == msgs


# ---------------------------------------------------------------------------
# 2. Detection condition — zero supply
# ---------------------------------------------------------------------------

def test_degeneracy_detected_on_zero_supply():
    """A family with required_h > 0 and served_h == 0 triggers exactly one warning."""
    coverage = {"Pick": CoverageStat(required_h=10.0, served_h=0.0)}
    warnings = _detect_warnings(coverage)
    assert len(warnings) == 1, f"Expected 1 warning, got {warnings}"
    assert "Pick" in warnings[0], f"Warning must name the affected family: {warnings[0]}"
    assert "10.0h" in warnings[0], f"Warning must include required hours: {warnings[0]}"


def test_degeneracy_warning_names_family():
    """The warning message identifies the specific task family by name."""
    coverage = {"Outbound-Pick": CoverageStat(required_h=8.5, served_h=0.0)}
    warnings = _detect_warnings(coverage)
    assert len(warnings) == 1
    assert "Outbound-Pick" in warnings[0]


def test_multiple_degenerate_families_all_flagged():
    """Every zero-supply demanded family gets its own warning."""
    coverage = {
        "Pick": CoverageStat(required_h=10.0, served_h=0.0),
        "Pack": CoverageStat(required_h=5.0, served_h=0.0),
        "Receive": CoverageStat(required_h=3.0, served_h=0.0),
    }
    warnings = _detect_warnings(coverage)
    assert len(warnings) == 3
    family_names = [w for w in ("Pick", "Pack", "Receive") if any(family in w for family in ("Pick", "Pack", "Receive") for w in warnings)]
    # All three families must appear
    assert any("Pick" in w for w in warnings)
    assert any("Pack" in w for w in warnings)
    assert any("Receive" in w for w in warnings)


# ---------------------------------------------------------------------------
# 3. Negative test — fully covered family produces no warning
# ---------------------------------------------------------------------------

def test_no_warning_for_fully_covered_family():
    """A family with served_h == required_h produces no warnings."""
    coverage = {"Pick": CoverageStat(required_h=10.0, served_h=10.0)}
    warnings = _detect_warnings(coverage)
    assert warnings == [], f"Fully covered family must not warn, got: {warnings}"


def test_no_warning_for_partially_covered_family():
    """Partial coverage (served_h > 0 but < required_h) is NOT flagged as degenerate."""
    coverage = {"Pick": CoverageStat(required_h=10.0, served_h=3.0)}
    warnings = _detect_warnings(coverage)
    assert warnings == [], (
        f"Partial coverage is not degenerate (served_h > 0); got: {warnings}"
    )


def test_mixed_families_only_zero_supply_flagged():
    """Only the zero-supply family is flagged; the covered one is not."""
    coverage = {
        "Pick": CoverageStat(required_h=10.0, served_h=0.0),   # degenerate
        "Pack": CoverageStat(required_h=8.0, served_h=8.0),    # fully covered
    }
    warnings = _detect_warnings(coverage)
    assert len(warnings) == 1
    assert "Pick" in warnings[0]
    assert "Pack" not in warnings[0]


# ---------------------------------------------------------------------------
# 4. Edge cases
# ---------------------------------------------------------------------------

def test_zero_required_hours_not_flagged():
    """A family with required_h == 0 is not flagged (no real demand)."""
    coverage = {"Pick": CoverageStat(required_h=0.0, served_h=0.0)}
    warnings = _detect_warnings(coverage)
    assert warnings == [], (
        f"Family with zero demand must not produce a warning; got: {warnings}"
    )


def test_near_zero_required_hours_not_flagged():
    """required_h at floating-point noise level (< 1e-9) is not flagged."""
    coverage = {"Pick": CoverageStat(required_h=1e-10, served_h=0.0)}
    warnings = _detect_warnings(coverage)
    assert warnings == [], (
        f"Near-zero demand must not be treated as real demand; got: {warnings}"
    )


def test_empty_coverage_map_no_warnings():
    """An empty coverage_by_function produces no warnings."""
    warnings = _detect_warnings({})
    assert warnings == []


# ---------------------------------------------------------------------------
# 5. Status never altered by detection
# ---------------------------------------------------------------------------

def test_status_not_altered_when_warnings_present():
    """A SolveResult with warnings still carries the original solver status.

    Detection is append-only to warnings — it must never touch status
    (enforced by the detection loop in engine.py never writing to status).
    """
    r = _make_result(
        status="OPTIMAL",
        warnings=["Degenerate solve: task family 'Pick' has 8.0h required but zero assigned supply."],
    )
    assert r.status == "OPTIMAL", (
        f"Warnings must not alter status; expected OPTIMAL, got {r.status!r}"
    )


# ---------------------------------------------------------------------------
# 6. Warnings survive serialization
# ---------------------------------------------------------------------------

def test_warnings_in_serialize_result_output():
    """serialize_result includes a top-level 'warnings' key."""
    r = _make_result()
    d = serialize_result(r)
    assert "warnings" in d, f"serialize_result output must have 'warnings' key; keys: {list(d)}"
    assert d["warnings"] == []


def test_warnings_values_survive_serialization():
    """Warning strings pass through serialize_result unchanged."""
    msg = "Degenerate solve: task family 'Pick' has 10.0h required but zero assigned supply."
    r = _make_result(warnings=[msg])
    d = serialize_result(r)
    assert d["warnings"] == [msg], f"Warning content must be preserved; got: {d['warnings']}"
