"""Executable capability binding; manifest data remains framework-free (AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from typing import Callable

from application.contracts.capability_manifest import (
    CapabilityError,
    CapabilityManifestV1,
    IncompleteManifestError,
    validate_manifest,
)


@dataclass(frozen=True)
class CapabilityModuleV1:
    """Everything the adapter needs to render one governed capability.

    `request_argument` is DECLARED rather than derived from the handler's
    signature: it is the model-facing JSON key, so deriving it from a Python
    parameter name would let a purely local rename silently change the tool's
    wire contract and invalidate frozen golden cases.

    `model_facing_text_field`, when set, names the single result field the model
    receives instead of the whole record -- the explicit replacement for the
    adapter guessing by result shape.  Left `None`, the full record is rendered.
    """

    manifest: CapabilityManifestV1
    handler: Callable[..., object]
    request_type: type
    error_type: type[CapabilityError]
    retryable_error_codes: frozenset[str]
    required_role: str
    required_feature_policy: str
    request_argument: str = "request"
    model_facing_text_field: str | None = None


def validate_module(module: CapabilityModuleV1) -> None:
    """Reject an unusable module declaration at registration, never at first call."""
    validate_manifest(module.manifest)
    name = module.manifest.capability_name

    undeclared = module.retryable_error_codes - set(module.manifest.errors)
    if undeclared:
        # Otherwise the model-visible error vocabulary would exceed the declared
        # one: a code the manifest never advertises could still reach the model
        # as a correctable retry.
        raise IncompleteManifestError(
            f"{name} marks undeclared error codes retryable: {sorted(undeclared)}"
        )

    parameters = tuple(signature(module.handler).parameters)
    if len(parameters) < 3:
        raise IncompleteManifestError(
            f"{name} handler must accept (deps, request, manifest)"
        )
    if module.request_argument != parameters[1]:
        raise IncompleteManifestError(
            f"{name} declares request argument {module.request_argument!r} "
            f"but its handler names it {parameters[1]!r}"
        )
    if not module.request_argument.isidentifier():
        raise IncompleteManifestError(f"{name} request argument must be an identifier")


__all__ = ["CapabilityModuleV1", "validate_module"]
