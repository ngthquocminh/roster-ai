"""Tier-1 claim-support checker port (G' phase 3).

Judges whether a verified fact's WORDING is supported by its record. Tier 0
(the gate) has already checked the fact's attributes; this port adds a
probability, and in shadow mode that probability is recorded only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ClaimSupportItemV1:
    item_id: str
    claim_text: str
    evidence_text: str


@dataclass(frozen=True)
class ClaimSupportResultV1:
    """Per-item support probability. `error` is a closed code, never provider text."""

    probabilities: Mapping[str, float] = field(default_factory=dict)
    skipped: int = 0
    error: str | None = None


class ClaimSupportChecker(Protocol):
    """Implementations must not raise; failures are returned as `error`."""

    name: str
    #: Closed label for telemetry: "typesafe", "openrouter" or "stub".
    provider: str

    def check(self, items: tuple[ClaimSupportItemV1, ...]) -> ClaimSupportResultV1: ...


__all__ = ["ClaimSupportChecker", "ClaimSupportItemV1", "ClaimSupportResultV1"]
