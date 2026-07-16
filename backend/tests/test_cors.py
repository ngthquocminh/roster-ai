"""CORS configuration + middleware tests (BE-01).

Task 1 covers the settings-level parsing of CORS_ORIGINS via
`default_settings()` directly — no app import needed for these cases.
Task 2 extends this file with app-level tests exercising the actual
CORSMiddleware behaviour (allowed/disallowed origin, preflight).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from settings import default_settings


def test_cors_origins_default_when_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = default_settings()
    assert settings.cors_origins == ("http://localhost:5173", "http://localhost:4173")


def test_cors_origins_single_origin_yields_tuple(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test")
    settings = default_settings()
    assert settings.cors_origins == ("http://a.test",)


def test_cors_origins_multiple_origins_preserve_order(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test,http://c.test")
    settings = default_settings()
    assert settings.cors_origins == ("http://a.test", "http://b.test", "http://c.test")


def test_cors_origins_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " http://a.test , http://b.test ")
    settings = default_settings()
    assert settings.cors_origins == ("http://a.test", "http://b.test")


def test_cors_origins_drops_empty_segments(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,,")
    settings = default_settings()
    assert settings.cors_origins == ("http://a.test",)


def test_cors_origins_empty_string_yields_empty_tuple(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    settings = default_settings()
    assert settings.cors_origins == ()


# --- Task 2: app-level CORSMiddleware tests -----------------------------

def _fresh_app(monkeypatch, tmp_path, cors_origins: str):
    """Import api.main fresh, with CORS_ORIGINS set before import.

    CORS is resolved once at app-construction time (see api/main.py's
    add_middleware comment) — unlike every other Settings field, which is
    re-read per request. Because api.main may already be cached in
    sys.modules (another test file may have imported it first, freezing
    whatever CORS_ORIGINS happened to be set then), we must evict it from
    sys.modules before importing so this test's env value actually takes
    effect. Reversed ordering (import before setenv) is the exact silent
    failure mode RESEARCH.md's Common Pitfalls #1 warns about: no exception,
    the header is just absent.
    """
    monkeypatch.setenv("CORS_ORIGINS", cors_origins)
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    import sys

    sys.modules.pop("api.main", None)
    from api.main import app

    return app


def test_cors_allowed_origin_reflected(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, "http://localhost:5173")
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_disallowed_origin_no_header(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, "http://localhost:5173")
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in resp.headers


def test_cors_two_origins_no_cross_contamination(monkeypatch, tmp_path):
    """Two requests with different origins, against the same imported app,
    each get their own correct outcome — the second does not inherit or
    corrupt the first's evaluation."""
    app = _fresh_app(monkeypatch, tmp_path, "http://localhost:5173")
    with TestClient(app) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
        disallowed = client.get("/health", headers={"Origin": "http://evil.example"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-origin" not in disallowed.headers


@pytest.mark.parametrize("origin", ["http://a.test", "http://b.test", "http://c.test"])
def test_cors_reflects_every_configured_origin(monkeypatch, tmp_path, origin):
    """Assumption-delta invariant: the allow-list behavior is parametrized
    over the WHOLE configured list, never special-cased to the first entry."""
    app = _fresh_app(monkeypatch, tmp_path, "http://a.test,http://b.test,http://c.test")
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": origin})
        assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_allows_post(monkeypatch, tmp_path):
    app = _fresh_app(monkeypatch, tmp_path, "http://localhost:5173")
    with TestClient(app) as client:
        resp = client.options(
            "/scenarios",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "POST" in resp.headers["access-control-allow-methods"]
