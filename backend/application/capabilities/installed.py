"""Statically reviewed installation set; AD-15 forbids runtime discovery."""
from application.capabilities.demonstration import demonstration_module
from application.capabilities.module import CapabilityModuleV1
from application.capabilities.scheduling_inspect import scheduling_inspect_module
from application.contracts.capability_manifest import validate_manifest


def _installed_modules() -> tuple[CapabilityModuleV1, ...]:
    modules = (scheduling_inspect_module(), demonstration_module())
    for module in modules:
        validate_manifest(module.manifest)
    return modules


INSTALLED_MODULES = _installed_modules()

__all__ = ["INSTALLED_MODULES"]
