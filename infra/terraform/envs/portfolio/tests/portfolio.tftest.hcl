# Mocked plan of the whole env root (Story 6.1 Task 6). The modules have their own
# policy tests; this file proves the WIRING between them: that the values one
# module consumes are the ones another produced or the operator supplied.
# Mock providers, no credentials.
mock_provider "aws" {
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
}

run "edge_and_identity_agree_on_the_app_domain" {
  command = apply

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

  variables {
    environment = "staging"
  }

  assert {
    condition     = local.name_prefix == "shiftmind-staging" && local.default_tags == { Project = "shiftmind", Environment = "staging", ManagedBy = "terraform" }
    error_message = "Names use shiftmind-<environment> and default tags carry Project, Environment and ManagedBy (D9)."
  }
}

run "app_domain_must_be_a_dns_name" {
  command = plan

  variables {
    app_domain = "Not A Domain"
  }

  expect_failures = [var.app_domain]
}
