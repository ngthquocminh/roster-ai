"""Synchronous PostgreSQL persistence adapter for BFF identity sessions.

Every method here goes exclusively through the `auth.*` SECURITY DEFINER
functions installed by the identity migration (see AD-23) — never direct
table DML. `shiftmind_runtime` (the role every connection downgrades to,
see `_run`) has no grants on `auth.session_index` / `auth.login_handshake`
at all; only `EXECUTE` on these functions. This is what makes it safe for
this adapter to run under the API's own restricted `shiftmind_login`
connection instead of a privileged one.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, Engine, create_engine, text

from application.ports.session import (
    ActiveIdentity,
    LoginHandshake,
    ResolvedSession,
)


def _downgrade(connection: Connection) -> None:
    connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")


class PostgresIdentitySessionStore:
    def __init__(
        self,
        database_url: str,
        *,
        engine: Engine | None = None,
    ) -> None:
        self._engine = engine or create_engine(database_url, hide_parameters=True)

    def create_login_handshake(self, handshake: LoginHandshake) -> None:
        with self._engine.begin() as connection:
            _downgrade(connection)
            connection.execute(
                text(
                    "SELECT auth.create_login_handshake("
                    ":state, :nonce, :code_verifier, :redirect_target, :expires_at"
                    ")"
                ),
                {
                    "state": handshake.state,
                    "nonce": handshake.nonce,
                    "code_verifier": handshake.code_verifier,
                    "redirect_target": handshake.redirect_target,
                    "expires_at": handshake.expires_at,
                },
            )

    def consume_login_handshake(self, state: str) -> LoginHandshake | None:
        with self._engine.begin() as connection:
            _downgrade(connection)
            row = connection.execute(
                text(
                    "SELECT state, nonce, code_verifier, redirect_target, expires_at "
                    "FROM auth.consume_login_handshake(:state)"
                ),
                {"state": state},
            ).one_or_none()
        if row is None:
            return None
        return LoginHandshake(
            state=row.state,
            nonce=row.nonce,
            code_verifier=row.code_verifier,
            redirect_target=row.redirect_target,
            expires_at=row.expires_at,
        )

    def establish_session_for_subject(
        self,
        *,
        subject: str,
        session_token_hash: str,
        csrf_token_hash: str,
        expires_at: datetime,
    ) -> ActiveIdentity | None:
        with self._engine.begin() as connection:
            _downgrade(connection)
            row = connection.execute(
                text(
                    "SELECT app_user_id, site_id "
                    "FROM auth.establish_session_for_subject("
                    ":subject, :session_token_hash, :csrf_token_hash, :expires_at"
                    ")"
                ),
                {
                    "subject": subject,
                    "session_token_hash": session_token_hash,
                    "csrf_token_hash": csrf_token_hash,
                    "expires_at": expires_at,
                },
            ).one_or_none()
        if row is None:
            return None
        return ActiveIdentity(
            app_user_id=row.app_user_id,
            site_id=row.site_id,
        )

    def resolve_session(self, session_token_hash: str) -> ResolvedSession | None:
        with self._engine.connect() as connection:
            _downgrade(connection)
            row = connection.execute(
                text(
                    "SELECT app_user_id, site_id, csrf_token_hash, expires_at "
                    "FROM auth.resolve_session(:token_hash)"
                ),
                {"token_hash": session_token_hash},
            ).one_or_none()
        if row is None:
            return None
        return ResolvedSession(
            app_user_id=row.app_user_id,
            site_id=row.site_id,
            csrf_token_hash=row.csrf_token_hash,
            expires_at=row.expires_at,
        )

    def revoke_session(self, session_token_hash: str) -> bool:
        with self._engine.begin() as connection:
            _downgrade(connection)
            revoked = connection.execute(
                text("SELECT auth.revoke_session(:token_hash)"),
                {"token_hash": session_token_hash},
            ).scalar_one()
        return bool(revoked)
