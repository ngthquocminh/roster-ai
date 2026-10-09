locals {
  # Provider default_tags; the cost allocation tags (modules/stack/cost.tf)
  # activate Project and Environment.
  default_tags = {
    Project     = "shiftmind"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Story 6.2 D6: three passwords generated per plan/apply and never stored.
# Ephemeral resources are in neither state nor a plan file; their values reach
# AWS only through write-only arguments (password_wo, secret_string_wo), which
# are sent only when db_credentials_version changes. 40 alphanumerics: URL-safe,
# and none of RDS's forbidden characters (/, @, ", space).
#
# They live here, not in a module, because `terraform test` cannot mock an
# ephemeral resource (F14, measured on 1.15.9); everything else is in
# modules/stack, which the offline tests target with literal passwords.
ephemeral "aws_secretsmanager_random_password" "migrator" {
  password_length     = 40
  exclude_punctuation = true
}

ephemeral "aws_secretsmanager_random_password" "login" {
  password_length     = 40
  exclude_punctuation = true
}

ephemeral "aws_secretsmanager_random_password" "csrf" {
  password_length     = 40
  exclude_punctuation = true
}

module "stack" {
  source = "../../modules/stack"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  region                = var.region
  environment           = var.environment
  availability_zones    = var.availability_zones
  vpc_cidr              = var.vpc_cidr
  hosted_zone_name      = var.hosted_zone_name
  app_domain            = var.app_domain
  cognito_domain_prefix = var.cognito_domain_prefix
  planner_email         = var.planner_email

  db_instance_class        = var.db_instance_class
  force_ssl_apply_method   = var.force_ssl_apply_method
  db_credentials_version   = var.db_credentials_version
  backend_image_digest     = var.backend_image_digest
  github_repository        = var.github_repository
  github_environment       = var.github_environment
  github_oidc_provider_arn = var.github_oidc_provider_arn
  monthly_budget_usd       = var.monthly_budget_usd
  budget_alert_email       = var.budget_alert_email

  migrator_password = ephemeral.aws_secretsmanager_random_password.migrator.random_password
  login_password    = ephemeral.aws_secretsmanager_random_password.login.random_password
  csrf_secret       = ephemeral.aws_secretsmanager_random_password.csrf.random_password
}
