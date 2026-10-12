"""The predefined fixtures governed by Story 1.1.

Both local bootstrap and the evidence tooling import fixtures from this one
list, so the set a fresh database seeds and the set evidence binds to cannot
drift apart. It lived in the one-shot SQLite-to-PostgreSQL cutover script until
that script was removed with the legacy v0.4 stack.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


@dataclass(frozen=True)
class FixtureSpec:
    path: Path
    fixture_id: str
    version: str


def default_fixtures() -> tuple[FixtureSpec, ...]:
    """Return the two predefined fixtures governed by Story 1.1."""
    return (
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input.json",
            "sample_tiny_input",
            "v1",
        ),
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input_more_tm.json",
            "sample_tiny_input_more_tm",
            "v1",
        ),
    )
