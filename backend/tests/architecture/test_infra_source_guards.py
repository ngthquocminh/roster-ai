"""Story 6.2: Terraform facts that `terraform test` cannot see.

`replace_triggered_by` is a lifecycle argument, not a resource value, so no
mocked assertion can read it; and "the evidence bucket has no lifecycle rule"
is the absence of a resource, which an assertion cannot reference at all. Both
are read from the module source instead. Each guard has a synthetic violation.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_MODULE = REPO_ROOT / "infra" / "terraform" / "modules" / "data"
URL_SECRET_VERSIONS = ("database_url", "provisioning_database_url")


def resource_block(source: str, resource_type: str, name: str) -> str | None:
    """Return the body of `resource "<type>" "<name>" { ... }` by brace depth."""
    match = re.search(rf'^resource\s+"{resource_type}"\s+"{name}"\s*\{{', source, re.MULTILINE)
    if match is None:
        return None
    depth = 0
    for index in range(match.end() - 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.end() : index]
    return None


def versions_missing_instance_trigger(source: str) -> list[str]:
    missing = []
    for name in URL_SECRET_VERSIONS:
        body = resource_block(source, "aws_secretsmanager_secret_version", name)
        trigger = re.search(r"replace_triggered_by\s*=\s*\[\s*aws_db_instance\.this\.id\s*\]", body or "")
        if body is None or trigger is None:
            missing.append(name)
    return missing


def lifecycle_configurations(source: str) -> list[str]:
    return re.findall(r'^resource\s+"aws_s3_bucket_lifecycle_configuration"\s+"(\w+)"', source, re.MULTILINE)


def _module_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(DATA_MODULE.glob("*.tf")))


def test_url_secrets_are_rewritten_when_the_instance_is_replaced() -> None:
    assert versions_missing_instance_trigger(_module_source()) == []


def test_evidence_bucket_has_no_lifecycle_rule() -> None:
    assert lifecycle_configurations(_module_source()) == []


def test_trigger_guard_detects_synthetic_violations() -> None:
    good = (
        'resource "aws_secretsmanager_secret_version" "database_url" {\n'
        "  lifecycle {\n    replace_triggered_by = [aws_db_instance.this.id]\n  }\n}\n"
    )
    without = 'resource "aws_secretsmanager_secret_version" "provisioning_database_url" {\n  secret_id = "x"\n}\n'
    wrong_target = (
        'resource "aws_secretsmanager_secret_version" "provisioning_database_url" {\n'
        "  lifecycle {\n    replace_triggered_by = [aws_db_parameter_group.this.id]\n  }\n}\n"
    )
    assert versions_missing_instance_trigger(good + without) == ["provisioning_database_url"]
    assert versions_missing_instance_trigger(good + wrong_target) == ["provisioning_database_url"]
    assert versions_missing_instance_trigger(good) == ["provisioning_database_url"]


def test_lifecycle_guard_detects_a_synthetic_violation() -> None:
    assert lifecycle_configurations(
        'resource "aws_s3_bucket_lifecycle_configuration" "evidence" {\n  bucket = "x"\n}\n'
    ) == ["evidence"]
