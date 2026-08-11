"""Application-owned capability grant composition (AD-2/AD-5)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from application.capabilities.scheduling_inspect import (
    CAPABILITY_NAME,
    InspectCapabilityManifest,
    scheduling_inspect_manifest,
)

PLANNER_ROLE = "planner"
SCHEDULING_INSPECT_POLICY = "scheduling_inspect_enabled"
POLICY_VERSION = "one-user-mvp-v1"


@dataclass(frozen=True)
class CapabilityGrantContextV1:
    """Trusted inputs; role/policy are constants until a second user is activated."""

    role: str
    site_id: UUID
    feature_policy: frozenset[str]
    conversation_id: UUID
    conversation_site_id: UUID


def compose_granted_capabilities(
    context: CapabilityGrantContextV1,
) -> tuple[InspectCapabilityManifest, ...]:
    if (
        context.role != PLANNER_ROLE
        or context.site_id != context.conversation_site_id
        or SCHEDULING_INSPECT_POLICY not in context.feature_policy
    ):
        return ()
    return (scheduling_inspect_manifest(),)


def resolve_granted_capability(
    granted: tuple[InspectCapabilityManifest, ...], proposed_name: str
) -> InspectCapabilityManifest | None:
    return next((item for item in granted if item.capability_name == proposed_name), None)


__all__ = [
    "CAPABILITY_NAME", "CapabilityGrantContextV1", "PLANNER_ROLE", "POLICY_VERSION",
    "SCHEDULING_INSPECT_POLICY", "compose_granted_capabilities", "resolve_granted_capability",
]
