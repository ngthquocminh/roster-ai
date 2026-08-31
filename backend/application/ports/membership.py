"""Transactional read port for active site membership (EAD-10)."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import Connection


class MembershipReader(Protocol):
    def has_active_membership(
        self,
        connection: Connection,
        *,
        app_user_id: UUID,
        site_id: UUID,
    ) -> bool: ...


__all__ = ["MembershipReader"]
