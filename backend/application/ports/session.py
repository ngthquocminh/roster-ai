"""Application-session persistence port for the authentication BFF."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class LoginHandshake:
    state: str
    nonce: str
    code_verifier: str
    redirect_target: str
    expires_at: datetime


@dataclass(frozen=True)
class ActiveIdentity:
    app_user_id: UUID
    site_id: UUID


@dataclass(frozen=True)
class ResolvedSession:
    app_user_id: UUID
    site_id: UUID
    csrf_token_hash: str
    expires_at: datetime


class IdentitySessionStore(Protocol):
    def create_login_handshake(self, handshake: LoginHandshake) -> None: ...

    def consume_login_handshake(self, state: str) -> LoginHandshake | None: ...

    def establish_session_for_subject(
        self,
        *,
        subject: str,
        session_token_hash: str,
        csrf_token_hash: str,
        expires_at: datetime,
    ) -> ActiveIdentity | None:
        """Atomically resolve `subject`'s active identity and create its
        session in one step. Returns None (no session created) if the
        subject has no provisioned, active membership — the caller never
        supplies app_user_id/site_id itself, so it cannot establish a
        session for an identity other than the one PostgreSQL resolved."""
        ...

    def resolve_session(self, session_token_hash: str) -> ResolvedSession | None: ...

    def revoke_session(self, session_token_hash: str) -> bool: ...
