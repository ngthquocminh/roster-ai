"""Owned OIDC boundary and provider adapter contracts for Story 1.2."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from application.ports.identity import OidcIdentity, create_provider
from settings import default_settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_authlib_runtime_dependency_is_pinned() -> None:
    project = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"authlib==1.7.2"' in project


def test_oidc_identity_is_frozen_and_provider_neutral() -> None:
    identity = OidcIdentity(
        subject="planner-subject",
        email="planner@example.test",
        issuer="https://issuer.example.test",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert {item.name for item in fields(identity)} == {
        "subject",
        "email",
        "issuer",
        "expires_at",
    }
    with pytest.raises(FrozenInstanceError):
        identity.subject = "changed"  # type: ignore[misc]


def test_oidc_settings_default_to_keyless_fake_provider(monkeypatch) -> None:
    for name in (
        "OIDC_PROVIDER",
        "OIDC_ISSUER",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "OIDC_REDIRECT_URI",
        "APP_BASE_URL",
        "SESSION_TTL_S",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = default_settings()

    assert settings.oidc_provider == "fake"
    assert settings.oidc_issuer == "http://shiftmind.test/oidc"
    assert settings.oidc_client_id == "shiftmind-local"
    assert settings.oidc_client_secret is None
    assert settings.oidc_redirect_uri == "http://shiftmind.test/api/v1/auth/callback"
    assert settings.app_base_url == "http://shiftmind.test"
    assert settings.session_ttl_s == 3600


def test_oidc_client_secret_is_redacted_from_settings_repr(monkeypatch) -> None:
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "do-not-log-me")

    assert "do-not-log-me" not in repr(default_settings())


def test_malformed_session_ttl_s_falls_back_to_the_default_instead_of_crashing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SESSION_TTL_S", "not-a-number")

    assert default_settings().session_ttl_s == 3600


def test_csrf_secret_is_redacted_from_settings_repr(monkeypatch) -> None:
    monkeypatch.setenv("CSRF_SECRET", "do-not-log-this-either")

    assert "do-not-log-this-either" not in repr(default_settings())


def test_csrf_secret_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setenv("CSRF_SECRET", "a-different-deployment-secret")

    assert default_settings().csrf_secret == "a-different-deployment-secret"


def test_fake_provider_completes_deterministic_oidc_exchange() -> None:
    asyncio.run(_exercise_fake_provider())


async def _exercise_fake_provider() -> None:
    settings = default_settings()
    provider = create_provider("fake", settings=settings)
    redirect_uri = settings.oidc_redirect_uri

    authorization_url = await provider.authorization_url(
        state="state-1",
        nonce="nonce-1",
        code_challenge="challenge-1",
        redirect_uri=redirect_uri,
    )
    query = parse_qs(urlparse(authorization_url).query)
    assert query == {
        "client_id": [settings.oidc_client_id],
        "code_challenge": ["challenge-1"],
        "code_challenge_method": ["S256"],
        "nonce": ["nonce-1"],
        "redirect_uri": [redirect_uri],
        "response_type": ["code"],
        "scope": ["openid email"],
        "state": ["state-1"],
    }

    code = provider.issue_authorization_code(
        subject="seeded-planner",
        email="planner@example.test",
        nonce="nonce-1",
        code_verifier="verifier-1",
    )
    identity = await provider.exchange_code(
        code=code,
        code_verifier="verifier-1",
        redirect_uri=redirect_uri,
        nonce="nonce-1",
    )

    assert identity.subject == "seeded-planner"
    assert identity.email == "planner@example.test"
    assert identity.issuer == settings.oidc_issuer
    assert identity.expires_at > datetime.now(timezone.utc)


def test_oidc_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown OIDC provider"):
        create_provider("unknown", settings=default_settings())


@pytest.mark.parametrize(
    ("claim_overrides", "exchange_nonce"),
    [
        ({"aud": "wrong-audience"}, "nonce-1"),
        ({"iss": "https://wrong-issuer.example"}, "nonce-1"),
        ({"exp": 1}, "nonce-1"),
        ({}, "wrong-nonce"),
    ],
)
def test_fake_provider_rejects_invalid_id_token_claims(
    claim_overrides,
    exchange_nonce,
) -> None:
    async def exercise() -> None:
        settings = default_settings()
        provider = create_provider("fake", settings=settings)
        code = provider.issue_authorization_code(
            subject="seeded-planner",
            email="planner@example.test",
            nonce="nonce-1",
            code_verifier="verifier-1",
            claim_overrides=claim_overrides,
        )
        with pytest.raises(Exception):
            await provider.exchange_code(
                code=code,
                code_verifier="verifier-1",
                redirect_uri=settings.oidc_redirect_uri,
                nonce=exchange_nonce,
            )

    asyncio.run(exercise())
