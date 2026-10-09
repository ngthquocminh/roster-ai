"""Story 6.2 D2/D4: the role model holds on the governed database, and each
privilege check reddens on a synthetic violation of its own family.

Every violation is injected inside a transaction that the test rolls back,
and `run_checks` reads through that same connection. Roles are
cluster-global, so nothing here may outlive its test.

The governed database is migrated by the local superuser. The NON-superuser
proof (the RDS master's shape) needs a fresh cluster and lives in
infra/scripts/bootstrap-nonsuperuser.sh, not here (Story 6.2 F17).
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, text

from scripts.check_db_privileges import CheckResult, run_checks

pytestmark = pytest.mark.postgres

CATALOG_CHECKS = {
    "runtime_roles_are_not_privileged",
    "runtime_roles_own_nothing",
    "runtime_roles_cannot_reach_privileged_roles",
    "owner_is_unprivileged_and_unreachable",
    "owner_holds_the_definer_objects",
    "rls_is_forced_on_every_tenant_table",
    "every_rls_table_has_an_owner_exempt_policy",
    "runtime_roles_have_no_auth_table_privileges",
}


@pytest.fixture
def rolled_back(governed_postgres_engine) -> Iterator[Connection]:
    with governed_postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


def _failed(results: list[CheckResult]) -> set[str]:
    return {result.name for result in results if not result.passed}


def test_every_catalog_check_passes_on_the_governed_database(rolled_back: Connection) -> None:
    results = run_checks(rolled_back)
    assert {result.name for result in results} == CATALOG_CHECKS
    assert _failed(results) == set(), [r for r in results if not r.passed]


def test_every_rls_table_has_exactly_the_owner_exempt_policy(rolled_back: Connection) -> None:
    """D2.2's coverage, read straight from the catalog (independent of D4)."""
    rows = rolled_back.execute(
        text(
            "SELECT n.nspname || '.' || c.relname AS name, "
            "  (SELECT p.roles::text[] FROM pg_policies AS p "
            "   WHERE p.schemaname = n.nspname AND p.tablename = c.relname "
            "   AND p.policyname = c.relname || '_owner_exempt') AS roles "
            "FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE c.relrowsecurity AND c.relkind IN ('r', 'p')"
        )
    ).all()
    # The tables F6 seeds into and the leasing table must all be covered.
    names = {row.name for row in rows}
    assert {
        "public.site",
        "public.scenario",
        "public.scenario_version",
        "public.fixture_lineage",
        "public.membership",
        "workflow.job_queue",
    } <= names
    assert {row.name: row.roles for row in rows if row.roles != ["shiftmind_owner"]} == {}


def test_coverage_reddens_on_an_rls_table_without_its_policy(rolled_back: Connection) -> None:
    rolled_back.execute(text("CREATE TABLE public.zz_unexempt (site_id uuid)"))
    rolled_back.execute(text("ALTER TABLE public.zz_unexempt ENABLE ROW LEVEL SECURITY"))
    rolled_back.execute(text("ALTER TABLE public.zz_unexempt FORCE ROW LEVEL SECURITY"))
    assert _failed(run_checks(rolled_back)) == {"every_rls_table_has_an_owner_exempt_policy"}


def test_coverage_reddens_on_a_widened_owner_exempt_policy(rolled_back: Connection) -> None:
    rolled_back.execute(
        text("ALTER POLICY membership_owner_exempt ON public.membership TO shiftmind_owner, shiftmind_runtime")
    )
    assert _failed(run_checks(rolled_back)) == {"every_rls_table_has_an_owner_exempt_policy"}


@pytest.mark.parametrize(
    ("violation", "expected"),
    [
        (
            ["ALTER ROLE shiftmind_lease BYPASSRLS"],
            {"runtime_roles_are_not_privileged"},
        ),
        (
            ["ALTER ROLE shiftmind_login INHERIT"],
            {"runtime_roles_are_not_privileged"},
        ),
        (
            [
                "CREATE TABLE public.zz_runtime_owned (id int)",
                "ALTER TABLE public.zz_runtime_owned OWNER TO shiftmind_runtime",
            ],
            {"runtime_roles_own_nothing"},
        ),
        (
            ["GRANT shiftmind_owner TO shiftmind_lease"],
            {"runtime_roles_cannot_reach_privileged_roles", "owner_is_unprivileged_and_unreachable"},
        ),
        (
            ["ALTER ROLE shiftmind_owner BYPASSRLS"],
            {"owner_is_unprivileged_and_unreachable"},
        ),
        (
            ["ALTER ROLE shiftmind_owner LOGIN"],
            {"owner_is_unprivileged_and_unreachable"},
        ),
        (
            ["ALTER FUNCTION auth.revoke_session(text) OWNER TO CURRENT_USER"],
            {"owner_holds_the_definer_objects"},
        ),
        (
            ["ALTER FUNCTION workflow.renew_job_lease(uuid, bigint, integer) OWNER TO CURRENT_USER"],
            {"owner_holds_the_definer_objects"},
        ),
        (
            ["ALTER TABLE public.scenario NO FORCE ROW LEVEL SECURITY"],
            {"rls_is_forced_on_every_tenant_table"},
        ),
        (
            ["GRANT SELECT ON auth.session_index TO shiftmind_runtime"],
            {"runtime_roles_have_no_auth_table_privileges"},
        ),
        (
            ["GRANT DELETE ON auth.login_handshake TO shiftmind_login"],
            {"runtime_roles_have_no_auth_table_privileges"},
        ),
    ],
)
def test_each_check_family_reddens_on_its_synthetic_violation(
    rolled_back: Connection, violation: list[str], expected: set[str]
) -> None:
    for statement in violation:
        rolled_back.execute(text(statement))
    assert _failed(run_checks(rolled_back)) == expected


def test_login_check_reddens_while_the_initial_password_still_works(
    governed_postgres_engine, rolled_back: Connection
) -> None:
    """Locally shiftmind_login keeps the migration's literal password (the
    cluster is shared, so this test must not rotate it): exactly the state
    D3's rotation exists to remove. The green side is proved on a fresh
    cluster by bootstrap-nonsuperuser.sh."""
    login_url = governed_postgres_engine.url.set(
        username="shiftmind_login", password="shiftmind_login"
    )
    results = {r.name: r for r in run_checks(rolled_back, login_url=login_url)}
    login = results["login_uses_the_rotated_password"]
    assert login.passed is False
    assert "configured password connects: True" in login.detail
    assert "initial password refused: False" in login.detail


def test_tls_check_reddens_on_an_unencrypted_local_session(
    governed_postgres_engine, rolled_back: Connection
) -> None:
    results = {
        r.name: r
        for r in run_checks(
            rolled_back,
            migrator_url=governed_postgres_engine.url,
            require_tls=True,
        )
    }
    assert results["tls_is_required"].passed is False
    assert "this session encrypted: False" in results["tls_is_required"].detail


def test_details_never_carry_the_url_or_password(
    governed_postgres_engine, rolled_back: Connection
) -> None:
    url = governed_postgres_engine.url
    results = run_checks(
        rolled_back,
        login_url=url.set(username="shiftmind_login", password="shiftmind_login"),
        migrator_url=url,
        require_tls=True,
    )
    # Locally the password equals a role name (`rosterai`), which details may
    # legitimately name, so the guard is on URL shape and host. The JSON line's
    # password guard is test_bootstrap_hosted.py, with distinctive passwords.
    for result in results:
        assert "://" not in result.detail and "@" not in result.detail
        assert str(url.host) not in result.detail
