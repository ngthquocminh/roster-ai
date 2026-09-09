"""Mechanical guards for the reviewer-facing portfolio documents.

Shaped after ``test_evidence_convention.py``: walk the tree rather than name
files, so a document added later is covered without editing this module.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
WALKTHROUGH = DOCS / "WALKTHROUGH.md"

#: Reviewer-facing markdown: every ``docs/**/*.md`` outside the archive, plus the
#: repository README. Archived material is historical by contract and exempt.
def _reviewer_facing_docs() -> tuple[Path, ...]:
    swept = [p for p in sorted(DOCS.rglob("*.md")) if "archive" not in p.parts]
    return (REPO_ROOT / "README.md", *swept)


#: Documents excluded from the retired-symbol sweep, each with the reason it is
#: exempt. These are not stale: the v0.3 surface was fenced, not removed (AD-1's
#: compatibility allowance), so they describe a surface that is still live.
#: ``settings.py:253,274`` still read ``ROSTERAI_DB``/``LLM_PROVIDER``, 15 legacy
#: operations are still mounted, and retirement is staged behind the fail-closed
#: middleware in ``api/main.py`` plus ``scripts/gate_a_cutover.py``.
#: The split is entry-document vs reference-document, not clean vs dirty. A
#: reviewer-entry document must not name the legacy seam at all, because naming
#: it there presents it as the current path. A deep-reference document describes
#: live mechanisms for a living, and several of those mechanisms legitimately
#: carry these names. Residual, ledgered: this guard is a literal token sweep and
#: cannot tell "accurately describes a live legacy mechanism" from "presents it
#: as current", so the documents below are reviewed by eye, not by test.
SYMBOL_SWEEP_EXCLUSIONS = {
    "CONFIGURATION.md": "documents the still-live legacy surface settings.py reads",
    "AGENT-RUNTIME-DECISION.md": "the ADR that decided to move off that seam",
    "GATE-A-RUNBOOK.md": "documents the SQLite cutover operation itself",
    "CI-SECRETS-CHECKLIST.md": "create_provider is a live keyless default",
    "TESTING.md": "describes tests that still exercise the legacy store",
    "DEVELOPMENT.md": "describes live test-isolation that pops those env vars",
}

RETIRED = (
    "LLM_PROVIDER",
    "ROSTERAI_DB",
    "rosterai.db",
    "create_provider",
    "backend/llm/",
    "/runs/{run_id}/insights",
    "SQLite",
)

SELF_APPROVAL_SENTENCE = "The planner who requests an approval can decide it."

_INLINE_LINK = re.compile(r"(?<!\\)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(][^)]*)?\)")
_REFERENCE_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?", re.MULTILINE)
_FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_fences(text: str) -> str:
    """Drop fenced code blocks so sample markdown inside them is not asserted."""
    out, fenced = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return "\n".join(out)


def _link_targets(text: str) -> list[str]:
    body = _strip_fences(text)
    return [*_INLINE_LINK.findall(body), *_REFERENCE_DEF.findall(body)]


@pytest.mark.parametrize(
    "document", _reviewer_facing_docs(), ids=lambda p: p.name
)
def test_reviewer_facing_relative_links_resolve(document: Path):
    for target in _link_targets(_read(document)):
        if "://" in target or target.startswith(("#", "mailto:", "//")):
            continue
        path = target.split("#", 1)[0]
        if not path:
            continue
        resolved = document.parent / _unescape(path)
        assert resolved.exists(), f"{document}: broken link {target}"


def _unescape(path: str) -> str:
    return path.replace("%20", " ").replace("\\_", "_")


def _claims_region(text: str) -> str:
    start = "<!-- behavioral-claims:start -->"
    end = "<!-- behavioral-claims:end -->"
    assert start in text, "behavioral-claims start marker is missing"
    assert end in text, "behavioral-claims end marker is missing"
    return text.split(start, 1)[1].split(end, 1)[0]


def test_behavioral_claim_anchors_exist():
    region = _claims_region(_read(WALKTHROUGH))
    claims = [line for line in region.splitlines() if line.strip()]
    assert claims, "behavioral-claims region is empty"

    checked = 0
    for line in claims:
        anchors = re.findall(r"Anchor:\s*`([^`]+)`", line)
        assert anchors, f"behavioral claim carries no anchor: {line.strip()[:80]}"
        for anchor in anchors:
            _assert_anchor_resolves(anchor)
            checked += 1
    assert checked >= len(claims)


def _assert_anchor_resolves(anchor: str) -> None:
    if anchor.startswith("evidence/"):
        assert (REPO_ROOT / anchor).is_file(), f"missing evidence anchor: {anchor}"
        return
    if "::" in anchor:
        node_id = anchor.removeprefix("backend/")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", node_id],
            cwd=REPO_ROOT / "backend",
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"anchor did not collect: {anchor}\n{result.stdout}\n{result.stderr}"
        )
        return
    # Decision 7's third anchor kind: `<path>:<line>` naming an assertion line.
    if ":" in anchor:
        raw_path, _, line_no = anchor.rpartition(":")
        target = REPO_ROOT / raw_path
        assert target.is_file(), f"anchor path does not exist: {anchor}"
        assert line_no.isdigit(), f"anchor line is not a number: {anchor}"
        lines = _read(target).splitlines()
        index = int(line_no)
        assert 1 <= index <= len(lines), f"anchor line out of range: {anchor}"
        assert lines[index - 1].strip(), f"anchor line is blank: {anchor}"
        return
    raise AssertionError(f"unrecognised anchor form: {anchor}")


@pytest.mark.parametrize(
    "document",
    [p for p in _reviewer_facing_docs() if p.name not in SYMBOL_SWEEP_EXCLUSIONS],
    ids=lambda p: p.name,
)
def test_reviewer_facing_docs_have_no_retired_symbols(document: Path):
    text = _read(document)
    for symbol in RETIRED:
        assert symbol not in text, f"{document}: retired symbol {symbol}"


def test_walkthrough_states_self_approval_limit():
    # Normalise whitespace so a reflow cannot break a present sentence, and drop
    # comments and fences so the statement must be visible to a reader.
    text = _strip_fences(_read(WALKTHROUGH))
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    assert " ".join(SELF_APPROVAL_SENTENCE.split()) in " ".join(text.split())
