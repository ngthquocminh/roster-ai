"""PostgreSQL adapter for the dedicated one-row site baseline record."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, insert, select, update
from sqlalchemy.exc import IntegrityError

from adapters.postgres.schema import site_baseline
from application.ports.site_baseline import SiteBaselineV1

#: The one constraint whose violation means "another promotion won the race".
_UNIQUE_BASELINE_CONSTRAINT = "uq_site_baseline_site"


class PostgresSiteBaselineReader:
    def get(self, connection: Connection, site_id: UUID) -> SiteBaselineV1 | None:
        row = connection.execute(
            select(site_baseline.c.site_id, site_baseline.c.schedule_version_id, site_baseline.c.resource_version)
            .where(site_baseline.c.site_id == site_id)
        ).one_or_none()
        if row is None:
            return None
        return SiteBaselineV1(site_id=row.site_id, schedule_version_id=row.schedule_version_id, resource_version=row.resource_version)


class PostgresSiteBaselineWriter:
    def promote(self, connection: Connection, *, site_id: UUID, schedule_version_id: UUID,
                actor_id: UUID, occurred_at, expected_resource_version: int | None) -> SiteBaselineV1 | None:
        if expected_resource_version is None:
            try:
                # SAVEPOINT: a lost insert race must not poison the outer TX2
                # transaction, which still has to roll back cleanly.
                with connection.begin_nested():
                    row = connection.execute(
                        insert(site_baseline).values(
                            site_id=site_id,
                            schedule_version_id=schedule_version_id,
                            resource_version=1,
                            updated_at=occurred_at,
                            updated_by_actor_id=actor_id,
                        ).returning(site_baseline)
                    ).one()
            except IntegrityError as exc:
                # ONLY the unique-constraint race means "the baseline moved under
                # us". `site_baseline` also carries `fk_site_baseline_version_site`
                # and a NOT NULL FK on `updated_by_actor_id`; swallowing those as a
                # `None` return reported genuine data corruption to the planner as
                # a benign concurrent promotion, permanently hiding it. Anything
                # that is not the uniqueness race propagates as the fault it is.
                if _UNIQUE_BASELINE_CONSTRAINT not in str(getattr(exc, "orig", exc)):
                    raise
                return None
        else:
            row = connection.execute(
                update(site_baseline).where(
                    site_baseline.c.site_id == site_id,
                    site_baseline.c.resource_version == expected_resource_version,
                ).values(
                    schedule_version_id=schedule_version_id,
                    resource_version=site_baseline.c.resource_version + 1,
                    updated_at=occurred_at,
                    updated_by_actor_id=actor_id,
                ).returning(site_baseline)
            ).one_or_none()
            if row is None:
                return None
        return SiteBaselineV1(row.site_id, row.schedule_version_id, row.resource_version)
