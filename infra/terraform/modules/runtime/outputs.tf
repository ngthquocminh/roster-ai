output "backend_repository_url" {
  description = "ECR repository URL of the backend image."
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_repository_arn" {
  description = "ARN of the backend ECR repository."
  value       = aws_ecr_repository.backend.arn
}

output "backend_repository_name" {
  description = "Name of the backend ECR repository."
  value       = aws_ecr_repository.backend.name
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "migrate_task_definition_arn" {
  description = "ARN of the migrate task definition; null until backend_image_digest is set."
  value       = one(aws_ecs_task_definition.migrate[*].arn)
}

output "task_role_arns" {
  description = "API and worker task roles (no permissions)."
  value       = { for k, r in aws_iam_role.task : k => r.arn }
}

output "execution_role_arns" {
  description = "api/worker/migrate execution roles."
  value       = { for k, r in aws_iam_role.execution : k => r.arn }
}

output "log_group_names" {
  description = "CloudWatch log group per service."
  value       = { for k, g in aws_cloudwatch_log_group.this : k => g.name }
}

output "oidc_client_secret_arn" {
  description = "Secret holding OIDC_CLIENT_SECRET."
  value       = aws_secretsmanager_secret.oidc_client_secret.arn
}

output "csrf_secret_arn" {
  description = "Secret holding CSRF_SECRET."
  value       = aws_secretsmanager_secret.csrf_secret.arn
}

# For the env-root wiring tests (assertions reach a module only through its
# outputs). The container definition holds secret ARNs, never values.
output "migrate_container_definitions" {
  description = "The migrate task's container definitions (JSON); null until backend_image_digest is set."
  value       = one(aws_ecs_task_definition.migrate[*].container_definitions)
}

output "oidc_client_secret_string" {
  description = "The value stored in oidc-client-secret, to prove it is the identity module's."
  value       = aws_secretsmanager_secret_version.oidc_client_secret.secret_string
  sensitive   = true
}
