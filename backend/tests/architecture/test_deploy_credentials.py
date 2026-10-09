"""Story 6.2 AC2: no long-lived deploy key exists, in Terraform or in CI.

GitHub Actions reaches AWS only through OIDC (`modules/github_oidc`). These
guards fail if anyone adds the alternative: an IAM user or access key in
Terraform, or a static key input or variable in a workflow. Each guard has a
synthetic violating source, per repository convention.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_IAM_KEY_RESOURCE = re.compile(
    r"""^\s*(resource|data)\s+"(aws_iam_user|aws_iam_access_key)"\s""", re.MULTILINE
)
_STATIC_KEY_REFERENCE = re.compile(
    r"aws-access-key-id|aws-secret-access-key|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY"
)


def iam_key_declarations(terraform: str) -> list[str]:
    return [match.group(0).strip() for match in _IAM_KEY_RESOURCE.finditer(terraform)]


def static_key_references(workflow: str) -> list[str]:
    return _STATIC_KEY_REFERENCE.findall(workflow)


def _terraform_files() -> list[Path]:
    return [
        path
        for path in (REPO_ROOT / "infra").rglob("*.tf")
        if ".terraform" not in path.parts
    ]


def _workflow_files() -> list[Path]:
    workflows = REPO_ROOT / ".github" / "workflows"
    return sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")])


def test_no_terraform_file_declares_an_iam_user_or_access_key() -> None:
    files = _terraform_files()
    assert files, "no .tf file found; the guard would prove nothing"
    offenders = {
        str(path.relative_to(REPO_ROOT)): found
        for path in files
        if (found := iam_key_declarations(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_no_workflow_references_a_static_aws_key() -> None:
    files = _workflow_files()
    assert files, "no workflow found; the guard would prove nothing"
    offenders = {
        path.name: found
        for path in files
        if (found := static_key_references(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_iam_key_guard_detects_synthetic_violations() -> None:
    source = (
        'resource "aws_iam_user" "deploy" {\n  name = "x"\n}\n'
        'resource  "aws_iam_access_key" "deploy" {\n  user = "x"\n}\n'
        'data "aws_iam_user" "existing" {}\n'
        'resource "aws_iam_role" "fine" {}\n'
        '# resource "aws_iam_user_policy" is a different type\n'
    )
    assert iam_key_declarations(source) == [
        'resource "aws_iam_user"',
        'resource  "aws_iam_access_key"',
        'data "aws_iam_user"',
    ]


def test_static_key_guard_detects_synthetic_violations() -> None:
    workflow = (
        "      - uses: aws-actions/configure-aws-credentials@v6\n"
        "        with:\n"
        "          aws-access-key-id: ${{ secrets.KEY }}\n"
        "          aws-secret-access-key: ${{ secrets.SECRET }}\n"
        "        env:\n"
        "          AWS_ACCESS_KEY_ID: x\n"
        "          AWS_SECRET_ACCESS_KEY: y\n"
        "          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}\n"
    )
    assert static_key_references(workflow) == [
        "aws-access-key-id",
        "aws-secret-access-key",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ]
