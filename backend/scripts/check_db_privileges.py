"""Read-only proof of AD-23's database role model (Story 6.2 D4).

Each check is a named, two-sided catalog query or connection probe run as the
deployment migrator. "Could not determine" is a failure, never a pass: a check
that finds none of the roles or tables it is about reports `passed=False`.

The checks prove the ROLE model -- who owns what, who can reach whom, who is
RLS-exempt and how. Whether each RLS predicate filters the right rows is the
existing postgres suites' job, not this module's.

`detail` strings are built from catalog names only. They never carry a
connection URL, password or host, because `bootstrap_hosted` prints them to a
log stream; for the same reason a probe's exception text is reduced to its
SQLSTATE and never echoed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

RUNTIME_ROLES: Final[tuple[str, ...]] = (
    "shiftmind_login",
    "shiftmind_runtime",
    "shiftmind_lease",
)
OWNER_ROLE: Final[str] = "shiftmind_owner"
LOGIN_ROLE: Final[str] = "shiftmind_login"
# The migration's literal initial password; a hosted login must not keep it.
INITIAL_LOGIN_PASSWORD: Final[str] = "shiftmind_login"
OWNER_EXEMPT_SUFFIX: Final[str] = "_owner_exempt"

# The exact definer surface 5e2a4c9d1f70 and a2b3c4d5e6f7 hand to the owner
# (the same sets test_identity_role_boundaries.py pins).
AUTH_TABLES: Final[frozenset[str]] = frozenset({"session_index", "login_handshake"})
AUTH_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "resolve_session",
        "create_login_handshake",
        "consume_login_handshake",
        "establish_session_for_subject",
        "revoke_session",
    }
)
WORKFLOW_TABLES: Final[frozenset[str]] = frozenset({"job_queue"})
WORKFLOW_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"lease_next_job", "renew_job_lease"}
)
TENANT_SCHEMAS: Final[tuple[str, ...]] = ("public", "workflow")
# AD-23's control table: keyed by site_id, but reached only through the
# definer functions, so it is privilege-guarded rather than RLS-guarded.
RLS_EXCLUDED: Final[frozenset[tuple[str, str]]] = frozenset({("auth", "session_index")})
TABLE_PRIVILEGES: Final[tuple[str, ...]] = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
_PROBE_TIMEOUT_S: Final[int] = 10
# 28P01 invalid_password, 28000 invalid_authorization_specification.
_AUTH_SQLSTATES: Final[frozenset[str]] = frozenset({"28P01", "28000"})


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _names(rows: list[str]) -> str:
    return ", ".join(sorted(rows)) if rows else "none"


def _runtime_roles_are_not_privileged(connection: Connection) -> CheckResult:
    name = "runtime_roles_are_not_privileged"
    rows = connection.execute(
        text(
            "SELECT rolname, rolsuper, rolbypassrls, rolinherit FROM pg_roles "
            "WHERE rolname = ANY(:roles)"
        ),
        {"roles": list(RUNTIME_ROLES)},
    ).all()
    missing = sorted(set(RUNTIME_ROLES) - {row.rolname for row in rows})
    if missing:
        return CheckResult(name, False, f"could not determine: missing {_names(missing)}")
    bad = [
        f"{row.rolname}({attr})"
        for row in rows
        for attr, value in (
            ("super", row.rolsuper),
            ("bypassrls", row.rolbypassrls),
            ("inherit", row.rolinherit),
        )
        if value
    ]
    return CheckResult(name, not bad, f"privileged attributes: {_names(bad)}")


def _runtime_roles_own_nothing(connection: Connection) -> CheckResult:
    rows = connection.execute(
        text(
            "SELECT 'relation ' || c.oid::regclass::text AS object FROM pg_class AS c "
            "  JOIN pg_roles AS r ON r.oid = c.relowner WHERE r.rolname = ANY(:roles) "
            "UNION ALL SELECT 'function ' || p.oid::regprocedure::text FROM pg_proc AS p "
            "  JOIN pg_roles AS r ON r.oid = p.proowner WHERE r.rolname = ANY(:roles) "
            "UNION ALL SELECT 'schema ' || n.nspname FROM pg_namespace AS n "
            "  JOIN pg_roles AS r ON r.oid = n.nspowner WHERE r.rolname = ANY(:roles) "
            "UNION ALL SELECT 'type ' || t.oid::regtype::text FROM pg_type AS t "
            "  JOIN pg_roles AS r ON r.oid = t.typowner WHERE r.rolname = ANY(:roles)"
        ),
        {"roles": list(RUNTIME_ROLES)},
    ).scalars().all()
    return CheckResult(
        "runtime_roles_own_nothing", not rows, f"owned by a runtime role: {_names(list(rows))}"
    )


def _runtime_roles_cannot_reach_privileged_roles(connection: Connection) -> CheckResult:
    name = "runtime_roles_cannot_reach_privileged_roles"
    targets = connection.execute(
        text(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname IN (:owner, current_user, 'rds_superuser')"
        ),
        {"owner": OWNER_ROLE},
    ).scalars().all()
    if OWNER_ROLE not in targets:
        return CheckResult(name, False, f"could not determine: {OWNER_ROLE} is missing")
    rows = connection.execute(
        text(
            "SELECT r.rolname AS runtime, t.rolname AS target FROM pg_roles AS r "
            "CROSS JOIN pg_roles AS t "
            "WHERE r.rolname = ANY(:roles) AND t.rolname = ANY(:targets) "
            "AND pg_has_role(r.oid, t.oid, 'MEMBER')"
        ),
        {"roles": list(RUNTIME_ROLES), "targets": list(targets)},
    ).all()
    reached = [f"{row.runtime}->{row.target}" for row in rows]
    return CheckResult(
        name,
        not reached,
        f"checked {_names(list(targets))}; reachable: {_names(reached)}",
    )


def _owner_is_unprivileged_and_unreachable(connection: Connection) -> CheckResult:
    name = "owner_is_unprivileged_and_unreachable"
    owner = connection.execute(
        text(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = :owner"
        ),
        {"owner": OWNER_ROLE},
    ).one_or_none()
    if owner is None:
        return CheckResult(name, False, f"could not determine: {OWNER_ROLE} is missing")
    bad = [
        attr
        for attr, value in (
            ("login", owner.rolcanlogin),
            ("super", owner.rolsuper),
            ("bypassrls", owner.rolbypassrls),
        )
        if value
    ]
    # Superusers can SET ROLE to anything and are excluded; on RDS the
    # platform's own superuser is `rdsadmin`, which the operator never holds.
    setters = connection.execute(
        text(
            "SELECT r.rolname FROM pg_roles AS r "
            "WHERE NOT r.rolsuper AND r.rolname <> :owner "
            "AND r.rolname <> current_user "
            "AND pg_has_role(r.oid, :owner, 'SET')"
        ),
        {"owner": OWNER_ROLE},
    ).scalars().all()
    return CheckResult(
        name,
        not bad and not setters,
        f"owner attributes: {_names(bad)}; other roles able to SET ROLE: {_names(list(setters))}",
    )


def _owner_holds_the_definer_objects(connection: Connection) -> CheckResult:
    def owned_tables(schema: str) -> dict[str, str]:
        rows = connection.execute(
            text(
                "SELECT tablename AS name, tableowner AS owner FROM pg_tables "
                "WHERE schemaname = :schema"
            ),
            {"schema": schema},
        ).all()
        return {row.name: row.owner for row in rows}

    def owned_functions(schema: str) -> dict[str, str]:
        rows = connection.execute(
            text(
                "SELECT p.proname AS name, pg_get_userbyid(p.proowner) AS owner "
                "FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                "WHERE n.nspname = :schema"
            ),
            {"schema": schema},
        ).all()
        return {row.name: row.owner for row in rows}

    auth_tables = owned_tables("auth")
    auth_functions = owned_functions("auth")
    workflow_tables = owned_tables("workflow")
    workflow_functions = owned_functions("workflow")
    problems: list[str] = []
    # auth is the owner's alone: the exact sets, so an extra object fails too.
    if set(auth_tables) != AUTH_TABLES:
        problems.append(f"auth tables are {_names(list(auth_tables))}")
    if set(auth_functions) != AUTH_FUNCTIONS:
        problems.append(f"auth functions are {_names(list(auth_functions))}")
    for label, objects, expected in (
        ("auth", auth_tables, AUTH_TABLES),
        ("auth", auth_functions, AUTH_FUNCTIONS),
        ("workflow", workflow_tables, WORKFLOW_TABLES),
        ("workflow", workflow_functions, WORKFLOW_FUNCTIONS),
    ):
        for object_name in sorted(expected):
            actual = objects.get(object_name)
            if actual != OWNER_ROLE:
                problems.append(f"{label}.{object_name} owner={actual or 'missing'}")
    return CheckResult(
        "owner_holds_the_definer_objects", not problems, f"problems: {_names(problems)}"
    )


def _rls_is_forced_on_every_tenant_table(connection: Connection) -> CheckResult:
    name = "rls_is_forced_on_every_tenant_table"
    rows = connection.execute(
        text(
            "SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "JOIN pg_attribute AS a ON a.attrelid = c.oid "
            "WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(:schemas) "
            "AND a.attname = 'site_id' AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"schemas": list(TENANT_SCHEMAS)},
    ).all()
    tables = [row for row in rows if (row.nspname, row.relname) not in RLS_EXCLUDED]
    if not tables:
        return CheckResult(name, False, "could not determine: no tenant table found")
    unforced = [
        f"{row.nspname}.{row.relname}"
        for row in tables
        if not (row.relrowsecurity and row.relforcerowsecurity)
    ]
    return CheckResult(
        name, not unforced, f"{len(tables)} tenant tables; not forced: {_names(unforced)}"
    )


def _every_rls_table_has_an_owner_exempt_policy(connection: Connection) -> CheckResult:
    name = "every_rls_table_has_an_owner_exempt_policy"
    tables = connection.execute(
        text(
            "SELECT n.nspname, c.relname FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE c.relrowsecurity AND c.relkind IN ('r', 'p')"
        )
    ).all()
    if not tables:
        return CheckResult(name, False, "could not determine: no RLS table found")
    policies = {
        (row.schemaname, row.tablename): row
        for row in connection.execute(
            text(
                "SELECT schemaname, tablename, roles::text[] AS roles, permissive, "
                "cmd, qual, with_check FROM pg_policies "
                "WHERE policyname = tablename || :suffix"
            ),
            {"suffix": OWNER_EXEMPT_SUFFIX},
        ).all()
    }
    problems: list[str] = []
    for table in tables:
        key = (table.nspname, table.relname)
        policy = policies.get(key)
        label = f"{table.nspname}.{table.relname}"
        if policy is None:
            problems.append(f"{label} has none")
        elif (
            set(policy.roles) != {OWNER_ROLE}
            or policy.permissive != "PERMISSIVE"
            or policy.cmd != "ALL"
            or policy.qual != "true"
            or policy.with_check != "true"
        ):
            problems.append(f"{label} is not exactly the owner exemption")
    return CheckResult(name, not problems, f"{len(tables)} RLS tables; problems: {_names(problems)}")


def _runtime_roles_have_no_auth_table_privileges(connection: Connection) -> CheckResult:
    name = "runtime_roles_have_no_auth_table_privileges"
    tables = [f"auth.{table}" for table in sorted(AUTH_TABLES)]
    present = connection.execute(
        text("SELECT count(*) FROM pg_tables WHERE schemaname = 'auth' AND tablename = ANY(:t)"),
        {"t": sorted(AUTH_TABLES)},
    ).scalar_one()
    if present != len(tables):
        return CheckResult(name, False, "could not determine: an auth table is missing")
    held = connection.execute(
        text(
            "SELECT r.role || ' ' || p.priv || ' ' || t.tbl FROM unnest(CAST(:roles AS text[])) AS r(role) "
            "CROSS JOIN unnest(CAST(:privs AS text[])) AS p(priv) "
            "CROSS JOIN unnest(CAST(:tables AS text[])) AS t(tbl) "
            "WHERE has_table_privilege(r.role, t.tbl, p.priv)"
        ),
        {"roles": list(RUNTIME_ROLES), "privs": list(TABLE_PRIVILEGES), "tables": tables},
    ).scalars().all()
    return CheckResult(name, not held, f"held: {_names(list(held))}")


def _sqlstate(exc: OperationalError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def _probe(url: URL) -> tuple[str | None, str | None]:
    """Connect once. Return (current_user, None) or (None, failure class)."""
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": _PROBE_TIMEOUT_S},
    )
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT current_user")).scalar_one(), None
    except OperationalError as exc:
        message = str(exc.orig).lower()
        state = _sqlstate(exc)
        if state in _AUTH_SQLSTATES or "password authentication failed" in message:
            return None, "authentication"
        if "no encryption" in message or "pg_hba" in message:
            return None, "pg_hba_no_encryption"
        return None, f"other({state or 'no sqlstate'})"
    finally:
        engine.dispose()


def _login_uses_the_rotated_password(login_url: URL) -> CheckResult:
    name = "login_uses_the_rotated_password"
    if login_url.username != LOGIN_ROLE:
        return CheckResult(name, False, f"could not determine: URL user is not {LOGIN_ROLE}")
    user, failure = _probe(login_url)
    positive = user == LOGIN_ROLE
    _, stale_failure = _probe(login_url.set(password=INITIAL_LOGIN_PASSWORD))
    negative = stale_failure == "authentication"
    return CheckResult(
        name,
        positive and negative,
        f"configured password connects: {positive} ({failure or 'ok'}); "
        f"initial password refused: {negative} ({stale_failure or 'it connected'})",
    )


def _tls_is_required(connection: Connection, migrator_url: URL) -> CheckResult:
    encrypted = connection.execute(
        text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    ).scalar_one_or_none()
    plain_query = {**migrator_url.query, "sslmode": "disable"}
    user, failure = _probe(migrator_url.set(query=plain_query))
    refused = user is None and failure == "pg_hba_no_encryption"
    return CheckResult(
        "tls_is_required",
        bool(encrypted) and refused,
        f"this session encrypted: {bool(encrypted)}; "
        f"plaintext connection refused by pg_hba: {refused} ({failure or 'it connected'})",
    )


def run_checks(
    connection: Connection,
    *,
    login_url: URL | str | None = None,
    migrator_url: URL | str | None = None,
    require_tls: bool = False,
) -> list[CheckResult]:
    """Run D4's checks on `connection`, which must be the migrator's.

    The catalog checks all read through `connection`, so a caller can inject a
    violation inside a transaction and roll it back. `login_url` adds the
    rotated-password probe; `require_tls` (which needs `migrator_url`) adds
    the TLS probe. Both probes open their own short connections.
    """
    results = [
        _runtime_roles_are_not_privileged(connection),
        _runtime_roles_own_nothing(connection),
        _runtime_roles_cannot_reach_privileged_roles(connection),
        _owner_is_unprivileged_and_unreachable(connection),
        _owner_holds_the_definer_objects(connection),
        _rls_is_forced_on_every_tenant_table(connection),
        _every_rls_table_has_an_owner_exempt_policy(connection),
        _runtime_roles_have_no_auth_table_privileges(connection),
    ]
    if login_url is not None:
        results.append(_login_uses_the_rotated_password(make_url(login_url)))
    if require_tls:
        if migrator_url is None:
            results.append(
                CheckResult("tls_is_required", False, "could not determine: no migrator URL")
            )
        else:
            results.append(_tls_is_required(connection, make_url(migrator_url)))
    return results


__all__ = ["CheckResult", "run_checks"]
