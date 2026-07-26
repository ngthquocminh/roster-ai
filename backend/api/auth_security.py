"""Opaque-session and CSRF primitives shared by the versioned API."""
from __future__ import annotations

import base64
import hashlib
import hmac


SESSION_COOKIE_NAME = "__Host-shiftmind_session"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_token_for_session(session_token: str, csrf_secret: str) -> str:
    """Deterministically derive the CSRF token from the session token plus a
    per-deployment secret (Settings.csrf_secret) — re-derivable on demand
    (no second token to persist) but not reconstructible from a leaked
    session token alone."""
    digest = hmac.digest(
        csrf_secret.encode("utf-8"),
        session_token.encode("utf-8"),
        "sha256",
    )
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
