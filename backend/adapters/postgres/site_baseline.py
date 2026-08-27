"""PostgreSQL adapter for the dedicated one-row site baseline record."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, select

from adapters.postgres.schema import site_baseline
from application.ports.site_baseline import SiteBaselineV1


class PostgresSiteBaselineReader:
    def get(self, connection: Connection, site_id: UUID) -> SiteBaselineV1 | None:
        row = connection.execute(
            select(site_baseline.c.site_id, site_baseline.c.schedule_version_id, site_baseline.c.resource_version)
            .where(site_baseline.c.site_id == site_id)
        ).one_or_none()
        if row is None:
            return None
        return SiteBaselineV1(site_id=row.site_id, schedule_version_id=row.schedule_version_id, resource_version=row.resource_version)
