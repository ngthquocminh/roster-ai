"""PostgreSQL reader for the initiating actor's current site membership."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, literal, select

from adapters.postgres.schema import membership


class PostgresMembershipReader:
    def has_active_membership(
        self,
        connection: Connection,
        *,
        app_user_id: UUID,
        site_id: UUID,
    ) -> bool:
        return connection.execute(
            select(literal(1)).where(
                membership.c.app_user_id == app_user_id,
                membership.c.site_id == site_id,
                membership.c.revoked_at.is_(None),
            )
        ).first() is not None
