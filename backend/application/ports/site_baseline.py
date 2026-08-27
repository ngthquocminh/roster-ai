"""Read port for the sole current-baseline storage home (EAD-1/EAD-2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import Connection


@dataclass(frozen=True)
class SiteBaselineV1:
    site_id: UUID
    schedule_version_id: UUID
    resource_version: int


class SiteBaselineReader(Protocol):
    def get(self, connection: Connection, site_id: UUID) -> SiteBaselineV1 | None: ...


__all__ = ["SiteBaselineReader", "SiteBaselineV1"]
