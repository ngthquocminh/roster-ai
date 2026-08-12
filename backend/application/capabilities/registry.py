"""Application-owned capability grant composition (AD-2/AD-5)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from application.capabilities.installed import installed_modules
from application.capabilities.module import CapabilityModuleV1, validate_module

PLANNER_ROLE = "planner"
POLICY_VERSION = "one-user-mvp-v1"


@dataclass(frozen=True)
class CapabilityGrantContextV1:
    """Trusted inputs; role/policy are constants until a second user is activated.

    Currently constant in this milestone, and why: `role` is derived from the
    single active membership (the membership table has no role column),
    `feature_policy` is a server-side constant set, and `policy_version` is a
    server-side constant string. `site_id`, `conversation_id`, and
    `conversation_site_id` are genuinely varying server-derived values. Every
    field is branched on by `compose_granted_capabilities`, so substituting a
    real policy supplier later is a change of supplier, not of shape.
    """

    role: str
    site_id: UUID
    feature_policy: frozenset[str]
    conversation_id: UUID
    conversation_site_id: UUID
    revoked_conversation_ids: frozenset[UUID] = frozenset()


def compose_granted_capabilities(
    context: CapabilityGrantContextV1,
    modules: tuple[CapabilityModuleV1, ...] | None = None,
) -> tuple[CapabilityModuleV1, ...]:
    """Compose the granted set from trusted context only.

    Returns the granted declarations. An ungranted capability is ABSENT from
    the result, never present-and-denied (AD-2/Decision 4): the caller registers
    only what this returns, so a capability the run was not granted is a tool
    that does not exist rather than one that refuses.

    `modules` defaults to the installed set resolved at CALL time, not at import
    time, so manifest values read from configuration stay current. Passing an
    explicit tuple is what makes a removed-world composition a real composition.
    """
    resolved = installed_modules() if modules is None else modules
    if (context.site_id != context.conversation_site_id
            or context.conversation_id in context.revoked_conversation_ids):
        return ()
    granted = []
    for module in resolved:
        validate_module(module)
        if (context.role == module.required_role
                and module.required_feature_policy in context.feature_policy):
            granted.append(module)
    return tuple(granted)


def resolve_granted_capability(
    granted: tuple[CapabilityModuleV1, ...], proposed_name: str
) -> CapabilityModuleV1 | None:
    return next((item for item in granted if item.manifest.capability_name == proposed_name), None)


__all__ = [
    "CapabilityGrantContextV1", "PLANNER_ROLE", "POLICY_VERSION",
    "compose_granted_capabilities", "resolve_granted_capability",
]
