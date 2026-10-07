"""Transactional read port for active site membership (EAD-10)."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class MembershipReader(Protocol):
    def has_active_membership(
        self,
        connection: Any,
        *,
        app_user_id: UUID,
        site_id: UUID,
    ) -> bool: ...


__all__ = ["MembershipReader"]
