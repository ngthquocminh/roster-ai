"""Authlib-based Cognito OIDC authorization-code adapter."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import jwt
from authlib.jose.errors import JoseError

from application.ports.identity import OidcIdentity


_HTTP_TIMEOUT_S = 10.0
# Cognito rotates signing keys infrequently and without notice; refetching
# hourly (plus the kid-miss fallback in exchange_code) keeps us from
# rejecting every sign-in for the rest of the process lifetime after a
# rotation, without hammering the discovery/JWKS endpoints per request.
_METADATA_TTL = timedelta(hours=1)


class CognitoOidcProvider:
    """Validate Cognito metadata and ID tokens without browser-side state."""

    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._transport = transport
        self._metadata: dict[str, Any] | None = None
        self._metadata_fetched_at: datetime | None = None
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: datetime | None = None
        self._discovery_lock = asyncio.Lock()

    def _is_fresh(self, fetched_at: datetime | None) -> bool:
        return (
            fetched_at is not None
            and datetime.now(timezone.utc) - fetched_at < _METADATA_TTL
        )

    async def _load_metadata(self) -> dict[str, Any]:
        if self._metadata is not None and self._is_fresh(self._metadata_fetched_at):
            return self._metadata
        async with self._discovery_lock:
            if self._metadata is None or not self._is_fresh(
                self._metadata_fetched_at
            ):
                async with httpx.AsyncClient(
                    transport=self._transport, timeout=_HTTP_TIMEOUT_S
                ) as client:
                    response = await client.get(
                        f"{self.issuer}/.well-known/openid-configuration"
                    )
                    response.raise_for_status()
                    metadata = response.json()
                if metadata.get("issuer") != self.issuer:
                    raise ValueError("OIDC discovery issuer does not match")
                self._metadata = metadata
                self._metadata_fetched_at = datetime.now(timezone.utc)
        return self._metadata

    async def _load_jwks(self, *, force_refresh: bool = False) -> dict[str, Any]:
        if (
            not force_refresh
            and self._jwks is not None
            and self._is_fresh(self._jwks_fetched_at)
        ):
            return self._jwks
        metadata = await self._load_metadata()
        async with self._discovery_lock:
            if (
                force_refresh
                or self._jwks is None
                or not self._is_fresh(self._jwks_fetched_at)
            ):
                async with httpx.AsyncClient(
                    transport=self._transport, timeout=_HTTP_TIMEOUT_S
                ) as client:
                    response = await client.get(metadata["jwks_uri"])
                    response.raise_for_status()
                    self._jwks = response.json()
                    self._jwks_fetched_at = datetime.now(timezone.utc)
        return self._jwks

    async def authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        metadata = await self._load_metadata()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scope": "openid email",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        nonce: str,
    ) -> OidcIdentity:
        metadata = await self._load_metadata()
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=redirect_uri,
            code_challenge_method="S256",
            transport=self._transport,
            timeout=_HTTP_TIMEOUT_S,
        )
        async with client:
            token = await client.fetch_token(
                metadata["token_endpoint"],
                code=code,
                code_verifier=code_verifier,
            )
        raw_id_token = token.get("id_token")
        if not raw_id_token:
            raise ValueError("OIDC token response omitted id_token")

        claims_options = {
            "iss": {"essential": True, "value": self.issuer},
            "sub": {"essential": True},
            "aud": {"essential": True, "value": self.client_id},
            "exp": {"essential": True},
            "nonce": {"essential": True, "value": nonce},
        }
        try:
            claims = jwt.decode(
                raw_id_token, await self._load_jwks(), claims_options=claims_options
            )
        except JoseError:
            # The signing key may have rotated since our last JWKS fetch —
            # refresh once and retry before giving up.
            claims = jwt.decode(
                raw_id_token,
                await self._load_jwks(force_refresh=True),
                claims_options=claims_options,
            )
        claims.validate()
        if not claims.get("email"):
            raise ValueError("OIDC identity omitted email")
        return OidcIdentity(
            subject=str(claims["sub"]),
            email=str(claims["email"]),
            issuer=str(claims["iss"]),
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )

    def end_session_url(self, post_logout_redirect_uri: str) -> str | None:
        if self._metadata is None:
            return None
        endpoint = self._metadata.get("end_session_endpoint")
        if not endpoint:
            return None
        return f"{endpoint}?{urlencode({'logout_uri': post_logout_redirect_uri})}"
