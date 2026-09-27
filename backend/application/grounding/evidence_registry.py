"""Per-turn short citation handles for trusted calculation results.

A model cites a calculation by copying an identifier. A 64-character
content-addressed hash is easy to mis-copy, so the application mints a short
handle (`r1`, `r2`, ... in first-seen order) and shows the model that instead.
Records read by `scheduling_inspect` get handles too, prefixed by group
(`w3` a worker, `t12` a task, ...), which `<claim ev=...>` fact tags cite.
The handle is resolved back to the trusted result before grounding; persisted
claims resolved to a result keep the canonical `result_id` (an unresolved
citation is persisted as cited, on a failed claim). The application mints handles, never the
model, so an unknown handle stays the gate's `missing_evidence` state.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Iterable, Mapping

# One letter per evidence group, so a record handle names its kind. `r` stays
# reserved for calculation results.
RECORD_HANDLE_PREFIX: Mapping[str, str] = {
    "workers": "w",
    "work-areas-and-tasks": "t",
    "demand": "d",
    "baseline-assignments": "a",
    "locks": "l",
    "constraints-and-objectives": "c",
}


class EvidenceRegistry:
    """Turn-scoped issuer and resolver of citation handles. Framework-free."""

    def __init__(self) -> None:
        self._handles: dict[str, str] = {}
        self._result_ids: dict[str, str] = {}
        # Sync tool handlers may run on worker threads; minting must be atomic
        # or two results could share one handle.
        self._lock = Lock()
        self._record_handles: dict[tuple[str, str], str] = {}
        self._records: dict[str, tuple[str, str]] = {}
        self._record_counts: dict[str, int] = {}

    def handle_for(self, result_id: str) -> str:
        """The handle for `result_id`, minting the next one on first sight."""
        with self._lock:
            handle = self._handles.get(result_id)
            if handle is None:
                handle = f"r{len(self._handles) + 1}"
                self._handles[result_id] = handle
                self._result_ids[handle] = result_id
            return handle

    def handle_for_record(self, group: str, record_id: str) -> str:
        """The handle for one record of an evidence group, minted on first sight.

        Numbered per prefix in first-seen order: the first worker is `w1`.
        """
        prefix = RECORD_HANDLE_PREFIX[group]
        key = (group, record_id)
        with self._lock:
            handle = self._record_handles.get(key)
            if handle is None:
                count = self._record_counts.get(prefix, 0) + 1
                self._record_counts[prefix] = count
                handle = f"{prefix}{count}"
                self._record_handles[key] = handle
                self._records[handle] = key
            return handle

    def record_for(self, handle: str) -> tuple[str, str] | None:
        """(evidence group, record_id) a record handle was minted for."""
        return self._records.get(handle)

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


@dataclass(frozen=True)
class TrustedRecordV1:
    """One row a trusted inspect result returned this turn, keyed by its handle."""

    scenario_group: str
    record: Mapping[str, object]
    scenario_version_id: str


def trusted_records_by_handle(results: Iterable[object]) -> dict[str, TrustedRecordV1]:
    """Every record handle issued this turn, mapped to its trusted row.

    Read from the TRUSTED results (the handler's own return), never from
    model-visible text, so a fact tag is checked against what was really read.
    """
    records: dict[str, TrustedRecordV1] = {}
    for value in results:
        items = getattr(value, "items", None)
        group = getattr(value, "group", None)
        version = getattr(value, "scenario_version_id", None)
        if not isinstance(items, tuple) or not isinstance(group, str) or version is None:
            continue
        for item in items:
            if isinstance(item, Mapping) and isinstance(item.get("ev"), str):
                records[item["ev"]] = TrustedRecordV1(group, item, str(version))
    return records


__all__ = [
    "RECORD_HANDLE_PREFIX", "EvidenceRegistry", "TrustedRecordV1",
    "trusted_records_by_handle", "trusted_results_by_citation",
]
