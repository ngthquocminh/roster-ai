"""Owned OIDC seam for server-side BFF authentication."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class OidcIdentity:
    """The provider-neutral identity claims the application is allowed to use."""

    subject: str
    email: str
    issuer: str
    expires_at: datetime


class OidcProvider(Protocol):
    async def authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str: ...

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        nonce: str,
    ) -> OidcIdentity: ...

    def end_session_url(self, post_logout_redirect_uri: str) -> str | None: ...


def create_provider(name: str, *, settings) -> OidcProvider:
    """Create a configured OIDC adapter without leaking vendor types."""
    if name == "fake":
        from adapters.oidc.fake import FakeOidcProvider

        return FakeOidcProvider(
            issuer=settings.oidc_issuer,
            client_id=settings.oidc_client_id,
        )
    if name == "cognito":
        from adapters.cognito.oidc import CognitoOidcProvider

        return CognitoOidcProvider(
            issuer=settings.oidc_issuer,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
        )
    raise ValueError(
        f"Unknown OIDC provider: {name!r}. Available: ['fake', 'cognito']"
    )
