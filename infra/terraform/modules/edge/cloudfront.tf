# CloudFront (D2, D4): SPA from the private bucket by default, /api/* through a
# VPC origin to the internal ALB.

# Looked up by name, never by hardcoded ID. A wrong name fails at plan time.
data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# Forwards every cookie, every query string and every viewer header except Host:
# Origin, x-csrf-token and Last-Event-ID reach the API unchanged (F4, F6).
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "${var.name_prefix}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Serve /index.html for extension-less paths so SPA deep links work"
  publish = true
  code    = file("${path.module}/spa-rewrite.js")
}

# The ALB is internal, so CloudFront reaches it as a VPC origin. HTTPS only, TLS
# 1.2. The https_port is the listener's; the http_port is required by the API
# but unused, because the ALB has no port-80 listener.
resource "aws_cloudfront_vpc_origin" "alb" {
  vpc_origin_endpoint_config {
    name                   = "${var.name_prefix}-alb"
    arn                    = aws_lb.this.arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "https-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  depends_on = [aws_lb_listener.this]
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_200"
  default_root_object = "index.html"
  aliases             = [var.app_domain]
  comment             = "${var.name_prefix} SPA and API"

  origin {
    origin_id                = "spa"
    domain_name              = aws_s3_bucket.spa.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.spa.id
  }

  # The origin hostname must match a name on the ALB's certificate (D2), so it
  # is origin.<app_domain>, not the internal-*.elb.amazonaws.com name.
  origin {
    origin_id   = "api"
    domain_name = local.origin_domain

    vpc_origin_config {
      vpc_origin_id = aws_cloudfront_vpc_origin.alb.id
      # Above the 15 s SSE heartbeat (F6). response_completion_timeout is left
      # unset on purpose: setting it would cap an SSE stream's total lifetime.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }

  default_cache_behavior {
    target_origin_id       = "spa"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  # All seven methods, so Story 6.4's mutation-denial probes are answered by
  # the API's own denial rather than a CloudFront 403. https-only because a 301
  # on a POST would lose the body.
  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    viewer_protocol_policy   = "https-only"
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    compress                 = false
  }

  # No custom_error_response: error responses are distribution-wide, so a
  # 403/404 -> /index.html mapping would also rewrite the API's own RFC 7807
  # 401/403/404 (including the CSRF 403) into an HTML 200 (D4).

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.cloudfront.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
