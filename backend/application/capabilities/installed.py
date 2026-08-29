"""Statically reviewed installation set; AD-15 forbids runtime discovery.

The set is a literal tuple written out in `_INSTALLED_FACTORIES` and resolved by
a function call -- NOT a module-level constant.  Adding a capability is a source
change reviewed like any other; there is no discovery, no config, no entry
points.

Why a function rather than an import-time tuple: manifests read process
configuration (`scheduling_inspect_manifest()` resolves its row limit and
timeout from settings), so composing at import would both make
`application/**` unimportable without configuration and freeze operator-set
values for the lifetime of the process, contradicting `default_settings`'
documented "read fresh each call" contract.
"""
from __future__ import annotations

from application.capabilities.demonstration import demonstration_module
from application.capabilities.module import CapabilityModuleV1, validate_module
from application.capabilities.scheduling_compute import scheduling_compute_module
from application.capabilities.scheduling_draft import scheduling_draft_module
from application.capabilities.scheduling_inspect import scheduling_inspect_module
from application.capabilities.scheduling_optimize import scheduling_optimize_module
from application.capabilities.scheduling_baseline import scheduling_baseline_module
from application.contracts.capability_manifest import IncompleteManifestError

# The literal installation set. One line per governed capability.
_INSTALLED_FACTORIES = (
    scheduling_compute_module,
    scheduling_draft_module,
    scheduling_inspect_module,
    scheduling_optimize_module,
    scheduling_baseline_module,
    demonstration_module,
)


def installed_modules() -> tuple[CapabilityModuleV1, ...]:
    """Compose and validate the installed set from current configuration."""
    modules = tuple(factory() for factory in _INSTALLED_FACTORIES)
    names = [module.manifest.capability_name for module in modules]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        # Caught here rather than at per-run rendering, where it would fail
        # every agent construction instead of once at installation.
        raise IncompleteManifestError(
            f"installed capability names must be unique; duplicated: {duplicates}"
        )
    for module in modules:
        validate_module(module)
    return modules


def enabled_feature_policy(settings: object) -> frozenset[str]:
    """Resolve AD-2's feature policy from operator configuration.

    `compose_granted_capabilities` tests `required_feature_policy in
    feature_policy`, so the ONLY safe supplier is one where a module's presence
    depends on something outside the module. Building the set from the
    installed modules' own policy names -- the shape this replaces -- makes the
    predicate unfalsifiable: installing a capability grants it, including a
    consequential one whose approval suspension terminates a planner's turn.

    A declared policy with no corresponding setting raises rather than
    defaulting: a capability must never become grantable because nobody
    supplied its switch.
    """
    enabled: list[str] = []
    for module in installed_modules():
        policy = module.required_feature_policy
        if not hasattr(settings, policy):
            raise IncompleteManifestError(
                f"{module.manifest.capability_name} requires feature policy "
                f"{policy!r}, which no setting supplies"
            )
        if getattr(settings, policy):
            enabled.append(policy)
    return frozenset(enabled)


__all__ = ["enabled_feature_policy", "installed_modules"]
