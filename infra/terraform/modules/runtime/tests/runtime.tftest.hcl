# Offline proof of the runtime identities and the migrate task (Story 6.2 D6,
# D8, D10, D11). Mock provider, no credentials. That IAM evaluates these
# policies as intended is proved live by smoke-data.sh's two-sided
# simulate-principal-policy check.
# The task definition validates execution_role_arn as an ARN, so the mock
# needs a well-formed one; every other ARN stays random (and so distinct).
mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::111122223333:role/mock"
    }
  }
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "111122223333"
  }
}

variables {
  name_prefix                          = "shiftmind-test"
  environment                          = "test"
  region                               = "ap-southeast-1"
  secret_path_prefix                   = "shiftmind/test"
  database_url_secret_arn              = "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:shiftmind/test/database-url-AAAAAA"
  provisioning_database_url_secret_arn = "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:shiftmind/test/provisioning-database-url-BBBBBB"
  oidc_client_secret                   = "oidc-literal"
  csrf_secret                          = "CsrfLiteral0123456789"
  credentials_version                  = 1
  planner_subject                      = "sub-1234"
  planner_email                        = "planner@example.test"
  backend_image_digest                 = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}

run "repository_is_immutable_and_scanned" {
  command = apply

  assert {
    condition     = aws_ecr_repository.backend.image_tag_mutability == "IMMUTABLE"
    error_message = "Tags must be immutable: a digest, once pushed, never moves (AR27)."
  }

  assert {
    condition     = one(aws_ecr_repository.backend.image_scanning_configuration).scan_on_push == true
    error_message = "Images must be scanned on push."
  }

  assert {
    condition     = one(aws_ecr_repository.backend.encryption_configuration).encryption_type == "AES256"
    error_message = "The repository uses AES256."
  }

  assert {
    condition     = jsondecode(aws_ecr_lifecycle_policy.backend.policy).rules[0].selection.countNumber == 10 && jsondecode(aws_ecr_lifecycle_policy.backend.policy).rules[0].selection.countType == "imageCountMoreThan" && length(jsondecode(aws_ecr_lifecycle_policy.backend.policy).rules) == 1
    error_message = "Exactly one lifecycle rule keeps the 10 most recent images (6.5 rolls back to prior digests)."
  }
}

run "log_groups_retain_30_days" {
  command = apply

  assert {
    condition     = toset([for g in values(aws_cloudwatch_log_group.this) : g.name]) == toset(["/shiftmind/test/api", "/shiftmind/test/worker", "/shiftmind/test/migrate"])
    error_message = "One log group per service: api, worker, migrate."
  }

  assert {
    condition     = alltrue([for g in values(aws_cloudwatch_log_group.this) : g.retention_in_days == 30 && g.kms_key_id == null])
    error_message = "Every log group keeps 30 days (AD-17), with no CMK (D10)."
  }
}

run "cluster_has_no_container_insights" {
  command = apply

  assert {
    condition     = [for s in aws_ecs_cluster.this.setting : s.value if s.name == "containerInsights"] == ["disabled"]
    error_message = "Container Insights is on D10's not-added list."
  }
}

run "task_roles_have_no_policies" {
  command = apply

  assert {
    condition     = toset(keys(aws_iam_role.task)) == toset(["api", "worker"])
    error_message = "There are exactly two task roles."
  }

  # Attribute references only, never whole aws_iam_role objects: those carry
  # the provider's deprecated managed_policy_arns/inline_policy, and Terraform
  # 1.15 panics rendering a FAILED assertion over values with deprecation marks.
  # A separately declared attachment is invisible here; smoke-data.sh check 11
  # lists the live task roles' attached and inline policies instead.
  assert {
    condition = alltrue([
      for p in values(aws_iam_role_policy.execution) :
      !contains([aws_iam_role.task["api"].id, aws_iam_role.task["worker"].id], p.role)
    ])
    error_message = "No inline policy may attach to a task role (no backend code calls AWS)."
  }
}

# Exact sets: a superset (one more readable secret) reddens.
run "execution_roles_read_exactly_their_own_secrets" {
  command = apply

  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.execution["api"].policy).Statement : s.Resource if s.Action == "secretsmanager:GetSecretValue"
      ])) == toset([
      var.database_url_secret_arn, aws_secretsmanager_secret.oidc_client_secret.arn, aws_secretsmanager_secret.csrf_secret.arn,
    ])
    error_message = "api-exec reads exactly database-url, oidc-client-secret and csrf-secret."
  }

  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.execution["worker"].policy).Statement : s.Resource if s.Action == "secretsmanager:GetSecretValue"
    ])) == toset([var.database_url_secret_arn])
    error_message = "worker-exec reads exactly database-url."
  }

  assert {
    condition = toset(flatten([
      for s in jsondecode(aws_iam_role_policy.execution["migrate"].policy).Statement : s.Resource if s.Action == "secretsmanager:GetSecretValue"
    ])) == toset([var.database_url_secret_arn, var.provisioning_database_url_secret_arn])
    error_message = "migrate-exec reads exactly database-url and provisioning-database-url."
  }

  assert {
    # Explicit attribute references (see task_roles_have_no_policies).
    condition = { for k, p in aws_iam_role_policy.execution : k => p.role } == {
      api     = aws_iam_role.execution["api"].id
      worker  = aws_iam_role.execution["worker"].id
      migrate = aws_iam_role.execution["migrate"].id
    }
    error_message = "Each execution role has exactly its own inline policy."
  }
}

run "execution_roles_write_only_their_own_logs_and_pull_only_backend" {
  command = apply

  assert {
    condition = alltrue([
      for k, p in aws_iam_role_policy.execution : toset(flatten([
        for s in jsondecode(p.policy).Statement : s.Resource if contains(flatten([s.Action]), "logs:PutLogEvents")
      ])) == toset(["${aws_cloudwatch_log_group.this[k].arn}:*"])
    ])
    error_message = "Each execution role writes only to its own log group."
  }

  assert {
    condition = alltrue([
      for p in values(aws_iam_role_policy.execution) : toset(flatten([
        for s in jsondecode(p.policy).Statement : s.Resource if contains(flatten([s.Action]), "ecr:BatchGetImage")
      ])) == toset([aws_ecr_repository.backend.arn])
    ])
    error_message = "Execution roles pull only from the backend repository."
  }
}

run "no_wildcards_outside_ecr_authorization" {
  command = apply

  assert {
    condition = alltrue(flatten([
      for p in values(aws_iam_role_policy.execution) : [
        for s in jsondecode(p.policy).Statement :
        !contains(flatten([s.Action]), "*") && !anytrue([for a in flatten([s.Action]) : endswith(a, ":*")])
      ]
    ]))
    error_message = "No statement may grant Action \"*\" or a service-wide wildcard."
  }

  assert {
    condition = alltrue(flatten([
      for p in values(aws_iam_role_policy.execution) : [
        for s in jsondecode(p.policy).Statement : s.Action == "ecr:GetAuthorizationToken"
        if contains(flatten([s.Resource]), "*")
      ]
    ]))
    error_message = "Resource \"*\" is allowed only for ecr:GetAuthorizationToken."
  }

  assert {
    condition = alltrue(flatten([
      for p in values(aws_iam_role_policy.execution) : [for s in jsondecode(p.policy).Statement : s.Effect == "Allow"]
    ])) && alltrue([for p in values(aws_iam_role_policy.execution) : length(jsondecode(p.policy).Statement) == 4])
    error_message = "Each execution policy is exactly D8's four Allow statements."
  }
}

run "every_trust_is_ecs_tasks_from_this_account" {
  command = apply

  assert {
    condition = alltrue([
      # Attribute references only (see task_roles_have_no_policies).
      for trust in [
        aws_iam_role.task["api"].assume_role_policy, aws_iam_role.task["worker"].assume_role_policy,
        aws_iam_role.execution["api"].assume_role_policy, aws_iam_role.execution["worker"].assume_role_policy,
        aws_iam_role.execution["migrate"].assume_role_policy,
      ] :
      jsondecode(trust) == {
        Version = "2012-10-17"
        Statement = [{
          Effect    = "Allow"
          Principal = { Service = "ecs-tasks.amazonaws.com" }
          Action    = "sts:AssumeRole"
          Condition = { StringEquals = { "aws:SourceAccount" = "111122223333" } }
        }]
      }
    ])
    error_message = "Every runtime role trusts ecs-tasks.amazonaws.com only, with an aws:SourceAccount condition."
  }
}

run "migrate_task_runs_a_digest_with_tls_and_no_task_role" {
  command = apply

  assert {
    condition     = length(aws_ecs_task_definition.migrate) == 1
    error_message = "With a digest set there is exactly one migrate task definition."
  }

  assert {
    condition     = endswith(jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].image, "@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef") && startswith(jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].image, aws_ecr_repository.backend.repository_url)
    error_message = "The image must be <backend repository>@sha256:<digest>, never a tag."
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].command == ["python", "-m", "scripts.bootstrap_hosted", "--require-tls"]
    error_message = "The migrate task runs the hosted bootstrap with --require-tls."
  }

  assert {
    condition     = aws_ecs_task_definition.migrate[0].task_role_arn == null && aws_ecs_task_definition.migrate[0].execution_role_arn == aws_iam_role.execution["migrate"].arn
    error_message = "The migrate task has no task role and uses migrate-exec."
  }

  assert {
    condition = (
      jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].secrets == [
        { name = "ROSTERAI_DATABASE_URL", valueFrom = var.database_url_secret_arn },
        { name = "ROSTERAI_PROVISIONING_DATABASE_URL", valueFrom = var.provisioning_database_url_secret_arn },
      ] &&
      jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].environment == [
        { name = "SHIFTMIND_SEED_PLANNER_SUBJECT", value = "sub-1234" },
        { name = "SHIFTMIND_SEED_PLANNER_EMAIL", value = "planner@example.test" },
      ]
    )
    error_message = "The migrate task receives the two DB URLs as secrets and the seed planner as plain environment."
  }

  assert {
    condition = (
      aws_ecs_task_definition.migrate[0].requires_compatibilities == toset(["FARGATE"]) &&
      aws_ecs_task_definition.migrate[0].network_mode == "awsvpc" &&
      aws_ecs_task_definition.migrate[0].cpu == "512" && aws_ecs_task_definition.migrate[0].memory == "1024" &&
      one(aws_ecs_task_definition.migrate[0].runtime_platform).cpu_architecture == "X86_64" &&
      jsondecode(aws_ecs_task_definition.migrate[0].container_definitions)[0].logConfiguration.options["awslogs-group"] == "/shiftmind/test/migrate"
    )
    error_message = "Fargate, awsvpc, X86_64, 0.5 vCPU / 1 GB, logging to the migrate group."
  }
}

run "csrf_secret_is_write_only_and_oidc_is_plain" {
  command = apply

  assert {
    condition     = aws_secretsmanager_secret_version.csrf_secret.secret_string == null && aws_secretsmanager_secret_version.csrf_secret.secret_string_wo_version == 1
    error_message = "csrf-secret must be written only through secret_string_wo."
  }

  assert {
    condition     = aws_secretsmanager_secret_version.oidc_client_secret.secret_string == "oidc-literal"
    error_message = "oidc-client-secret is the identity module's value as a plain secret_string (6.1 D6)."
  }

  assert {
    condition = [aws_secretsmanager_secret.oidc_client_secret.name, aws_secretsmanager_secret.csrf_secret.name] == [
      "shiftmind/test/oidc-client-secret", "shiftmind/test/csrf-secret"
      ] && alltrue([
        for s in [aws_secretsmanager_secret.oidc_client_secret, aws_secretsmanager_secret.csrf_secret] : s.recovery_window_in_days == 0
    ])
    error_message = "Secrets follow shiftmind/<env>/<name> with no recovery window."
  }
}

run "no_task_definition_without_a_digest" {
  command = apply

  variables {
    backend_image_digest = null
  }

  assert {
    condition     = length(aws_ecs_task_definition.migrate) == 0 && output.migrate_task_definition_arn == null
    error_message = "Before the first image exists there is no migrate task definition."
  }
}

run "a_tag_is_not_a_digest" {
  command = plan

  variables {
    backend_image_digest = "latest"
  }

  expect_failures = [var.backend_image_digest]
}

run "a_short_digest_is_rejected" {
  command = plan

  variables {
    backend_image_digest = "sha256:abc123"
  }

  expect_failures = [var.backend_image_digest]
}
