"""Contract tests for the canonical governed-capability manifest."""
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from application import contracts
from application.contracts.capability_manifest import (
    SCHEMA_VERSION,
    CapabilityError,
    CapabilityManifestV1,
    IncompleteManifestError,
    validate_manifest,
)
from application.capabilities.installed import INSTALLED_MODULES


def test_capability_manifest_v1_has_the_exact_ad20_shape() -> None:
    assert {field.name for field in fields(CapabilityManifestV1)} == {
        "capability_name",
        "capability_version",
        "input_schema_ref",
        "output_schema_ref",
        "risk_class",
        "permission",
        "scope",
        "version_semantics",
        "idempotency_semantics",
        "budget_limit",
        "timeout_seconds",
        "approval_policy",
        "audit_mapping",
        "evidence_mapping",
        "errors",
        "evaluation_fixtures",
        "schema_version",
    }


def test_capability_manifest_is_frozen_versioned_and_exported() -> None:
    manifest = CapabilityManifestV1(
        capability_name="example",
        capability_version="1",
        input_schema_ref="example.RequestV1",
        output_schema_ref="example.ResultV1",
        risk_class="inspect",
        permission="example:inspect",
        scope="current_site",
        version_semantics="pinned",
        idempotency_semantics="read-only",
        budget_limit=1,
        timeout_seconds=1.0,
        approval_policy="none",
        audit_mapping="tool call id",
        evidence_mapping="result fields",
        errors=("example_error",),
        evaluation_fixtures=("evals/golden/example.json",),
    )
    assert manifest.schema_version == SCHEMA_VERSION
    assert contracts.CapabilityManifestV1 is CapabilityManifestV1
    with pytest.raises(FrozenInstanceError):
        manifest.scope = "other"  # type: ignore[misc]


def test_capability_error_provides_the_general_error_vocabulary_base() -> None:
    assert issubclass(CapabilityError, Exception)
    assert CapabilityError.code == "capability_error"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"permission": ""}, "permission"),
        ({"errors": ()}, "errors"),
        ({"evaluation_fixtures": ()}, "evaluation_fixtures"),
        ({"budget_limit": 0}, "budget_limit"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"risk_class": "unknown"}, "risk_class"),
        ({"approval_policy": "sometimes"}, "approval_policy"),
        ({"input_schema_ref": "RequestV1"}, "input_schema_ref"),
        ({"output_schema_ref": "bad-path.Result"}, "output_schema_ref"),
        ({"capability_name": "not-a-name"}, "capability_name"),
    ],
)
def test_manifest_validation_rejects_each_incomplete_shape(changes, message) -> None:
    valid = INSTALLED_MODULES[0].manifest
    with pytest.raises(IncompleteManifestError, match=message):
        validate_manifest(replace(valid, **changes))


@pytest.mark.parametrize("module", INSTALLED_MODULES)
def test_every_installed_manifest_is_complete(module) -> None:
    validate_manifest(module.manifest)
