"""Deterministic, in-process OIDC provider for local development and tests."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from urllib.parse import urlencode

from authlib.jose import JsonWebKey, jwt

from application.ports.identity import OidcIdentity


@dataclass(frozen=True)
class _AuthorizationCode:
    subject: str
    email: str
    nonce: str
    code_verifier: str
    expires_at: datetime
    claim_overrides: Mapping[str, object]


class FakeOidcProvider:
    """A keyless OIDC double that never opens a network connection."""

    def __init__(self, *, issuer: str, client_id: str) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self._private_key = JsonWebKey.generate_key(
            "RSA",
            2048,
            is_private=True,
            options={"kid": "shiftmind-fake-key"},
        )
        self._codes: dict[str, _AuthorizationCode] = {}

    @property
    def discovery_document(self) -> dict[str, object]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "jwks_uri": f"{self.issuer}/jwks",
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @property
    def jwks(self) -> dict[str, object]:
        return {"keys": [self._private_key.as_dict(is_private=False)]}

    async def authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "nonce": nonce,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
            }
        )
        return f"{self.issuer}/authorize?{query}"

    def issue_authorization_code(
        self,
        *,
        subject: str,
        email: str,
        nonce: str,
        code_verifier: str,
        claim_overrides: Mapping[str, object] | None = None,
    ) -> str:
        digest = hashlib.sha256(
            f"{subject}\0{email}\0{nonce}\0{code_verifier}".encode()
        ).hexdigest()
        code = f"fake-{digest}"
        self._codes[code] = _AuthorizationCode(
            subject=subject,
            email=email,
            nonce=nonce,
            code_verifier=code_verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            claim_overrides=dict(claim_overrides or {}),
        )
        return code

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        nonce: str,
    ) -> OidcIdentity:
        del redirect_uri
        authorization = self._codes.pop(code, None)
        now = datetime.now(timezone.utc)
        if authorization is None:
            raise ValueError("OIDC authorization code is invalid or already used")
        if not secrets.compare_digest(authorization.code_verifier, code_verifier):
            raise ValueError("OIDC code verifier does not match")
        if not secrets.compare_digest(authorization.nonce, nonce):
            raise ValueError("OIDC nonce does not match")
        if authorization.expires_at <= now:
            raise ValueError("OIDC authorization code has expired")

        expires_at = now + timedelta(hours=1)
        claims = {
            "iss": self.issuer,
            "sub": authorization.subject,
            "aud": self.client_id,
            "email": authorization.email,
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "nonce": authorization.nonce,
        }
        claims.update(authorization.claim_overrides)
        header = {"alg": "RS256", "kid": "shiftmind-fake-key"}
        encoded = jwt.encode(header, claims, self._private_key)
        decoded = jwt.decode(
            encoded,
            self.jwks,
            claims_options={
                "iss": {"essential": True, "value": self.issuer},
                "sub": {"essential": True},
                "aud": {"essential": True, "value": self.client_id},
                "exp": {"essential": True},
                "nonce": {"essential": True, "value": nonce},
            },
        )
        decoded.validate()
        return OidcIdentity(
            subject=str(decoded["sub"]),
            email=str(decoded["email"]),
            issuer=str(decoded["iss"]),
            expires_at=datetime.fromtimestamp(decoded["exp"], tz=timezone.utc),
        )

    def end_session_url(self, post_logout_redirect_uri: str) -> str | None:
        del post_logout_redirect_uri
        return None
