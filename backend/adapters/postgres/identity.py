"""Synchronous PostgreSQL persistence adapter for BFF identity sessions."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, create_engine, func, select, text, update

from adapters.postgres.schema import (
    app_user,
    login_handshake,
    membership,
    session_index,
)
from application.ports.session import (
    ActiveIdentity,
    LoginHandshake,
    ResolvedSession,
)


class PostgresIdentitySessionStore:
    def __init__(
        self,
        database_url: str,
        *,
        engine: Engine | None = None,
    ) -> None:
        self._engine = engine or create_engine(database_url)

    def create_login_handshake(self, handshake: LoginHandshake) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                login_handshake.insert().values(
                    state=handshake.state,
                    nonce=handshake.nonce,
                    code_verifier=handshake.code_verifier,
                    redirect_target=handshake.redirect_target,
                    expires_at=handshake.expires_at,
                )
            )

    def consume_login_handshake(self, state: str) -> LoginHandshake | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                update(login_handshake)
                .where(
                    login_handshake.c.state == state,
                    login_handshake.c.consumed_at.is_(None),
                    login_handshake.c.expires_at > func.now(),
                )
                .values(consumed_at=func.now())
                .returning(
                    login_handshake.c.state,
                    login_handshake.c.nonce,
                    login_handshake.c.code_verifier,
                    login_handshake.c.redirect_target,
                    login_handshake.c.expires_at,
                )
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

    def resolve_active_identity(self, subject: str) -> ActiveIdentity | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    app_user.c.id.label("app_user_id"),
                    membership.c.site_id,
                )
                .join(
                    membership,
                    membership.c.app_user_id == app_user.c.id,
                )
                .where(
                    app_user.c.idp_subject == subject,
                    app_user.c.disabled_at.is_(None),
                    membership.c.revoked_at.is_(None),
                )
                .limit(1)
            ).one_or_none()
        if row is None:
            return None
        return ActiveIdentity(
            app_user_id=row.app_user_id,
            site_id=row.site_id,
        )

    def create_session(
        self,
        *,
        session_token_hash: str,
        csrf_token_hash: str,
        app_user_id: UUID,
        site_id: UUID,
        expires_at: datetime,
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                session_index.insert().values(
                    session_token_hash=session_token_hash,
                    csrf_token_hash=csrf_token_hash,
                    app_user_id=app_user_id,
                    site_id=site_id,
                    expires_at=expires_at,
                )
            )

    def resolve_session(self, session_token_hash: str) -> ResolvedSession | None:
        with self._engine.connect() as connection:
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
            revoked_id = connection.execute(
                update(session_index)
                .where(
                    session_index.c.session_token_hash == session_token_hash,
                    session_index.c.revoked_at.is_(None),
                )
                .values(revoked_at=func.now())
                .returning(session_index.c.id)
            ).scalar_one_or_none()
        return revoked_id is not None
