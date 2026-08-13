"""Projection reader that opens one short site transaction per operation."""
from __future__ import annotations

from typing import Any
from uuid import UUID


class ShortTransactionScenarioProjectionReader:
    """Keep synchronous tool reads scoped without pinning a runtime transaction."""

    def __init__(self, reader: Any, open_site_context: Any, site_id: UUID) -> None:
        self._reader = reader
        self._open_site_context = open_site_context
        self._site_id = site_id

    def get_query_keys(self, group):
        return self._reader.get_query_keys(group)

    def __getattr__(self, name: str):
        operation = getattr(self._reader, name)

        def _in_short_transaction(_unused_connection, *args, **kwargs):
            with self._open_site_context(self._site_id) as connection:
                return operation(connection, *args, **kwargs)

        return _in_short_transaction
