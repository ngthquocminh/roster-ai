"""Versioned BFF authentication endpoints."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from api.auth_security import (
    SESSION_COOKIE_NAME,
    csrf_token_for_session,
    hash_secret,
)
from api.deps import get_identity_store, get_oidc_provider, get_settings
from api.problems import problem_response
from api.schemas import AuthSessionOut, ProblemDetailsV1
from application.ports.identity import OidcProvider
from application.ports.session import IdentitySessionStore, LoginHandshake
from settings import Settings


router = APIRouter(prefix="/auth", tags=["auth"])

_HANDSHAKE_TTL = timedelta(minutes=10)


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def _resolved_session(request: Request, store: IdentitySessionStore):
    state_session = getattr(request.state, "shiftmind_session", None)
    state_token = getattr(request.state, "shiftmind_session_token", None)
    if state_session is not None and state_token is not None:
        return state_token, state_session
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None, None
    resolved = await run_in_threadpool(
        store.resolve_session,
        hash_secret(session_token),
    )
    return session_token, resolved


@router.get(
    "/login",
    status_code=302,
    responses={302: {"description": "Redirect to the configured OIDC provider"}},
)
async def login(
    settings: Settings = Depends(get_settings),
    provider: OidcProvider = Depends(get_oidc_provider),
    store: IdentitySessionStore = Depends(get_identity_store),
) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    handshake = LoginHandshake(
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_target=settings.app_base_url,
        expires_at=datetime.now(timezone.utc) + _HANDSHAKE_TTL,
    )
    await run_in_threadpool(store.create_login_handshake, handshake)
    authorization_url = await provider.authorization_url(
        state=state,
        nonce=nonce,
        code_challenge=_pkce_challenge(code_verifier),
        redirect_uri=settings.oidc_redirect_uri,
    )
    return RedirectResponse(authorization_url, status_code=302)


@router.get(
    "/callback",
    status_code=302,
    responses={
        302: {"description": "Application session created"},
        401: {"model": ProblemDetailsV1},
    },
)
async def callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    provider: OidcProvider = Depends(get_oidc_provider),
    store: IdentitySessionStore = Depends(get_identity_store),
) -> Response:
    handshake = await run_in_threadpool(store.consume_login_handshake, state)
    if handshake is None:
        return problem_response(
            status=401,
            code="invalid_login_handshake",
            title="Sign-in failed",
            detail="The sign-in request is invalid or expired.",
        )
    try:
        identity = await provider.exchange_code(
            code=code,
            code_verifier=handshake.code_verifier,
            redirect_uri=settings.oidc_redirect_uri,
            nonce=handshake.nonce,
        )
    except Exception:
        return problem_response(
            status=401,
            code="oidc_identity_rejected",
            title="Sign-in failed",
            detail="The identity provider response could not be accepted.",
        )

    active_identity = await run_in_threadpool(
        store.resolve_active_identity,
        identity.subject,
    )
    if active_identity is None:
        return problem_response(
            status=401,
            code="identity_not_provisioned",
            title="Sign-in failed",
            detail="This identity is not provisioned for the application.",
        )

    now = datetime.now(timezone.utc)
    expires_at = min(
        now + timedelta(seconds=settings.session_ttl_s),
        identity.expires_at,
    )
    session_token = secrets.token_urlsafe(32)
    csrf_token = csrf_token_for_session(session_token)
    await run_in_threadpool(
        store.create_session,
        session_token_hash=hash_secret(session_token),
        csrf_token_hash=hash_secret(csrf_token),
        app_user_id=active_identity.app_user_id,
        site_id=active_identity.site_id,
        expires_at=expires_at,
    )
    response = RedirectResponse(handshake.redirect_target, status_code=302)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=max(0, int((expires_at - now).total_seconds())),
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.get(
    "/session",
    response_model=AuthSessionOut,
    responses={401: {"model": ProblemDetailsV1}},
)
async def session(
    request: Request,
    store: IdentitySessionStore = Depends(get_identity_store),
) -> AuthSessionOut | JSONResponse:
    session_token, resolved = await _resolved_session(request, store)
    if session_token is None or resolved is None:
        return problem_response(
            status=401,
            code="authentication_required",
            title="Authentication required",
            detail="A valid application session is required.",
        )
    csrf_token = csrf_token_for_session(session_token)
    if not hmac.compare_digest(
        hash_secret(csrf_token),
        resolved.csrf_token_hash,
    ):
        return problem_response(
            status=401,
            code="authentication_required",
            title="Authentication required",
            detail="A valid application session is required.",
        )
    return AuthSessionOut(
        app_user_id=resolved.app_user_id,
        site_id=resolved.site_id,
        csrf_token=csrf_token,
        expires_at=resolved.expires_at,
    )


@router.post(
    "/logout",
    status_code=204,
    responses={401: {"model": ProblemDetailsV1}},
)
async def logout(
    request: Request,
    store: IdentitySessionStore = Depends(get_identity_store),
) -> Response:
    session_token, resolved = await _resolved_session(request, store)
    if session_token is None or resolved is None:
        return problem_response(
            status=401,
            code="authentication_required",
            title="Authentication required",
            detail="A valid application session is required.",
        )
    await run_in_threadpool(store.revoke_session, hash_secret(session_token))
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response
