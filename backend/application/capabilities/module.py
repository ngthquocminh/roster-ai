"""Executable capability binding; manifest data remains framework-free (AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from application.contracts.capability_manifest import CapabilityError, CapabilityManifestV1


@dataclass(frozen=True)
class CapabilityModuleV1:
    manifest: CapabilityManifestV1
    handler: Callable[..., object]
    request_type: type
    error_type: type[CapabilityError]
    retryable_error_codes: frozenset[str]
    required_role: str
    required_feature_policy: str


__all__ = ["CapabilityModuleV1"]
