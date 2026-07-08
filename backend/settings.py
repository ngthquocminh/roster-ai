"""Runtime settings — filesystem paths and LLM provider config, resolved from
env with sane defaults.

Kept dependency-free so any layer can import it. Env overrides let tests point
at a temp DB / data dir, or select an LLM provider/model, without touching code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


@dataclass(frozen=True)
class Settings:
    db_path: str            # SQLite file
    data_dir: str           # directory holding input fixtures (*.json)
    llm_provider: str       # "stub" (default) | "gemini"
    llm_model: str          # model id passed to the selected provider
    # T-04-01: keep the API key out of the auto-generated __repr__ so it never
    # surfaces in logs, FastAPI dependency errors, or unhandled-exception dumps.
    llm_api_key: str | None = field(repr=False, default=None)  # from GEMINI_API_KEY; None for stub


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    llm_provider = os.environ.get("LLM_PROVIDER", "stub")
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = os.environ.get("GEMINI_API_KEY")
    return Settings(
        db_path=db_path,
        data_dir=data_dir,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
    )
