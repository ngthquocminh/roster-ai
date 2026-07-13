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


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    llm_provider = os.environ.get("LLM_PROVIDER", "stub")
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = os.environ.get("GEMINI_API_KEY")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    openrouter_model = os.environ.get("OPENROUTER_MODEL", _OPENROUTER_DEFAULT_MODEL)
    return Settings(
        db_path=db_path,
        data_dir=data_dir,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
    )
