# Runtime identities (Story 6.2 D8). Every role trusts ecs-tasks only from
# this account. Policies are inline and resource-scoped; the AWS-managed
# AmazonECSTaskExecutionRolePolicy is deliberately not attached because it
# grants ECR and Logs on "*".
#
# Task roles carry NO policy: no backend code calls an AWS API (F9). 6.3
# extends api-exec/worker-exec for the secrets its task definitions add.

data "aws_caller_identity" "current" {}

locals {
  ecs_tasks_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
      },
    ]
  })

  # D6's "Readable by" column.
  execution_secrets = {
    api     = [var.database_url_secret_arn, aws_secretsmanager_secret.oidc_client_secret.arn, aws_secretsmanager_secret.csrf_secret.arn]
    worker  = [var.database_url_secret_arn]
    migrate = [var.database_url_secret_arn, var.provisioning_database_url_secret_arn]
  }

  execution_policies = {
    for service, secrets in local.execution_secrets : service => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "EcrAuth"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*" # GetAuthorizationToken has no resource-level scope
        },
        {
          Sid      = "PullBackendImage"
          Effect   = "Allow"
          Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
          Resource = aws_ecr_repository.backend.arn
        },
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "${aws_cloudwatch_log_group.this[service].arn}:*"
        },
        {
          Sid      = "ReadOwnSecrets"
          Effect   = "Allow"
          Action   = "secretsmanager:GetSecretValue"
          Resource = secrets
        },
      ]
    })
  }
}

resource "aws_iam_role" "task" {
  for_each = toset(["api", "worker"])

  name               = "${var.name_prefix}-${each.key}-task"
  description        = "${each.key} task role: no AWS permissions (no backend code calls AWS)"
  assume_role_policy = local.ecs_tasks_trust
}

resource "aws_iam_role" "execution" {
  for_each = local.execution_secrets

  name               = "${var.name_prefix}-${each.key}-exec"
  description        = "${each.key} execution role: pull the backend image, write its logs, read its secrets"
  assume_role_policy = local.ecs_tasks_trust
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.execution_policies

  name   = "${var.name_prefix}-${each.key}-exec"
  role   = aws_iam_role.execution[each.key].id
  policy = each.value
}
