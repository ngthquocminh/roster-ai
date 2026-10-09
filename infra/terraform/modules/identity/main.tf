# Cognito as the hosted OIDC IdP behind the FastAPI BFF (Story 6.1 D6, AD-3).
# The BFF is a confidential client doing the authorization-code + PKCE exchange
# server-side, so the client has a secret and the browser never sees a token.

locals {
  callback_url = "https://${var.app_domain}/api/v1/auth/callback"
}

resource "aws_cognito_user_pool" "this" {
  name = var.name_prefix

  # Email is the username. Verification is satisfied by creating the user with
  # email_verified = true (see aws_cognito_user.planner).
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # The API default is case-SENSITIVE, unlike the console, and the setting is
  # immutable: changing it later replaces the pool (new issuer, client secret and
  # planner sub). Off, so `Planner@Example.com` signs in as `planner@example.com`.
  username_configuration {
    case_sensitive = false
  }

  # ESSENTIALS is the default tier and the one managed login v2 needs; it is
  # stated so a provider default change cannot silently move the pool.
  user_pool_tier = "ESSENTIALS"

  # AD-17: data persists until explicit teardown, and teardown must work.
  deletion_protection = "INACTIVE"

  # Sign-up is closed: only an administrator can create users.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length = 12
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id

  # Managed login v2. Without a branding style (below), v2 login pages do not render.
  managed_login_version = 2
}

resource "aws_cognito_user_pool_client" "bff" {
  name         = "${var.name_prefix}-bff"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = true

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = [local.callback_url]

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_managed_login_branding" "this" {
  user_pool_id = aws_cognito_user_pool.this.id
  client_id    = aws_cognito_user_pool_client.bff.id

  use_cognito_provided_values = true

  depends_on = [aws_cognito_user_pool_domain.this]
}

# Cognito emails the temporary password; Terraform never sees one.
resource "aws_cognito_user" "planner" {
  user_pool_id = aws_cognito_user_pool.this.id
  username     = var.planner_email

  attributes = {
    email          = var.planner_email
    email_verified = "true"
  }

  desired_delivery_mediums = ["EMAIL"]
}
