# Offline proof of the identity boundary (Story 6.1 D6; AC1 "public sign-up
# disabled"; F2, F3). Mock provider, no credentials.
mock_provider "aws" {}

variables {
  name_prefix           = "shiftmind-test"
  region                = "ap-southeast-1"
  app_domain            = "app.example.com"
  cognito_domain_prefix = "shiftmind-test"
  planner_email         = "planner@example.com"
}

run "sign_up_is_closed_and_passwords_are_long" {
  command = apply

  assert {
    condition     = one(aws_cognito_user_pool.this.admin_create_user_config).allow_admin_create_user_only == true
    error_message = "Public sign-up must be disabled (allow_admin_create_user_only)."
  }

  assert {
    condition     = one(aws_cognito_user_pool.this.password_policy).minimum_length == 12
    error_message = "Password minimum length must be 12."
  }

  assert {
    condition     = aws_cognito_user_pool.this.username_attributes == toset(["email"]) && aws_cognito_user_pool.this.auto_verified_attributes == toset(["email"])
    error_message = "Email must be the username and the auto-verified attribute."
  }

  assert {
    condition     = aws_cognito_user_pool.this.deletion_protection == "INACTIVE"
    error_message = "Deletion protection must be off so teardown works (AD-17)."
  }
}

run "bff_client_is_confidential_code_flow_with_exact_callback" {
  command = apply

  assert {
    condition     = aws_cognito_user_pool_client.bff.generate_secret == true
    error_message = "The BFF is a confidential client and needs a secret."
  }

  assert {
    condition     = aws_cognito_user_pool_client.bff.allowed_oauth_flows == toset(["code"]) && aws_cognito_user_pool_client.bff.allowed_oauth_flows_user_pool_client == true
    error_message = "Only the authorization-code flow may be enabled."
  }

  assert {
    condition     = aws_cognito_user_pool_client.bff.allowed_oauth_scopes == toset(["openid", "email"])
    error_message = "Scopes must be exactly openid and email (F2)."
  }

  assert {
    condition     = aws_cognito_user_pool_client.bff.supported_identity_providers == toset(["COGNITO"])
    error_message = "Cognito must be the only identity provider."
  }

  assert {
    condition     = aws_cognito_user_pool_client.bff.callback_urls == toset(["https://app.example.com/api/v1/auth/callback"])
    error_message = "The callback list must be exactly https://<app_domain>/api/v1/auth/callback (F2)."
  }

  assert {
    condition     = aws_cognito_user_pool_client.bff.prevent_user_existence_errors == "ENABLED"
    error_message = "User-existence errors must be suppressed."
  }
}

run "managed_login_v2_has_a_branding_style" {
  command = apply

  assert {
    condition     = aws_cognito_user_pool_domain.this.managed_login_version == 2
    error_message = "The domain must use managed login v2."
  }

  assert {
    condition     = aws_cognito_managed_login_branding.this.use_cognito_provided_values == true
    error_message = "Managed login v2 needs a branding style; use the Cognito-provided one."
  }

  assert {
    condition     = aws_cognito_user_pool.this.user_pool_tier == "ESSENTIALS"
    error_message = "Managed login v2 needs the ESSENTIALS tier."
  }
}

run "planner_is_emailed_a_temporary_password_and_never_has_one_in_code" {
  command = apply

  assert {
    condition     = aws_cognito_user.planner.username == "planner@example.com" && aws_cognito_user.planner.attributes["email_verified"] == "true"
    error_message = "The planner is created with a verified email."
  }

  assert {
    condition     = aws_cognito_user.planner.desired_delivery_mediums == toset(["EMAIL"])
    error_message = "The temporary password must be delivered by email only."
  }

  assert {
    condition     = aws_cognito_user.planner.password == null && aws_cognito_user.planner.temporary_password == null
    error_message = "No password may be set in code, tfvars or state."
  }
}

run "outputs_match_what_the_adapter_expects" {
  command = apply

  assert {
    condition     = !endswith(output.oidc_issuer, "/") && startswith(output.oidc_issuer, "https://cognito-idp.ap-southeast-1.amazonaws.com/")
    error_message = "The issuer must have no trailing slash (F3) and the regional cognito-idp host."
  }

  assert {
    condition     = output.cognito_domain == "shiftmind-test.auth.ap-southeast-1.amazoncognito.com"
    error_message = "The Cognito domain must be <prefix>.auth.<region>.amazoncognito.com."
  }

  assert {
    condition     = output.planner_subject == aws_cognito_user.planner.sub
    error_message = "planner_subject must be the user's sub (F9)."
  }
}
