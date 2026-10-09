
output "region" {
  description = "AWS region of the environment."
  value       = var.region
}

output "app_domain" {
  description = "Public hostname of the app."
  value       = var.app_domain
}

output "app_url" {
  description = "Public HTTPS URL of the app (APP_BASE_URL in Story 6.3)."
  value       = module.edge.app_url
}

output "origin_domain" {
  description = "Hostname CloudFront uses for the internal ALB."
  value       = module.edge.origin_domain
}

output "distribution_id" {
  description = "CloudFront distribution ID."
  value       = module.edge.distribution_id
}

output "spa_bucket_name" {
  description = "Private SPA bucket."
  value       = module.edge.spa_bucket_name
}

output "alb_arn" {
  description = "ARN of the internal ALB."
  value       = module.edge.alb_arn
}

output "api_target_group_arn" {
  description = "Target group the ECS API service registers into."
  value       = module.edge.api_target_group_arn
}

output "oidc_issuer" {
  description = "OIDC_ISSUER for the API (no trailing slash)."
  value       = module.identity.oidc_issuer
}

output "oidc_client_id" {
  description = "OIDC_CLIENT_ID for the API."
  value       = module.identity.oidc_client_id
}

output "oidc_client_secret" {
  description = "OIDC_CLIENT_SECRET for the API. Story 6.2 moves it into Secrets Manager."
  value       = module.identity.oidc_client_secret
  sensitive   = true
}

output "planner_subject" {
  description = "SHIFTMIND_SEED_PLANNER_SUBJECT: the planner's Cognito sub (F9)."
  value       = module.identity.planner_subject
}

output "cognito_domain" {
  description = "Hosted-login domain."
  value       = module.identity.cognito_domain
}

output "user_pool_id" {
  description = "Cognito user pool ID."
  value       = module.identity.user_pool_id
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.network.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = module.network.public_subnet_ids
}

output "app_subnet_ids" {
  description = "Private app subnet IDs (API and worker tasks run here)."
  value       = module.network.app_subnet_ids
}

output "data_subnet_ids" {
  description = "Private data subnet IDs (RDS in Story 6.2)."
  value       = module.network.data_subnet_ids
}

output "alb_security_group_id" {
  description = "ALB security group."
  value       = module.network.alb_security_group_id
}

output "api_security_group_id" {
  description = "API task security group."
  value       = module.network.api_security_group_id
}

output "worker_security_group_id" {
  description = "Worker task security group (no ingress rule)."
  value       = module.network.worker_security_group_id
}

output "migrator_security_group_id" {
  description = "Migrate task security group (no ingress rule)."
  value       = module.network.migrator_security_group_id
}

output "data_security_group_id" {
  description = "Data-tier security group."
  value       = module.network.data_security_group_id
}

output "app_route_table_id" {
  description = "Route table of the private app subnets."
  value       = module.network.app_route_table_id
}

output "data_route_table_id" {
  description = "Route table of the private data subnets."
  value       = module.network.data_route_table_id
}

# --- Story 6.2 ---------------------------------------------------------------
# Consumed by Story 6.3 (deploy), run-migrate.sh and smoke-data.sh. Nothing here
# is sensitive: ARNs and names, never a secret value.

output "db_instance_identifier" {
  description = "RDS instance identifier."
  value       = module.data.db_instance_identifier
}

output "db_address" {
  description = "RDS endpoint hostname (private)."
  value       = module.data.db_address
}

output "db_parameter_group_name" {
  description = "RDS parameter group (rds.force_ssl = 1)."
  value       = module.data.db_parameter_group_name
}

output "db_subnet_group_name" {
  description = "RDS subnet group over the data subnets."
  value       = module.data.db_subnet_group_name
}

output "evidence_bucket_name" {
  description = "Create-only versioned evidence bucket."
  value       = module.data.evidence_bucket_name
}

output "backend_repository_url" {
  description = "ECR repository URL of the backend image."
  value       = module.runtime.backend_repository_url
}

output "backend_repository_name" {
  description = "ECR repository name of the backend image."
  value       = module.runtime.backend_repository_name
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = module.runtime.cluster_name
}

output "migrate_task_definition_arn" {
  description = "Migrate task definition ARN; null until backend_image_digest is set."
  value       = module.runtime.migrate_task_definition_arn
}

output "task_role_arns" {
  description = "API and worker task roles (no permissions)."
  value       = module.runtime.task_role_arns
}

output "execution_role_arns" {
  description = "api/worker/migrate execution roles."
  value       = module.runtime.execution_role_arns
}

output "log_group_names" {
  description = "CloudWatch log group per service."
  value       = module.runtime.log_group_names
}

output "secret_arns" {
  description = "Secrets Manager ARN per secret (D6's table)."
  value = {
    database-url              = module.data.database_url_secret_arn
    provisioning-database-url = module.data.provisioning_database_url_secret_arn
    oidc-client-secret        = module.runtime.oidc_client_secret_arn
    csrf-secret               = module.runtime.csrf_secret_arn
  }
}

output "github_deploy_role_arn" {
  description = "Role GitHub Actions assumes (repository secret AWS_DEPLOY_ROLE_ARN)."
  value       = module.github_oidc.deploy_role_arn
}

output "github_oidc_provider_arn" {
  description = "GitHub OIDC provider the deploy role trusts."
  value       = module.github_oidc.oidc_provider_arn
}

output "budget_name" {
  description = "Account-wide monthly cost budget."
  value       = aws_budgets_budget.monthly.name
}

output "backend_repository_arn" {
  description = "ARN of the backend ECR repository."
  value       = module.runtime.backend_repository_arn
}

output "github_deploy_subject" {
  description = "The exact OIDC sub the deploy role trusts (repo:<owner>/<name>:environment:<env>)."
  value       = module.github_oidc.deploy_subject
}
