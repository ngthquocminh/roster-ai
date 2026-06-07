"""Runtime settings — filesystem paths, resolved from env with sane defaults.

Kept dependency-free so any layer can import it. Env overrides let tests point
at a temp DB / data dir without touching code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent


@dataclass(frozen=True)
class Settings:
    db_path: str       # SQLite file
    data_dir: str      # directory holding input fixtures (*.json)


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    return Settings(db_path=db_path, data_dir=data_dir)
