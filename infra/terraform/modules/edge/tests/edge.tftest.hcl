# Offline proof of the edge configuration (Story 6.1 D2-D4, AC2 first clause).
# Mock providers, no credentials. It proves configuration *intent*; Task 8's
# real plan/apply/smoke proves AWS accepted it.
#
# Known gaps a mock cannot close, recorded in the story's mutation table:
#   - Which managed policy a behavior consumes: under a mock the `id` of a data
#     source is always null (override_data and mock_data honour every attribute
#     except `id`), so only the policy NAMES are asserted here. infra/scripts/
#     smoke-edge.sh compares the real attached policy IDs against the managed
#     policies on the live distribution.
#   - "CloudFront/listener consume the VALIDATED certificate ARN": under a mock
#     the validation resource echoes the certificate ARN, so the two are equal.
#   - "No port-80 listener": the test iterates every listener in
#     aws_lb_listener.this; a second, separately declared listener resource
#     would not be seen.
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
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

variables {
  name_prefix           = "shiftmind-test"
  app_domain            = "app.example.com"
  zone_id               = "Z0000000000000"
  vpc_id                = "vpc-0000000000000"
  app_subnet_ids        = ["subnet-aaaa", "subnet-bbbb"]
  alb_security_group_id = "sg-alb"
}

run "viewer_tls_is_1_2_and_no_behavior_allows_plain_http" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = one(aws_cloudfront_distribution.this.viewer_certificate).minimum_protocol_version == "TLSv1.2_2021"
    error_message = "Viewer minimum TLS must be TLSv1.2_2021."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.this.viewer_certificate).ssl_support_method == "sni-only"
    error_message = "Viewer certificate must use SNI only."
  }

  assert {
    condition = alltrue([
      for b in concat(
        [one(aws_cloudfront_distribution.this.default_cache_behavior)],
        tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)
      ) : b.viewer_protocol_policy != "allow-all"
    ])
    error_message = "No behavior may allow plain HTTP (viewer_protocol_policy = allow-all)."
  }

  assert {
    condition     = one(aws_cloudfront_distribution.this.default_cache_behavior).viewer_protocol_policy == "redirect-to-https"
    error_message = "The SPA behavior must redirect HTTP to HTTPS."
  }

  assert {
    condition     = aws_cloudfront_distribution.this.aliases == toset(["app.example.com"]) && aws_cloudfront_distribution.this.http_version == "http2and3" && aws_cloudfront_distribution.this.price_class == "PriceClass_200"
    error_message = "Alias, HTTP version and price class must match D4."
  }
}

run "vpc_origin_is_https_only_tls_1_2" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = one(aws_cloudfront_vpc_origin.alb.vpc_origin_endpoint_config).origin_protocol_policy == "https-only"
    error_message = "CloudFront must reach the ALB over HTTPS only."
  }

  assert {
    condition     = one(one(aws_cloudfront_vpc_origin.alb.vpc_origin_endpoint_config).origin_ssl_protocols).items == toset(["TLSv1.2"])
    error_message = "CloudFront-to-ALB must negotiate TLSv1.2 only."
  }

  assert {
    condition     = one(aws_cloudfront_vpc_origin.alb.vpc_origin_endpoint_config).https_port == 443
    error_message = "The VPC origin must target the ALB's HTTPS listener."
  }
}

run "alb_is_internal_https_only_with_a_long_idle_timeout" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = aws_lb.this.internal == true
    error_message = "The ALB must be internal."
  }

  assert {
    condition     = aws_lb.this.idle_timeout >= 16
    error_message = "ALB idle timeout must exceed the 15 s SSE heartbeat."
  }

  assert {
    condition     = aws_lb.this.drop_invalid_header_fields == true
    error_message = "The ALB must drop invalid header fields."
  }

  assert {
    condition     = length(aws_lb_listener.this) == 1
    error_message = "The ALB must have exactly one listener."
  }

  assert {
    condition = alltrue([
      for l in values(aws_lb_listener.this) :
      l.protocol == "HTTPS" && l.port == 443 && l.ssl_policy == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    ])
    error_message = "Every listener must be HTTPS:443 with the TLS 1.2+ policy and no port-80 listener may exist."
  }

  assert {
    condition     = aws_lb_target_group.api.target_type == "ip" && aws_lb_target_group.api.port == 8000
    error_message = "The target group must be ip-type on the API port."
  }

  assert {
    condition     = one(aws_lb_target_group.api.health_check).path == "/health" && one(aws_lb_target_group.api.health_check).matcher == "200"
    error_message = "Health check must be GET /health -> 200."
  }
}

run "api_behavior_streams_and_forwards_everything" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.ordered_cache_behavior) == 1
    error_message = "Exactly one ordered behavior (/api/*) is expected."
  }

  assert {
    condition     = tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)[0].path_pattern == "/api/*"
    error_message = "The ordered behavior must be /api/*."
  }

  assert {
    condition     = tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)[0].allowed_methods == toset(["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"])
    error_message = "/api/* must allow all seven methods."
  }

  assert {
    condition     = data.aws_cloudfront_cache_policy.caching_disabled.name == "Managed-CachingDisabled" && data.aws_cloudfront_cache_policy.caching_optimized.name == "Managed-CachingOptimized"
    error_message = "The cache policies must be the AWS-managed CachingDisabled (API) and CachingOptimized (SPA), looked up by name."
  }

  assert {
    condition     = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.name == "Managed-AllViewerExceptHostHeader"
    error_message = "/api/* must use the managed policy that forwards cookies, query strings, Origin, x-csrf-token and Last-Event-ID."
  }

  assert {
    condition     = tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)[0].compress == false
    error_message = "/api/* must not compress (SSE)."
  }

  assert {
    condition     = tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)[0].viewer_protocol_policy == "https-only"
    error_message = "/api/* must be https-only (a 301 on a POST would lose the body)."
  }

  assert {
    condition     = length(tolist(aws_cloudfront_distribution.this.ordered_cache_behavior)[0].function_association) == 0
    error_message = "The SPA rewrite function must not run on /api/*."
  }
}

run "api_origin_timeouts_allow_sse_and_are_not_capped" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = one([
      for o in aws_cloudfront_distribution.this.origin : one(o.vpc_origin_config).origin_read_timeout if o.origin_id == "api"
    ]) > 15
    error_message = "The API origin read timeout must exceed the 15 s SSE heartbeat."
  }

  assert {
    condition = alltrue([
      for o in aws_cloudfront_distribution.this.origin : o.response_completion_timeout == null || o.response_completion_timeout == 0
    ])
    error_message = "response_completion_timeout must stay unset: it would cap an SSE stream's total lifetime."
  }

  assert {
    condition = one([
      for o in aws_cloudfront_distribution.this.origin : o.domain_name if o.origin_id == "api"
    ]) == "origin.app.example.com"
    error_message = "The API origin hostname must be origin.<app_domain> so it matches the ALB certificate."
  }
}

run "spa_rewrite_is_on_the_default_behavior_and_errors_are_not_rewritten" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = length(aws_cloudfront_distribution.this.custom_error_response) == 0
    error_message = "custom_error_response is distribution-wide and would rewrite the API's own 401/403/404."
  }

  assert {
    condition     = one(one(aws_cloudfront_distribution.this.default_cache_behavior).function_association).event_type == "viewer-request"
    error_message = "The SPA rewrite must run on viewer-request of the default behavior."
  }

  assert {
    condition     = aws_cloudfront_function.spa_rewrite.runtime == "cloudfront-js-2.0" && aws_cloudfront_function.spa_rewrite.publish == true
    error_message = "The rewrite must be a published cloudfront-js-2.0 function."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.spa_rewrite.code, "indexOf('.') === -1") && strcontains(aws_cloudfront_function.spa_rewrite.code, "request.uri = '/index.html'")
    error_message = "The function must rewrite only extension-less URIs to /index.html (loaded from spa-rewrite.js)."
  }
}

run "spa_bucket_is_private_encrypted_and_oac_signed" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.spa.block_public_acls,
      aws_s3_bucket_public_access_block.spa.block_public_policy,
      aws_s3_bucket_public_access_block.spa.ignore_public_acls,
      aws_s3_bucket_public_access_block.spa.restrict_public_buckets,
    ])
    error_message = "All four Block Public Access flags must be on."
  }

  assert {
    condition     = one(aws_s3_bucket_ownership_controls.spa.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled with BucketOwnerEnforced."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.spa.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The SPA bucket must be encrypted at rest."
  }

  assert {
    condition     = aws_cloudfront_origin_access_control.spa.signing_protocol == "sigv4" && aws_cloudfront_origin_access_control.spa.signing_behavior == "always" && aws_cloudfront_origin_access_control.spa.origin_access_control_origin_type == "s3"
    error_message = "OAC must sign every request with sigv4."
  }

  assert {
    condition     = aws_s3_bucket.spa.bucket == "shiftmind-test-spa-123456789012"
    error_message = "The SPA bucket name must embed the account ID for global uniqueness."
  }
}

run "spa_bucket_policy_grants_only_this_distribution_and_denies_plaintext" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition = length([
      for st in jsondecode(aws_s3_bucket_policy.spa.policy).Statement : st if st.Effect == "Allow"
    ]) == 1
    error_message = "The bucket policy must contain exactly one Allow statement."
  }

  assert {
    condition = alltrue([
      for st in jsondecode(aws_s3_bucket_policy.spa.policy).Statement :
      st.Action == "s3:GetObject" &&
      st.Principal.Service == "cloudfront.amazonaws.com" &&
      st.Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.this.arn
      if st.Effect == "Allow"
    ])
    error_message = "The Allow statement must be s3:GetObject for cloudfront.amazonaws.com, bound to this distribution's ARN."
  }

  assert {
    condition = anytrue([
      for st in jsondecode(aws_s3_bucket_policy.spa.policy).Statement :
      st.Effect == "Deny" && st.Condition.Bool["aws:SecureTransport"] == "false"
      if st.Effect == "Deny"
    ])
    error_message = "The bucket policy must deny aws:SecureTransport = false."
  }

  # The Deny must cover every principal, every action, and both the bucket and its
  # objects: a Deny narrowed to one action or to the bucket ARN alone would still
  # carry the condition and pass the assertion above.
  assert {
    condition = alltrue([
      for st in jsondecode(aws_s3_bucket_policy.spa.policy).Statement :
      st.Principal == "*" && st.Action == "s3:*" &&
      toset(flatten([st.Resource])) == toset([aws_s3_bucket.spa.arn, "${aws_s3_bucket.spa.arn}/*"])
      if st.Effect == "Deny"
    ])
    error_message = "The plaintext Deny must be Principal *, Action s3:*, on the bucket and every object."
  }
}

run "dns_and_certificates_are_wired_to_the_zone" {
  command = apply

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  assert {
    condition     = aws_acm_certificate.cloudfront.domain_name == "app.example.com" && aws_acm_certificate.origin.domain_name == "origin.app.example.com"
    error_message = "Certificates must cover <app_domain> (CloudFront) and origin.<app_domain> (ALB)."
  }

  assert {
    condition     = aws_acm_certificate.cloudfront.validation_method == "DNS" && aws_acm_certificate.origin.validation_method == "DNS"
    error_message = "Both certificates must be DNS-validated."
  }

  assert {
    condition     = aws_route53_record.cloudfront_validation.type == "CNAME" && aws_route53_record.origin_validation.type == "CNAME" && aws_route53_record.cloudfront_validation.zone_id == "Z0000000000000" && aws_route53_record.origin_validation.zone_id == "Z0000000000000"
    error_message = "Each certificate must get a CNAME validation record in the hosted zone."
  }

  assert {
    condition     = aws_route53_record.origin.name == "origin.app.example.com" && aws_route53_record.origin.type == "A"
    error_message = "origin.<app_domain> must be an A alias to the ALB."
  }

  assert {
    condition     = aws_route53_record.app_a.name == "app.example.com" && aws_route53_record.app_aaaa.name == "app.example.com" && aws_route53_record.app_a.type == "A" && aws_route53_record.app_aaaa.type == "AAAA"
    error_message = "<app_domain> must have A and AAAA aliases to CloudFront."
  }
}
