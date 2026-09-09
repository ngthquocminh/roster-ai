"""Mechanical guards for the reviewer-facing portfolio documents."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WALKTHROUGH = REPO_ROOT / "docs" / "WALKTHROUGH.md"
CURRENT_DOCS = (
    REPO_ROOT / "README.md",
    WALKTHROUGH,
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "GETTING-STARTED.md",
    REPO_ROOT / "docs" / "DEVELOPMENT.md",
    REPO_ROOT / "docs" / "API.md",
    REPO_ROOT / "docs" / "ARCHITECTURE.md",
)
SYMBOL_DOCS = (
    REPO_ROOT / "README.md",
    WALKTHROUGH,
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "API.md",
    REPO_ROOT / "docs" / "ARCHITECTURE.md",
)
RETIRED = (
    "LLM_PROVIDER",
    "ROSTERAI_DB",
    "rosterai.db",
    "create_provider",
    "backend/llm/",
    "/runs/{run_id}/insights",
    "SQLite",
)


def test_reviewer_facing_relative_links_resolve():
    for document in CURRENT_DOCS:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            path = target.split("#", 1)[0]
            assert (document.parent / path).resolve().exists(), f"{document}: {target}"


def test_behavioral_claim_anchors_exist():
    text = WALKTHROUGH.read_text()
    region = text.split("<!-- behavioral-claims:start -->", 1)[1].split(
        "<!-- behavioral-claims:end -->", 1
    )[0]
    for anchor in re.findall(r"`([^`]+)`", region):
        if anchor.startswith("evidence/"):
            assert (REPO_ROOT / anchor).is_file(), anchor
        elif "::" in anchor:
            node_id = anchor.removeprefix("backend/")
            result = subprocess.run(
                ["pytest", "--collect-only", "-q", node_id], cwd=REPO_ROOT / "backend", capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr


def test_reviewer_facing_docs_have_no_retired_symbols():
    for document in SYMBOL_DOCS:
        text = document.read_text()
        for symbol in RETIRED:
            assert symbol not in text, f"{document}: {symbol}"


def test_walkthrough_states_self_approval_limit():
    assert "The planner who requests an approval can decide it." in WALKTHROUGH.read_text()
