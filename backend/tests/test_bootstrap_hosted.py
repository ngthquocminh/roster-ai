"""Story 6.2 D3: the hosted bootstrap's refusal rules and its one JSON line.

No database here. The stages are replaced by fakes so that each test isolates
one rule: what the entry point refuses, that stdout is exactly one JSON line,
and that neither stdout nor stderr ever carries a password, host or URL.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import bootstrap_hosted
from scripts.bootstrap_hosted import (
    RefusedConfiguration,
    redact,
    validate_login_url,
)
from scripts.check_db_privileges import CheckResult

LOGIN_PASSWORD = "Gen3ratedLoginPassw0rdXyz"
MIGRATOR_PASSWORD = "Gen3ratedMigratorPassw0rd"
HOST = "shiftmind-test-db.abc123.ap-southeast-1.rds.amazonaws.com"
LOGIN_URL = f"postgresql+psycopg://shiftmind_login:{LOGIN_PASSWORD}@{HOST}:5432/rosterai?sslmode=require"
MIGRATOR_URL = f"postgresql+psycopg://shiftmind_migrator:{MIGRATOR_PASSWORD}@{HOST}:5432/rosterai?sslmode=require"
FORBIDDEN = (LOGIN_PASSWORD, MIGRATOR_PASSWORD, HOST, "postgresql")


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        (f"postgresql+psycopg://shiftmind_migrator:{LOGIN_PASSWORD}@{HOST}/rosterai", "authenticate as"),
        (f"postgresql+psycopg://shiftmind_login:shiftmind_login@{HOST}/rosterai", "initial login password"),
        (f"postgresql+psycopg://shiftmind_login@{HOST}/rosterai", "no password"),
    ],
)
def test_validate_login_url_refuses_a_url_that_defeats_rotation(url: str, reason: str) -> None:
    with pytest.raises(RefusedConfiguration, match=reason):
        validate_login_url(url)


def test_validate_login_url_accepts_a_generated_login_password() -> None:
    url = validate_login_url(LOGIN_URL)
    assert url.username == "shiftmind_login"
    assert url.password == LOGIN_PASSWORD


def test_redact_replaces_every_secret_and_the_longest_first() -> None:
    message = f"failed: {MIGRATOR_URL} and {LOGIN_PASSWORD} at {HOST}"
    redacted = redact(message, [MIGRATOR_PASSWORD, HOST, MIGRATOR_URL, LOGIN_PASSWORD])
    for secret in (MIGRATOR_PASSWORD, LOGIN_PASSWORD, HOST, "shiftmind_migrator:"):
        assert secret not in redacted


class _FakeEngine:
    def dispose(self) -> None:
        return None

    def connect(self) -> Any:
        engine = self

        class _Ctx:
            def __enter__(self) -> _FakeEngine:
                return engine

            def __exit__(self, *exc: object) -> None:
                return None

        return _Ctx()


@pytest.fixture
def hosted_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("ROSTERAI_DATABASE_URL", LOGIN_URL)
    monkeypatch.setenv("ROSTERAI_PROVISIONING_DATABASE_URL", MIGRATOR_URL)
    calls: dict[str, Any] = {"rotated": None, "checks_kwargs": None}
    fixture = SimpleNamespace(created=True)
    monkeypatch.setattr(bootstrap_hosted, "create_engine", lambda *a, **k: _FakeEngine())
    monkeypatch.setattr(
        bootstrap_hosted,
        "bootstrap_local",
        lambda **_: SimpleNamespace(
            fixtures=(fixture, fixture), planner=SimpleNamespace(created=False)
        ),
    )

    def _rotate(engine: object, password: str) -> None:
        calls["rotated"] = password

    monkeypatch.setattr(bootstrap_hosted, "rotate_login_password", _rotate)

    def _checks(connection: object, **kwargs: Any) -> list[CheckResult]:
        calls["checks_kwargs"] = kwargs
        return calls.get("results") or [CheckResult("a_check", True, "fine")]

    monkeypatch.setattr(bootstrap_hosted, "run_checks", _checks)
    return calls


def _single_json_line(out: str) -> dict[str, Any]:
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    return json.loads(lines[0])


def _assert_no_secret(text: str) -> None:
    for secret in FORBIDDEN:
        assert secret not in text


def test_main_prints_one_clean_json_line_and_exits_zero_when_everything_passes(
    hosted_env: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    code = bootstrap_hosted.main(["--require-tls"])
    out, err = capsys.readouterr()
    report = _single_json_line(out)
    assert code == 0
    assert report["passed"] is True
    assert report["tls"] == "required"
    assert report["planner_created"] is False
    assert report["fixtures"] == {"count": 2, "created": 2}
    assert report["privileges"] == {
        "passed": True,
        "checks": [{"name": "a_check", "passed": True, "detail": "fine"}],
    }
    # Rotation happens to the URL's password, before the checks run.
    assert hosted_env["rotated"] == LOGIN_PASSWORD
    assert hosted_env["checks_kwargs"]["require_tls"] is True
    _assert_no_secret(out)
    _assert_no_secret(err)


def test_main_reports_not_requested_tls_without_the_flag(
    hosted_env: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert bootstrap_hosted.main([]) == 0
    report = _single_json_line(capsys.readouterr().out)
    assert report["tls"] == "not_requested"
    assert hosted_env["checks_kwargs"]["require_tls"] is False


def test_main_exits_non_zero_when_any_check_fails(
    hosted_env: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    hosted_env["results"] = [
        CheckResult("a_check", True, "fine"),
        CheckResult("b_check", False, "broken"),
    ]
    assert bootstrap_hosted.main([]) == 1
    report = _single_json_line(capsys.readouterr().out)
    assert report["passed"] is False
    assert report["privileges"]["passed"] is False


def test_main_refuses_the_initial_login_password_before_touching_the_database(
    hosted_env: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(
        "ROSTERAI_DATABASE_URL",
        f"postgresql+psycopg://shiftmind_login:shiftmind_login@{HOST}:5432/rosterai",
    )
    assert bootstrap_hosted.main([]) == 1
    out, err = capsys.readouterr()
    report = _single_json_line(out)
    assert report["failed_stage"] == "validate"
    assert report["error"] == "RefusedConfiguration"
    assert hosted_env["rotated"] is None
    _assert_no_secret(out)
    _assert_no_secret(err)


def test_a_failing_rotation_never_leaks_the_password_it_was_setting(
    hosted_env: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _explode(engine: object, password: str) -> None:
        raise RuntimeError(
            f"ALTER ROLE shiftmind_login PASSWORD '{password}' failed on {HOST}"
        )

    monkeypatch.setattr(bootstrap_hosted, "rotate_login_password", _explode)
    assert bootstrap_hosted.main([]) == 1
    out, err = capsys.readouterr()
    report = _single_json_line(out)
    assert report["failed_stage"] == "rotate"
    assert report["error"] == "RuntimeError"
    assert "ALTER ROLE" in err  # the trace is kept, only the secrets go
    _assert_no_secret(out)
    _assert_no_secret(err)
