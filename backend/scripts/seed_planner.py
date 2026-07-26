"""Operator-only provisioning for ShiftMind's single seeded planner."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import Engine, create_engine, func, select

from adapters.postgres.schema import (
    app_user,
    membership,
    organization,
    site,
)
from settings import Settings, default_settings


_PROVISION_LOCK_KEY: Final[int] = 0x53484946544D494E


class SeedPlannerConflictError(ValueError):
    """Provisioning would violate the one-user/one-membership contract."""


@dataclass(frozen=True)
class SeedPlannerResult:
    app_user_id: UUID
    membership_id: UUID
    site_id: UUID
    subject: str
    email: str
    created: bool


def provision_seed_planner(
    *,
    subject: str,
    email: str,
    site_id: UUID,
    engine: Engine,
) -> SeedPlannerResult:
    """Create or replay the exact seeded identity in one transaction."""
    normalized_subject = subject.strip()
    normalized_email = email.strip()
    if not normalized_subject or not normalized_email:
        raise ValueError("Seed planner subject and email must be non-empty")

    with engine.begin() as connection:
        connection.execute(select(func.pg_advisory_xact_lock(_PROVISION_LOCK_KEY)))
        existing_user = connection.execute(
            select(
                app_user.c.id,
                app_user.c.idp_subject,
                app_user.c.email,
                app_user.c.disabled_at,
            )
            .order_by(app_user.c.id)
            .limit(1)
        ).one_or_none()

        if existing_user is not None:
            if (
                existing_user.idp_subject != normalized_subject
                or existing_user.email != normalized_email
                or existing_user.disabled_at is not None
            ):
                raise SeedPlannerConflictError(
                    "A different or disabled application user is already provisioned"
                )
            existing_membership = connection.execute(
                select(membership.c.id, membership.c.site_id)
                .where(
                    membership.c.app_user_id == existing_user.id,
                    membership.c.revoked_at.is_(None),
                )
                .limit(1)
            ).one_or_none()
            if existing_membership is not None:
                if existing_membership.site_id != site_id:
                    raise SeedPlannerConflictError(
                        "The active membership belongs to a different site"
                    )
                return SeedPlannerResult(
                    app_user_id=existing_user.id,
                    membership_id=existing_membership.id,
                    site_id=existing_membership.site_id,
                    subject=existing_user.idp_subject,
                    email=existing_user.email,
                    created=False,
                )
            app_user_id = existing_user.id
        else:
            app_user_id = connection.execute(
                app_user.insert()
                .values(
                    idp_subject=normalized_subject,
                    email=normalized_email,
                )
                .returning(app_user.c.id)
            ).scalar_one()

        membership_id = connection.execute(
            membership.insert()
            .values(app_user_id=app_user_id, site_id=site_id)
            .returning(membership.c.id)
        ).scalar_one()
        return SeedPlannerResult(
            app_user_id=app_user_id,
            membership_id=membership_id,
            site_id=site_id,
            subject=normalized_subject,
            email=normalized_email,
            created=True,
        )


def seed_planner_from_env(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> SeedPlannerResult:
    """Read operator inputs and provision against Story 1.1's seeded site."""
    subject = os.environ.get("SHIFTMIND_SEED_PLANNER_SUBJECT", "").strip()
    email = os.environ.get("SHIFTMIND_SEED_PLANNER_EMAIL", "").strip()
    if not subject:
        raise ValueError("SHIFTMIND_SEED_PLANNER_SUBJECT is required")
    if not email:
        raise ValueError("SHIFTMIND_SEED_PLANNER_EMAIL is required")

    resolved_settings = settings or default_settings()
    resolved_engine = engine or create_engine(resolved_settings.database_url)
    owns_engine = engine is None
    try:
        with resolved_engine.connect() as connection:
            site_id = connection.execute(
                select(site.c.id)
                .join(
                    organization,
                    organization.c.id == site.c.organization_id,
                )
                .where(
                    organization.c.name == "ShiftMind",
                    site.c.name == "Seeded Site",
                )
                .order_by(site.c.id)
                .limit(1)
            ).scalar_one_or_none()
        if site_id is None:
            raise ValueError(
                "Story 1.1 seeded site 'ShiftMind / Seeded Site' does not exist"
            )
        return provision_seed_planner(
            subject=subject,
            email=email,
            site_id=site_id,
            engine=resolved_engine,
        )
    finally:
        if owns_engine:
            resolved_engine.dispose()


def main() -> None:
    print(json.dumps(asdict(seed_planner_from_env()), default=str, indent=2))


if __name__ == "__main__":
    main()
