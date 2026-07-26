"""Opaque-session and CSRF primitives shared by the versioned API."""
from __future__ import annotations

import base64
import hashlib
import hmac


SESSION_COOKIE_NAME = "__Host-shiftmind_session"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_token_for_session(session_token: str) -> str:
    digest = hmac.digest(
        session_token.encode("utf-8"),
        b"shiftmind-csrf-v1",
        "sha256",
    )
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
