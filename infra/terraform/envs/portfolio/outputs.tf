# Consumed by Story 6.2 (data and runtime) and 6.3 (deploy), and by
# infra/scripts/smoke-edge.sh (`terraform output -json`).

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
