"""Deterministic, in-process OIDC provider for local development and tests."""
from __future__ import annotations

import base64
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
    expires_at: datetime
    claim_overrides: Mapping[str, object]
    #: Exactly one of these is set. `code_verifier` is the in-process path,
    #: which knows the verifier up front; `code_challenge` is the browser PKCE
    #: path, which sees only the S256 challenge until redemption. They were
    #: briefly one field distinguished by a `"challenge:"` string prefix, which
    #: silently reinterpreted any verifier that happened to start with it.
    code_verifier: str | None = None
    code_challenge: str | None = None


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

    def issue_authorization_code_from_challenge(
        self,
        *,
        subject: str,
        email: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """Mint the browser-facing half of a PKCE authorization flow."""
        self._evict_expired_codes()
        code = f"fake-{secrets.token_urlsafe(24)}"
        self._codes[code] = _AuthorizationCode(
            subject=subject,
            email=email,
            nonce=nonce,
            code_challenge=code_challenge,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            claim_overrides={},
        )
        return code

    def _evict_expired_codes(self) -> None:
        """Drop lapsed codes before minting another.

        `/oidc/authorize` is reachable over HTTP and needs no credential, so
        codes that are never redeemed would otherwise accumulate for the life
        of the process.
        """
        now = datetime.now(timezone.utc)
        self._codes = {
            code: authorization
            for code, authorization in self._codes.items()
            if authorization.expires_at > now
        }

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        nonce: str,
    ) -> OidcIdentity:
        del redirect_uri
        authorization = self._consume_code(code, code_verifier)
        if not secrets.compare_digest(authorization.nonce, nonce):
            raise ValueError("OIDC nonce does not match")
        encoded, _ = self._signed_identity(authorization)
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

    def exchange_code_for_token_response(
        self, *, code: str, code_verifier: str, client_id: str
    ) -> dict[str, object]:
        """Consume a PKCE code through the local HTTP token endpoint."""
        if not secrets.compare_digest(client_id, self.client_id):
            raise ValueError("OIDC client id does not match")
        authorization = self._consume_code(code, code_verifier)
        encoded, claims = self._signed_identity(authorization)
        return {
            "access_token": f"fake-access-{secrets.token_urlsafe(18)}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": encoded.decode("ascii") if isinstance(encoded, bytes) else encoded,
            "scope": "openid email",
            "subject": claims["sub"],
        }

    def _consume_code(self, code: str, code_verifier: str) -> _AuthorizationCode:
        authorization = self._codes.pop(code, None)
        now = datetime.now(timezone.utc)
        if authorization is None:
            raise ValueError("OIDC authorization code is invalid or already used")
        if authorization.code_challenge is not None:
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            expected_verifier = authorization.code_challenge
            actual_verifier = (
                base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            )
        else:
            expected_verifier = authorization.code_verifier or ""
            actual_verifier = code_verifier
        if not secrets.compare_digest(expected_verifier, actual_verifier):
            raise ValueError("OIDC code verifier does not match")
        if authorization.expires_at <= now:
            raise ValueError("OIDC authorization code has expired")
        return authorization

    def _signed_identity(
        self, authorization: _AuthorizationCode
    ) -> tuple[bytes | str, dict[str, object]]:
        now = datetime.now(timezone.utc)
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
        return encoded, claims

    def end_session_url(self, post_logout_redirect_uri: str) -> str | None:
        del post_logout_redirect_uri
        return None
