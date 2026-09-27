"""Deterministic claim-support double for keyless CI (G' phase 3)."""
from __future__ import annotations

from application.ports.claim_support import ClaimSupportItemV1, ClaimSupportResultV1


class StubClaimSupportChecker:
    """Returns a fixed probability per item, or a fixed error; records calls."""

    name = "stub"
    provider = "stub"

    def __init__(self, probability: float = 0.95, *, error: str | None = None) -> None:
        self._probability = probability
        self._error = error
        self.calls: list[tuple[ClaimSupportItemV1, ...]] = []

    def check(self, items: tuple[ClaimSupportItemV1, ...]) -> ClaimSupportResultV1:
        self.calls.append(items)
        if self._error is not None:
            return ClaimSupportResultV1(error=self._error)
        return ClaimSupportResultV1(
            probabilities={item.item_id: self._probability for item in items})


__all__ = ["StubClaimSupportChecker"]
