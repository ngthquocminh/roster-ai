"""AD-5/AD-20's pure-data declaration for a governed capability.

The manifest is serializable contract data.  It deliberately excludes the
handler and framework objects so durable records can retain the exact declared
capability version without binding application contracts to an agent runtime.

`RiskClassV1` is defined HERE rather than in `application/capabilities/`: the
manifest is the contract and capabilities are its consumers, so the dependency
must point capabilities -> contracts.  `capabilities/vocabulary.py` re-exports
this name, which keeps the AD-5 vocabulary importable from its original home
without `application/contracts/**` depending on `application/capabilities/**`.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Literal, get_args

SCHEMA_VERSION = "1"

RiskClassV1 = Literal[
    "inspect", "draft", "compute", "consequential", "prohibited"
]

ApprovalPolicyV1 = Literal["none", "exact_action"]

# Every risk class EXCEPT `prohibited`, derived from the vocabulary rather than
# hand-copied so a new class cannot silently fail validation.  `prohibited`
# names a capability the system must refuse to install at all, so a manifest
# declaring it is incomplete by construction -- there is no legitimate module
# that both declares itself prohibited and asks to be registered.
INSTALLABLE_RISK_CLASSES = tuple(
    value for value in get_args(RiskClassV1) if value != "prohibited"
)


class CapabilityError(Exception):
    """General base for failures declared by a capability manifest."""

    code: str = "capability_error"


class CapabilityApprovalRequired(CapabilityError):
    """Application signal translated to framework approval by the adapter.

    Carries NO precomputed result on purpose.  A handler raises this BEFORE
    doing its work, so an unapproved call performs nothing; the adapter grants
    approval by re-invoking the handler with `AgentDepsV1.tool_call_approved`
    set, and the handler then executes exactly once.
    """

    code = "approval_required"


class IncompleteManifestError(ValueError):
    """A declaration is unsafe or unusable for registration."""


@dataclass(frozen=True)
class CapabilityManifestV1:
    """Versioned authority, execution, audit, and evaluation declaration."""

    capability_name: str
    capability_version: str
    input_schema_ref: str
    output_schema_ref: str
    risk_class: RiskClassV1
    permission: str
    scope: str
    version_semantics: str
    idempotency_semantics: str
    budget_limit: int
    timeout_seconds: float
    approval_policy: ApprovalPolicyV1
    audit_mapping: str
    evidence_mapping: str
    errors: tuple[str, ...]
    evaluation_fixtures: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION


def validate_manifest(manifest: CapabilityManifestV1) -> None:
    """Reject incomplete declarations without consulting process or filesystem state."""
    string_fields = (
        field.name
        for field in fields(manifest)
        if isinstance(getattr(manifest, field.name), str)
    )
    for name in string_fields:
        if not getattr(manifest, name).strip():
            raise IncompleteManifestError(f"{name} must not be empty")
    if not manifest.capability_name.isidentifier():
        raise IncompleteManifestError("capability_name must be a valid identifier")
    for name in ("input_schema_ref", "output_schema_ref"):
        value = getattr(manifest, name)
        if len(value.split(".")) < 2 or any(not part.isidentifier() for part in value.split(".")):
            raise IncompleteManifestError(f"{name} must be a dotted object path")
    if manifest.budget_limit < 1:
        raise IncompleteManifestError("budget_limit must be at least 1")
    if manifest.timeout_seconds <= 0:
        raise IncompleteManifestError("timeout_seconds must be positive")
    if manifest.risk_class not in INSTALLABLE_RISK_CLASSES:
        raise IncompleteManifestError("risk_class is not recognized")
    if manifest.approval_policy not in get_args(ApprovalPolicyV1):
        raise IncompleteManifestError("approval_policy is not recognized")
    if not manifest.errors:
        raise IncompleteManifestError("errors must not be empty")
    if not manifest.evaluation_fixtures:
        raise IncompleteManifestError("evaluation_fixtures must not be empty")


__all__ = [
    "ApprovalPolicyV1",
    "CapabilityApprovalRequired",
    "CapabilityError",
    "CapabilityManifestV1",
    "INSTALLABLE_RISK_CLASSES",
    "IncompleteManifestError",
    "RiskClassV1",
    "SCHEMA_VERSION",
    "validate_manifest",
]
