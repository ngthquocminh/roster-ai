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

    def resolve_active_identity(self, subject: str) -> ActiveIdentity | None: ...

    def create_session(
        self,
        *,
        session_token_hash: str,
        csrf_token_hash: str,
        app_user_id: UUID,
        site_id: UUID,
        expires_at: datetime,
    ) -> None: ...

    def resolve_session(self, session_token_hash: str) -> ResolvedSession | None: ...

    def revoke_session(self, session_token_hash: str) -> bool: ...
