"""The default pytest session ignores a developer's real agent-runtime settings.

`settings.py` loads `backend/.env` at import, so without `conftest.py`'s pin a
real `AGENT_RUNTIME_MODEL` / `AGENT_RUNTIME_API_KEY` reaches every
`default_settings()` call. Existing suites cannot prove the pin: several already
`monkeypatch.delenv` the model themselves, and a fake value does not redden the
rest, so the pin needs its own guard.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import _selects_live, pytest_configure
from settings import default_settings


def test_default_session_runs_against_the_keyless_deterministic_double() -> None:
    settings = default_settings()

    assert settings.agent_runtime_model == "deterministic"
    assert settings.agent_runtime_api_key is None


@pytest.mark.parametrize(
    ("markexpr", "expected"),
    [
        ("not live", False),
        ("postgres and not live", False),
        ("", True),
        ("live", True),
        ("live or postgres", True),
        ("not live or live", True),
    ],
)
def test_only_a_mark_expression_that_selects_live_counts_as_a_live_session(
    markexpr: str, expected: bool
) -> None:
    assert _selects_live(markexpr) is expected


def test_a_live_session_keeps_the_real_agent_runtime_values(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_MODEL", "openrouter:real-model")
    monkeypatch.setenv("AGENT_RUNTIME_API_KEY", "real-key")

    pytest_configure(SimpleNamespace(getoption=lambda name: "live"))

    settings = default_settings()
    assert settings.agent_runtime_model == "openrouter:real-model"
    assert settings.agent_runtime_api_key == "real-key"


def test_a_default_session_overrides_real_agent_runtime_values(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_MODEL", "openrouter:real-model")
    monkeypatch.setenv("AGENT_RUNTIME_API_KEY", "real-key")

    pytest_configure(SimpleNamespace(getoption=lambda name: "not live"))

    settings = default_settings()
    assert settings.agent_runtime_model == "deterministic"
    assert settings.agent_runtime_api_key is None
