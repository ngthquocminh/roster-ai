output "oidc_issuer" {
  description = "OIDC issuer (OIDC_ISSUER). No trailing slash: the adapter compares it with the discovery document's issuer verbatim."
  value       = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}

output "oidc_client_id" {
  description = "BFF app client ID (OIDC_CLIENT_ID)."
  value       = aws_cognito_user_pool_client.bff.id
}

output "oidc_client_secret" {
  description = "BFF app client secret (OIDC_CLIENT_SECRET). Story 6.2 moves it into Secrets Manager."
  value       = aws_cognito_user_pool_client.bff.client_secret
  sensitive   = true
}

output "planner_subject" {
  description = "The planner's Cognito sub, which becomes SHIFTMIND_SEED_PLANNER_SUBJECT (F9)."
  value       = aws_cognito_user.planner.sub
}

output "cognito_domain" {
  description = "Hosted-login domain, <prefix>.auth.<region>.amazoncognito.com."
  value       = "${aws_cognito_user_pool_domain.this.domain}.auth.${var.region}.amazoncognito.com"
}

output "user_pool_id" {
  description = "User pool ID."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "User pool ARN."
  value       = aws_cognito_user_pool.this.arn
}

output "callback_urls" {
  description = "Callback URLs registered on the BFF app client."
  value       = aws_cognito_user_pool_client.bff.callback_urls
}
