"""Runtime settings — filesystem paths and LLM provider config, resolved from
env with sane defaults.

Kept to a single lightweight config-layer dependency (python-dotenv) so any
layer can import it. Env overrides let tests point at a temp DB / data dir, or
select an LLM provider/model, without touching code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent

# Load backend/.env once at import time, resolved relative to this file so it
# works regardless of process CWD (API server, run.py CLI, pytest). A real OS
# env var always wins (override=False); an empty `GEMINI_API_KEY=` in the file
# does not clobber an already-set OS key.
load_dotenv(_BACKEND_DIR / ".env", override=False)


# Live-verified tool-capable as of 2026-07-13; replaces meta-llama/llama-3.3-70b-instruct:free, which started returning upstream 429 rate-limit errors.
_OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b:free"


@dataclass(frozen=True)
class Settings:
    db_path: str            # SQLite file
    data_dir: str           # directory holding input fixtures (*.json)
    database_url: str       # governed PostgreSQL history
    maintenance_flag_path: str  # persistent Gate A legacy-write lock
    llm_provider: str       # "stub" (default) | "gemini" | "openrouter"
    llm_model: str          # model id passed to the selected provider
    # T-04-01: keep the API key out of the auto-generated __repr__ so it never
    # surfaces in logs, FastAPI dependency errors, or unhandled-exception dumps.
    llm_api_key: str | None = field(repr=False, default=None)  # from GEMINI_API_KEY; None for stub
    # Same repr=False treatment as llm_api_key (T-04-01) — from OPENROUTER_API_KEY.
    openrouter_api_key: str | None = field(repr=False, default=None)
    # Separate from llm_model because llm_model's default "gemini-2.5-flash" is
    # not a valid OpenRouter slug.
    openrouter_model: str = _OPENROUTER_DEFAULT_MODEL
    # Browser origins allowed to call this API (BE-01, D-04). Not secret, so
    # this field carries no repr override — that treatment is reserved for the
    # two API key fields above.
    cors_origins: tuple[str, ...] = field(default=())
    oidc_provider: str = "fake"
    oidc_issuer: str = "http://shiftmind.test/oidc"
    oidc_client_id: str = "shiftmind-local"
    oidc_client_secret: str | None = field(repr=False, default=None)
    oidc_redirect_uri: str = "http://shiftmind.test/api/v1/auth/callback"
    app_base_url: str = "http://shiftmind.test"
    session_ttl_s: int = 3600


def resolve_fixture_path(data_dir: str, fixture: str) -> str | None:
    """Resolve `fixture` against `data_dir`, rejecting any path that escapes it
    (an absolute path, or a relative path containing `../` sequences) — CR-03.

    `os.path.join(data_dir, fixture)` silently discards `data_dir` when
    `fixture` is absolute, and a relative `fixture` containing `../` can
    normalize outside `data_dir` even without being absolute; either lets a
    caller reference an arbitrary file on disk (path traversal).

    Returns the resolved absolute path, or None if `fixture` is invalid.
    Callers translate None into the appropriate "unknown fixture" response
    for their layer (400 at scenario-creation time, 404/LookupError at
    constraint-parse time) — never a bare filesystem error.
    """
    if os.path.isabs(fixture):
        return None
    data_dir_abs = os.path.abspath(data_dir)
    candidate = os.path.normpath(os.path.join(data_dir_abs, fixture))
    if candidate != data_dir_abs and not candidate.startswith(data_dir_abs + os.sep):
        return None
    return candidate


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    database_url = os.environ.get(
        "ROSTERAI_DATABASE_URL",
        "postgresql+psycopg://rosterai:rosterai@localhost:5432/rosterai",
    )
    maintenance_flag_path = os.environ.get(
        "ROSTERAI_MAINTENANCE_FLAG",
        str(_BACKEND_DIR / "var" / "gate-a-maintenance"),
    )
    llm_provider = os.environ.get("LLM_PROVIDER", "stub")
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = os.environ.get("GEMINI_API_KEY")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    openrouter_model = os.environ.get("OPENROUTER_MODEL", _OPENROUTER_DEFAULT_MODEL)
    # The os.environ.get default only applies when CORS_ORIGINS is absent from
    # env entirely; an explicitly empty CORS_ORIGINS="" yields an empty
    # allow-list (a valid "no browser origin may call this" posture), not a
    # silent fallback to the default two Vite origins.
    cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173")
    cors_origins = tuple(o.strip() for o in cors_origins_raw.split(",") if o.strip())
    oidc_provider = os.environ.get("OIDC_PROVIDER", "fake")
    oidc_issuer = os.environ.get("OIDC_ISSUER", "http://shiftmind.test/oidc")
    oidc_client_id = os.environ.get("OIDC_CLIENT_ID", "shiftmind-local")
    oidc_client_secret = os.environ.get("OIDC_CLIENT_SECRET")
    oidc_redirect_uri = os.environ.get(
        "OIDC_REDIRECT_URI",
        "http://shiftmind.test/api/v1/auth/callback",
    )
    app_base_url = os.environ.get("APP_BASE_URL", "http://shiftmind.test")
    session_ttl_s = int(os.environ.get("SESSION_TTL_S", "3600"))
    return Settings(
        db_path=db_path,
        data_dir=data_dir,
        database_url=database_url,
        maintenance_flag_path=maintenance_flag_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        cors_origins=cors_origins,
        oidc_provider=oidc_provider,
        oidc_issuer=oidc_issuer.rstrip("/"),
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_redirect_uri=oidc_redirect_uri,
        app_base_url=app_base_url.rstrip("/"),
        session_ttl_s=session_ttl_s,
    )
