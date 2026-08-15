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
