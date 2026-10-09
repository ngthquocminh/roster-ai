"""One hosted bootstrap entry point: migrate, seed, rotate, prove (Story 6.2 D3).

`python -m scripts.bootstrap_hosted [--require-tls]` runs, in order:

1. `bootstrap_local` unchanged: migrate, import fixtures, provision the seed
   planner, all through `ROSTERAI_PROVISIONING_DATABASE_URL`.
2. One `ALTER ROLE shiftmind_login PASSWORD ...` to the password inside
   `ROSTERAI_DATABASE_URL`. The migration creates that login with a literal
   password; a hosted database must never keep it.
3. `check_db_privileges.run_checks`, with the TLS probe when asked.
4. Exactly one JSON line on stdout, then exit 0 only when everything passed.

It is idempotent: a second run replays the fixtures, reports
`planner_created: false`, re-asserts the same password and passes the same
checks. Rotation is therefore not scheduled; it happens when the deployment
changes the URL secret and runs this again.

The JSON line is the task's only output that anyone reads, and it lands in a
log stream, so it is built from counts, booleans and catalog names only. A
failure is reported as a stage and an exception class; the exception text goes
to stderr with every password and the host replaced, because the ALTER ROLE
statement embeds the password and a connection error names the host.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict
from typing import Any, Final

from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url

from scripts.bootstrap_local import BootstrapResult, bootstrap_local
from scripts.check_db_privileges import INITIAL_LOGIN_PASSWORD, LOGIN_ROLE, run_checks
from settings import Settings, default_settings

REDACTED: Final[str] = "<redacted>"


class RefusedConfiguration(ValueError):
    """The hosted URLs would leave the login on a known or wrong credential."""


def validate_login_url(database_url: str) -> URL:
    """Refuse a login URL whose user or password defeats the rotation."""
    url = make_url(database_url)
    if url.username != LOGIN_ROLE:
        raise RefusedConfiguration(
            f"ROSTERAI_DATABASE_URL must authenticate as {LOGIN_ROLE}"
        )
    if not url.password:
        raise RefusedConfiguration("ROSTERAI_DATABASE_URL carries no password")
    if url.password == INITIAL_LOGIN_PASSWORD:
        raise RefusedConfiguration(
            "ROSTERAI_DATABASE_URL still uses the migration's initial login password"
        )
    return url


def rotate_login_password(engine: Engine, password: str) -> None:
    """Set the login's password; the literal is composed by psycopg, not f-strings."""
    statement = sql.SQL("ALTER ROLE {} PASSWORD {}").format(
        sql.Identifier(LOGIN_ROLE), sql.Literal(password)
    )
    with engine.begin() as connection:
        driver_connection = connection.connection.driver_connection
        with driver_connection.cursor() as cursor:
            cursor.execute(statement)


def redact(message: str, secrets: list[str]) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        message = message.replace(secret, REDACTED)
    return message


def _secrets_of(settings: Settings) -> list[str]:
    values: list[str] = []
    for raw in (settings.database_url, settings.provisioning_database_url):
        try:
            url = make_url(raw)
        except Exception:  # an unparseable URL is itself redacted whole
            values.append(raw)
            continue
        values.extend(v for v in (url.password, url.host, raw) if v)
    return values


def build_report(
    *,
    bootstrap: BootstrapResult | None,
    require_tls: bool,
    checks: list[dict[str, Any]],
    stage: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    passed = error is None and bool(checks) and all(c["passed"] for c in checks)
    report: dict[str, Any] = {
        "passed": passed,
        "fixtures": None
        if bootstrap is None
        else {
            "count": len(bootstrap.fixtures),
            "created": sum(1 for f in bootstrap.fixtures if f.created),
        },
        "planner_created": None if bootstrap is None else bootstrap.planner.created,
        "tls": "required" if require_tls else "not_requested",
        "privileges": {
            "passed": bool(checks) and all(c["passed"] for c in checks),
            "checks": checks,
        },
    }
    if error is not None:
        report["failed_stage"] = stage
        report["error"] = error
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--require-tls",
        action="store_true",
        help="also prove this session is encrypted and a plaintext one is refused",
    )
    args = parser.parse_args(argv)

    settings = default_settings()
    secrets = _secrets_of(settings)
    bootstrap: BootstrapResult | None = None
    checks: list[dict[str, Any]] = []
    stage = "validate"
    try:
        login_url = validate_login_url(settings.database_url)
        engine = create_engine(settings.provisioning_database_url, hide_parameters=True)
        try:
            stage = "bootstrap"
            bootstrap = bootstrap_local(settings=settings, engine=engine)
            stage = "rotate"
            rotate_login_password(engine, login_url.password or "")
            stage = "checks"
            with engine.connect() as connection:
                results = run_checks(
                    connection,
                    login_url=login_url,
                    migrator_url=settings.provisioning_database_url,
                    require_tls=args.require_tls,
                )
            checks = [asdict(result) for result in results]
        finally:
            engine.dispose()
    except Exception as exc:  # one JSON line on every path, then non-zero
        print(redact(traceback.format_exc(), secrets), file=sys.stderr)
        report = build_report(
            bootstrap=bootstrap,
            require_tls=args.require_tls,
            checks=checks,
            stage=stage,
            error=type(exc).__name__,
        )
        print(json.dumps(report, sort_keys=True))
        return 1

    report = build_report(bootstrap=bootstrap, require_tls=args.require_tls, checks=checks)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "RefusedConfiguration",
    "build_report",
    "main",
    "redact",
    "rotate_login_password",
    "validate_login_url",
]
