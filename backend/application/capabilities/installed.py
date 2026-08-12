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
from application.capabilities.scheduling_inspect import scheduling_inspect_module
from application.contracts.capability_manifest import IncompleteManifestError

# The literal installation set. One line per governed capability.
_INSTALLED_FACTORIES = (scheduling_inspect_module, demonstration_module)


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


__all__ = ["installed_modules"]
