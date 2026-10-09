# The API's two non-database secrets (Story 6.2 D6). The database URLs live in
# modules/data beside the instance whose endpoint they embed.

resource "aws_secretsmanager_secret" "oidc_client_secret" {
  name                    = "${var.secret_path_prefix}/oidc-client-secret"
  description             = "OIDC_CLIENT_SECRET (api only)"
  recovery_window_in_days = 0
}

# A plain secret_string on purpose: the value is already in state (6.1 D6),
# and a plain value follows a replaced Cognito client automatically.
resource "aws_secretsmanager_secret_version" "oidc_client_secret" {
  secret_id     = aws_secretsmanager_secret.oidc_client_secret.id
  secret_string = var.oidc_client_secret
}

resource "aws_secretsmanager_secret" "csrf_secret" {
  name                    = "${var.secret_path_prefix}/csrf-secret"
  description             = "CSRF_SECRET (api only)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "csrf_secret" {
  secret_id                = aws_secretsmanager_secret.csrf_secret.id
  secret_string_wo         = var.csrf_secret
  secret_string_wo_version = var.credentials_version
}
