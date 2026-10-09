# GitHub Actions deploy identity (Story 6.2 D9). No long-lived key exists:
# a job in the `portfolio` environment exchanges its OIDC token for a
# one-hour session that can push to ONE repository and do nothing else.
#
# StringEquals on both aud and sub, never StringLike: a wildcard sub is the
# classic way an OIDC trust admits every branch or every repository.
# 6.3 extends this role's permissions and adds required reviewers.

locals {
  github_issuer = "token.actions.githubusercontent.com"
  provider_arn  = var.github_oidc_provider_arn == null ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.existing[0].arn
}

# AWS ignores thumbprints for GitHub's issuer, so none is pinned.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.github_oidc_provider_arn == null ? 1 : 0

  url            = "https://${local.github_issuer}"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "existing" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  arn = var.github_oidc_provider_arn
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.name_prefix}-github-deploy"
  description          = "GitHub Actions (environment-scoped OIDC): push the backend image only"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Federated = local.provider_arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.github_issuer}:aud" = "sts.amazonaws.com"
            "${local.github_issuer}:sub" = "repo:${var.github_repository}:environment:${var.github_environment}"
          }
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "deploy" {
  name = "${var.name_prefix}-github-deploy"
  role = aws_iam_role.deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*" # GetAuthorizationToken has no resource-level scope
      },
      {
        Sid    = "PushBackendImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:DescribeImages",
        ]
        Resource = var.backend_repository_arn
      },
    ]
  })
}
