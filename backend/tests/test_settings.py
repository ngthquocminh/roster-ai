"""Feature-policy flag parsing.

These flags decide whether a governed capability reaches a live planner, so a
malformed value has to be loud rather than resolved to whichever answer happens
to be the default.
"""
from __future__ import annotations

import pytest

from settings import InvalidFlagError, default_settings


def test_a_malformed_feature_flag_fails_loudly_instead_of_falling_back(monkeypatch) -> None:
    """Fail-open in the DISABLE direction was the dangerous half.

    The previous shape returned the fallback for any unrecognized token. For the
    two capabilities defaulting True that meant `SCHEDULING_COMPUTE_ENABLED=
    disabled` silently left the capability granted -- an operator turning it off
    got no effect and no error. The docstring claimed "a typo cannot silently
    enable a capability", which was true only for the one flag defaulting False.
    """
    monkeypatch.setenv("SCHEDULING_COMPUTE_ENABLED", "disabled")
    with pytest.raises(InvalidFlagError, match="SCHEDULING_COMPUTE_ENABLED"):
        default_settings()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("off", False), ("0", False), ("no", False), ("FALSE", False),
     ("on", True), ("1", True), ("yes", True), ("TRUE", True)],
)
def test_recognized_feature_flag_spellings_still_parse(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("SCHEDULING_COMPUTE_ENABLED", raw)
    assert default_settings().scheduling_compute_enabled is expected


def test_an_unset_feature_flag_takes_its_declared_default(monkeypatch) -> None:
    """demonstration is a harness module and stays off unless asked for."""
    monkeypatch.delenv("SCHEDULING_COMPUTE_ENABLED", raising=False)
    monkeypatch.delenv("DEMONSTRATION_ENABLED", raising=False)
    settings = default_settings()
    assert settings.scheduling_compute_enabled is True
    assert settings.demonstration_enabled is False


def test_scheduling_draft_settings_are_operator_owned_and_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SCHEDULING_DRAFT_ENABLED", raising=False)
    monkeypatch.setenv("SCHEDULING_DRAFT_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("SCHEDULING_DRAFT_MAX_CONSTRAINTS", "6")
    settings = default_settings()
    assert settings.scheduling_draft_enabled is True
    assert settings.scheduling_draft_timeout_seconds == 7.5
    assert settings.scheduling_draft_max_constraints == 6


def test_governed_solver_settings_are_positive_and_application_owned(monkeypatch) -> None:
    for name in (
        "SOLVER_ENGINE_NAME", "SOLVER_SEED", "SOLVER_NUM_SEARCH_WORKERS",
        "SOLVER_MAX_DETERMINISTIC_TIME", "SOLVER_WALL_TIME_LIMIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = default_settings()
    assert settings.solver_engine_name == "cpsat"
    assert settings.solver_seed == 42
    assert settings.solver_num_search_workers == 1
    assert settings.solver_max_deterministic_time == 30.0
    assert settings.solver_wall_time_limit_seconds == 30.0


@pytest.mark.parametrize(
    ("name", "raw"),
    (
        ("SOLVER_ENGINE_NAME", ""),
        ("SOLVER_SEED", "0"),
        ("SOLVER_NUM_SEARCH_WORKERS", "-1"),
        ("SOLVER_MAX_DETERMINISTIC_TIME", "not-a-number"),
        ("SOLVER_WALL_TIME_LIMIT_SECONDS", "0"),
    ),
)
def test_invalid_governed_solver_setting_fails_at_startup(monkeypatch, name, raw) -> None:
    monkeypatch.setenv(name, raw)
    with pytest.raises(InvalidFlagError, match=name):
        default_settings()
