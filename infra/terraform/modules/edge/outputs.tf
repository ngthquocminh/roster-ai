output "app_url" {
  description = "Public HTTPS URL of the app."
  value       = "https://${var.app_domain}"
}

output "origin_domain" {
  description = "Hostname CloudFront uses for the internal ALB (origin.<app_domain>)."
  value       = local.origin_domain
}

output "distribution_id" {
  description = "CloudFront distribution ID (cache invalidation in Story 6.3)."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "CloudFront distribution ARN."
  value       = aws_cloudfront_distribution.this.arn
}

output "alb_arn" {
  description = "ARN of the internal ALB."
  value       = aws_lb.this.arn
}

output "alb_dns_name" {
  description = "Internal DNS name of the ALB."
  value       = aws_lb.this.dns_name
}

output "api_target_group_arn" {
  description = "Target group the ECS API service registers into (Story 6.3)."
  value       = aws_lb_target_group.api.arn
}

output "spa_bucket_name" {
  description = "Private SPA bucket (Story 6.3 publishes the web build here)."
  value       = aws_s3_bucket.spa.id
}

output "spa_bucket_arn" {
  description = "ARN of the SPA bucket."
  value       = aws_s3_bucket.spa.arn
}

output "distribution_aliases" {
  description = "Aliases (CNAMEs) the distribution answers to; exactly [app_domain]."
  value       = aws_cloudfront_distribution.this.aliases
}

output "alb_subnet_ids" {
  description = "Subnets the internal ALB is attached to."
  value       = aws_lb.this.subnets
}
