output "deploy_role_arn" {
  description = "Role GitHub Actions assumes (repository secret AWS_DEPLOY_ROLE_ARN)."
  value       = aws_iam_role.deploy.arn
}

output "deploy_role_name" {
  description = "Name of the deploy role."
  value       = aws_iam_role.deploy.name
}

output "oidc_provider_arn" {
  description = "The GitHub OIDC provider the role trusts (managed here, or looked up)."
  value       = local.provider_arn
}

output "oidc_provider_managed" {
  description = "True when this module created the provider; false when it only looks one up."
  value       = var.github_oidc_provider_arn == null
}

output "deploy_subject" {
  description = "The exact OIDC sub the deploy role trusts."
  value       = "repo:${var.github_repository}:environment:${var.github_environment}"
}
