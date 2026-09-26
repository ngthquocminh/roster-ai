"""Per-turn short citation handles for trusted calculation results.

A model cites a calculation by copying an identifier. A 64-character
content-addressed hash is easy to mis-copy, so the application mints a short
handle (`r1`, `r2`, ... in first-seen order) and shows the model that instead.
The handle is resolved back to the trusted result before grounding; persisted
claims resolved to a result keep the canonical `result_id` (an unresolved
citation is persisted as cited, on a failed claim). The application mints handles, never the
model, so an unknown handle stays the gate's `missing_evidence` state.
"""
from __future__ import annotations

from threading import Lock
from typing import Iterable


class EvidenceRegistry:
    """Turn-scoped issuer and resolver of citation handles. Framework-free."""

    def __init__(self) -> None:
        self._handles: dict[str, str] = {}
        self._result_ids: dict[str, str] = {}
        # Sync tool handlers may run on worker threads; minting must be atomic
        # or two results could share one handle.
        self._lock = Lock()

    def handle_for(self, result_id: str) -> str:
        """The handle for `result_id`, minting the next one on first sight."""
        with self._lock:
            handle = self._handles.get(result_id)
            if handle is None:
                handle = f"r{len(self._handles) + 1}"
                self._handles[result_id] = handle
                self._result_ids[handle] = result_id
            return handle

    def result_id_for(self, handle: str) -> str | None:
        return self._result_ids.get(handle)

    def handle_of(self, result_id: str) -> str | None:
        """The handle already minted for `result_id`, without minting one."""
        return self._handles.get(result_id)


def trusted_results_by_citation(
    results: Iterable[object], registry: EvidenceRegistry | None
) -> dict[str, object]:
    """Every citation a claim may carry, mapped to its trusted result.

    Keys are each result's canonical `result_id` and, when one was minted this
    turn, its short handle.
    """
    by_citation: dict[str, object] = {}
    for value in results:
        result_id = getattr(value, "result_id", None)
        if not isinstance(result_id, str):
            continue
        by_citation[result_id] = value
        handle = registry.handle_of(result_id) if registry is not None else None
        if handle is not None:
            by_citation[handle] = value
    return by_citation


__all__ = ["EvidenceRegistry", "trusted_results_by_citation"]
