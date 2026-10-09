# Mocked plan of the whole composition (Story 6.1 Task 6, extended by 6.2). The
# modules have their own policy tests; this file proves the WIRING between them:
# that the values one module consumes are the ones another produced or the
# operator supplied. Mock providers, no credentials.
#
# Every run targets modules/stack, not this root. The root generates three
# passwords with ephemeral resources, and Terraform 1.15 cannot load a
# configuration containing one under mock_provider (Story 6.2 F14, measured).
# The root's remaining lines -- providers, default_tags, the three ephemeral
# resources and the stack call -- are proved by `terraform validate` and the
# operator-run plan, not here.
mock_provider "aws" {
  # The migrate task definition validates its execution role ARN.
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock"
    }
  }

  mock_resource "aws_cognito_user_pool_client" {
    defaults = {
      client_secret = "mock-cognito-client-secret"
    }
  }

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:ap-southeast-1:123456789012:certificate/00000000-0000-0000-0000-000000000001"
      domain_validation_options = [{
        domain_name           = "validation.example.com"
        resource_record_name  = "_abc.validation.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_def.acm-validations.aws."
      }]
    }
  }

  mock_resource "aws_lb" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:loadbalancer/app/shiftmind-test-alb/0123456789abcdef"
      dns_name = "internal-shiftmind-test-alb-1.ap-southeast-1.elb.amazonaws.com"
      zone_id  = "Z1LMS91P8CMLE5"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:ap-southeast-1:123456789012:targetgroup/shiftmind-test-api/0123456789abcdef"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::123456789012:distribution/EDFDVBD6EXAMPLE"
      domain_name    = "d111111abcdef8.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::123456789012:function/shiftmind-test-spa-rewrite"
    }
  }
}

mock_provider "aws" {
  alias = "us_east_1"

  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000002"
      domain_validation_options = [{
        domain_name           = "validation.example.com"
        resource_record_name  = "_abc.validation.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_def.acm-validations.aws."
      }]
    }
  }
}

override_data {
  target = data.aws_route53_zone.this
  values = {
    zone_id = "Z0000000000000"
  }
}

variables {
  hosted_zone_name      = "example.com"
  app_domain            = "app.example.com"
  cognito_domain_prefix = "shiftmind-test"
  planner_email         = "planner@example.com"

  db_instance_class    = "db.t4g.micro"
  github_repository    = "example-owner/example-repo"
  monthly_budget_usd   = 100
  budget_alert_email   = "budget@example.com"
  backend_image_digest = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  migrator_password    = "MigratorLiteral0123456789"
  login_password       = "LoginLiteral0123456789"
  csrf_secret          = "CsrfLiteral0123456789"
}

run "edge_and_identity_agree_on_the_app_domain" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = module.edge.distribution_aliases == toset(["app.example.com"])
    error_message = "The CloudFront alias must equal app_domain."
  }

  assert {
    condition     = module.identity.callback_urls == toset(["https://app.example.com/api/v1/auth/callback"])
    error_message = "The Cognito callback host must equal app_domain."
  }

  assert {
    condition     = output.app_url == "https://app.example.com"
    error_message = "app_url must be the https URL of app_domain."
  }
}

run "alb_sits_in_the_network_modules_app_subnets" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = module.edge.alb_subnet_ids == toset(module.network.app_subnet_ids)
    error_message = "The ALB must be attached to the network module's private app subnets."
  }

  assert {
    condition     = length(module.network.app_subnet_ids) == 2 && length(setintersection(toset(module.network.app_subnet_ids), toset(module.network.public_subnet_ids))) == 0
    error_message = "App subnets must be two, distinct from the public subnets."
  }
}

run "default_availability_zones_are_the_first_two_of_the_region" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(module.network.app_subnet_ids) == 2
    error_message = "Two AZs by default."
  }

  assert {
    condition     = jsonencode(local.availability_zones) == jsonencode(["ap-southeast-1a", "ap-southeast-1b"])
    error_message = "The default AZs must be <region>a and <region>b."
  }
}

run "availability_zones_can_be_overridden" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  variables {
    availability_zones = ["ap-southeast-1b", "ap-southeast-1c"]
  }

  assert {
    condition     = jsonencode(local.availability_zones) == jsonencode(["ap-southeast-1b", "ap-southeast-1c"])
    error_message = "An explicit availability_zones list must win over the default."
  }
}

run "oidc_outputs_follow_the_adapter_contract" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = !endswith(output.oidc_issuer, "/")
    error_message = "oidc_issuer must have no trailing slash (F3)."
  }

  assert {
    condition     = output.cognito_domain == "shiftmind-test.auth.ap-southeast-1.amazoncognito.com"
    error_message = "cognito_domain must be built from the prefix and region."
  }
}

run "resources_are_named_from_the_environment" {
  command = apply

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  variables {
    environment = "staging"
  }

  # default_tags moved with the providers into the root, which no mocked run can
  # load (see the header); the cost-tag run below pins the tag KEYS instead.
  assert {
    condition     = local.name_prefix == "shiftmind-staging" && local.secret_path_prefix == "shiftmind/staging"
    error_message = "Names use shiftmind-<environment> and secrets shiftmind/<environment>/<name> (D9)."
  }
}

run "app_domain_must_be_a_dns_name" {
  command = plan

  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  variables {
    app_domain = "Not A Domain"
  }

  expect_failures = [var.app_domain]
}

# --- Story 6.2 wiring --------------------------------------------------------

run "rds_sits_in_the_network_modules_data_tier" {
  command = apply
  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = toset(module.data.db_subnet_ids) == toset(module.network.data_subnet_ids)
    error_message = "RDS must use exactly the network module's data subnets."
  }

  assert {
    condition     = toset(module.data.db_security_group_ids) == toset([module.network.data_security_group_id])
    error_message = "RDS's only security group must be the network module's data security group."
  }
}

run "migrate_task_seeds_the_identity_modules_planner" {
  command = apply
  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = jsondecode(module.runtime.migrate_container_definitions)[0].environment == [
      { name = "SHIFTMIND_SEED_PLANNER_SUBJECT", value = module.identity.planner_subject },
      { name = "SHIFTMIND_SEED_PLANNER_EMAIL", value = "planner@example.com" },
    ]
    error_message = "The migrate task must seed the Cognito user's sub and the planner email."
  }

  assert {
    condition = jsondecode(module.runtime.migrate_container_definitions)[0].secrets == [
      { name = "ROSTERAI_DATABASE_URL", valueFrom = module.data.database_url_secret_arn },
      { name = "ROSTERAI_PROVISIONING_DATABASE_URL", valueFrom = module.data.provisioning_database_url_secret_arn },
    ]
    error_message = "The migrate task must read the data module's two URL secrets."
  }

  assert {
    condition     = startswith(jsondecode(module.runtime.migrate_container_definitions)[0].image, "${output.backend_repository_url}@sha256:")
    error_message = "The migrate task runs the backend repository's image by digest."
  }
}

run "oidc_client_secret_comes_from_the_identity_module" {
  command = apply
  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = nonsensitive(module.runtime.oidc_client_secret_string == module.identity.oidc_client_secret) && nonsensitive(module.identity.oidc_client_secret == "mock-cognito-client-secret")
    error_message = "oidc-client-secret must hold the Cognito app client's secret."
  }
}

run "budget_is_account_wide_with_two_alerts" {
  command = apply
  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(aws_budgets_budget.monthly.cost_filter) == 0
    error_message = "The budget must be account-wide: a tag filter is blind to untagged spend (D11)."
  }

  assert {
    condition = (
      aws_budgets_budget.monthly.budget_type == "COST" && aws_budgets_budget.monthly.time_unit == "MONTHLY" &&
      tonumber(aws_budgets_budget.monthly.limit_amount) == 100 && aws_budgets_budget.monthly.limit_unit == "USD"
    )
    error_message = "A monthly COST budget of monthly_budget_usd."
  }

  assert {
    condition = toset([
      for n in aws_budgets_budget.monthly.notification :
      "${n.notification_type}-${n.threshold}-${n.threshold_type}-${n.comparison_operator}-${join(",", n.subscriber_email_addresses)}"
    ]) == toset(["ACTUAL-80-PERCENTAGE-GREATER_THAN-budget@example.com", "FORECASTED-100-PERCENTAGE-GREATER_THAN-budget@example.com"])
    error_message = "Alerts go to budget_alert_email at 80% ACTUAL and 100% FORECASTED."
  }
}

run "both_cost_tags_are_active" {
  command = apply
  module {
    source = "../../modules/stack"
  }

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = { for k, t in aws_ce_cost_allocation_tag.this : k => t.status } == { Project = "Active", Environment = "Active" }
    error_message = "Project and Environment must be active cost allocation tags."
  }
}
