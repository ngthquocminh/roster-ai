"""CORS configuration + middleware tests (BE-01).

Task 1 covers the settings-level parsing of CORS_ORIGINS via
`default_settings()` directly — no app import needed for these cases.
Task 2 extends this file with app-level tests exercising the actual
CORSMiddleware behaviour (allowed/disallowed origin, preflight).
"""
from __future__ import annotations

import pytest

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
