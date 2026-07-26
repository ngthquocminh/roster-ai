"""BFF authentication endpoint contracts for Story 1.2."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from adapters.oidc.fake import FakeOidcProvider
from api.deps import get_identity_store, get_oidc_provider, get_settings
from api.main import app
from application.ports.session import (
    ActiveIdentity,
    LoginHandshake,
    ResolvedSession,
)
from settings import default_settings
from api.routers.auth import SESSION_COOKIE_NAME, hash_secret


class MemoryIdentityStore:
    def __init__(self) -> None:
        self.app_user_id = uuid4()
        self.site_id = uuid4()
        self.subject = "seeded-planner"
        self.handshakes: dict[str, LoginHandshake] = {}
        self.sessions: dict[str, ResolvedSession] = {}

    def create_login_handshake(self, handshake: LoginHandshake) -> None:
        self.handshakes[handshake.state] = handshake

    def consume_login_handshake(self, state: str) -> LoginHandshake | None:
        handshake = self.handshakes.pop(state, None)
        if handshake is None or handshake.expires_at <= datetime.now(timezone.utc):
            return None
        return handshake

    def resolve_active_identity(self, subject: str) -> ActiveIdentity | None:
        if subject != self.subject:
            return None
        return ActiveIdentity(
            app_user_id=self.app_user_id,
            site_id=self.site_id,
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
        self.sessions[session_token_hash] = ResolvedSession(
            app_user_id=app_user_id,
            site_id=site_id,
            csrf_token_hash=csrf_token_hash,
            expires_at=expires_at,
        )

    def resolve_session(self, session_token_hash: str) -> ResolvedSession | None:
        return self.sessions.get(session_token_hash)

    def revoke_session(self, session_token_hash: str) -> bool:
        return self.sessions.pop(session_token_hash, None) is not None


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "legacy.db"))
    settings = replace(
        default_settings(),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
        oidc_issuer="https://fake-idp.test",
        oidc_client_id="shiftmind-tests",
        oidc_redirect_uri="https://testserver/api/v1/auth/callback",
        app_base_url="https://testserver",
    )
    provider = FakeOidcProvider(
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
    )
    store = MemoryIdentityStore()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_oidc_provider] = lambda: provider
    app.dependency_overrides[get_identity_store] = lambda: store
    with TestClient(
        app,
        base_url="https://testserver",
        follow_redirects=False,
    ) as client:
        yield client, provider, store
    app.dependency_overrides.clear()


def _complete_login(client, provider, store):
    login = client.get("/api/v1/auth/login")
    assert login.status_code == 302
    authorize_query = parse_qs(urlparse(login.headers["location"]).query)
    state = authorize_query["state"][0]
    handshake = store.handshakes[state]
    code = provider.issue_authorization_code(
        subject=store.subject,
        email="planner@example.test",
        nonce=handshake.nonce,
        code_verifier=handshake.code_verifier,
    )

    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": code, "state": state},
    )
    return callback, state


def test_login_callback_session_and_logout_happy_path(auth_client) -> None:
    client, provider, store = auth_client

    callback, _ = _complete_login(client, provider, store)
    assert callback.status_code == 302
    assert callback.headers["location"] == "https://testserver"
    assert "provider" not in callback.text.lower()
    assert "token" not in callback.text.lower()
    set_cookie = callback.headers["set-cookie"]
    assert set_cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Domain=" not in set_cookie
    raw_cookie = client.cookies.get(SESSION_COOKIE_NAME)
    assert raw_cookie
    assert raw_cookie not in store.sessions
    assert hash_secret(raw_cookie) in store.sessions

    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    body = session.json()
    assert body["app_user_id"] == str(store.app_user_id)
    assert body["site_id"] == str(store.site_id)
    assert body["csrf_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "https://testserver",
            "X-CSRF-Token": body["csrf_token"],
        },
    )
    assert logout.status_code == 204
    replay = client.get(
        "/api/v1/auth/session",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={raw_cookie}"},
    )
    assert replay.status_code == 401


def test_session_without_valid_cookie_is_non_disclosing_problem_details(
    auth_client,
) -> None:
    client, _, _ = auth_client

    response = client.get("/api/v1/auth/session")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "authentication_required"
    assert not {"fixture", "membership", "site_name"}.intersection(response.json())


def test_callback_never_auto_provisions_an_unknown_identity(auth_client) -> None:
    client, provider, store = auth_client
    login = client.get("/api/v1/auth/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    handshake = store.handshakes[state]
    code = provider.issue_authorization_code(
        subject="not-provisioned",
        email="other@example.test",
        nonce=handshake.nonce,
        code_verifier=handshake.code_verifier,
    )

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": code, "state": state},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "identity_not_provisioned"
    assert store.sessions == {}


def test_login_handshake_state_is_single_use(auth_client) -> None:
    client, provider, store = auth_client
    callback, state = _complete_login(client, provider, store)
    assert callback.status_code == 302

    replay = client.get(
        "/api/v1/auth/callback",
        params={"code": "replayed-code", "state": state},
    )

    assert replay.status_code == 401
    assert replay.json()["code"] == "invalid_login_handshake"


def test_versioned_validation_failures_use_stable_problem_details(
    auth_client,
) -> None:
    client, _, _ = auth_client

    response = client.get("/api/v1/auth/callback")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        ({"Origin": "https://testserver"}, "csrf_validation_failed"),
        (
            {
                "Origin": "https://testserver",
                "X-CSRF-Token": "wrong-token",
            },
            "csrf_validation_failed",
        ),
        (
            {
                "Origin": "https://foreign.example",
                "X-CSRF-Token": "placeholder",
            },
            "csrf_validation_failed",
        ),
    ],
)
def test_logout_rejects_missing_or_invalid_csrf_and_origin(
    auth_client,
    headers,
    expected_code,
) -> None:
    client, provider, store = auth_client
    callback, _ = _complete_login(client, provider, store)
    assert callback.status_code == 302

    response = client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == expected_code
    assert client.get("/api/v1/auth/session").status_code == 200


def test_safe_referer_fallback_allows_valid_csrf(auth_client) -> None:
    client, provider, store = auth_client
    callback, _ = _complete_login(client, provider, store)
    assert callback.status_code == 302
    csrf_token = client.get("/api/v1/auth/session").json()["csrf_token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Referer": "https://testserver/workspace",
            "X-CSRF-Token": csrf_token,
        },
    )

    assert response.status_code == 204


def test_versioned_api_requires_auth_but_legacy_routes_keep_their_behavior(
    auth_client,
) -> None:
    client, _, _ = auth_client

    protected = client.get("/api/v1/not-a-real-resource")
    legacy = client.post(
        "/scenarios",
        json={"name": "bad", "fixture": "missing.json"},
    )

    assert protected.status_code == 401
    assert protected.json()["code"] == "authentication_required"
    protected_text = protected.text.lower()
    assert "fixture" not in protected_text
    assert "membership" not in protected_text
    assert "site name" not in protected_text
    assert legacy.status_code == 400


def test_application_exposes_no_registration_or_membership_creation_route(
    auth_client,
) -> None:
    client, _, _ = auth_client
    route_paths = {getattr(route, "path", "") for route in app.routes}
    openapi_paths = app.openapi()["paths"]

    assert not any(
        marker in path.lower()
        for path in route_paths
        for marker in ("register", "signup", "sign-up")
    )
    assert not any(
        method.lower() == "post"
        and any(marker in path.lower() for marker in ("app_user", "membership"))
        for path, operations in openapi_paths.items()
        for method in operations
    )
