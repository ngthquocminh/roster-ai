# Two ACM certificates, both DNS-validated in the existing hosted zone (D3):
#   - us-east-1 for the CloudFront alias <app_domain> (CloudFront only reads
#     certificates from us-east-1);
#   - in the ALB's region for origin.<app_domain>. CloudFront validates the
#     origin certificate against the origin domain name, and an internal-*.elb
#     name cannot carry an ACM certificate (D2).
# CloudFront and the listener consume the *validation* resources' ARNs, so
# neither can be created against a certificate that is still pending.

locals {
  origin_domain = "origin.${var.app_domain}"
}

resource "aws_acm_certificate" "cloudfront" {
  provider = aws.us_east_1

  domain_name       = var.app_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "origin" {
  domain_name       = local.origin_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Each certificate covers exactly one name (no SANs), so it has exactly one
# validation option; `one()` makes that an enforced assumption. It also keeps the
# resources free of for_each keys derived from apply-time values.
resource "aws_route53_record" "cloudfront_validation" {
  zone_id         = var.zone_id
  name            = one(aws_acm_certificate.cloudfront.domain_validation_options).resource_record_name
  type            = one(aws_acm_certificate.cloudfront.domain_validation_options).resource_record_type
  records         = [one(aws_acm_certificate.cloudfront.domain_validation_options).resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_route53_record" "origin_validation" {
  zone_id         = var.zone_id
  name            = one(aws_acm_certificate.origin.domain_validation_options).resource_record_name
  type            = one(aws_acm_certificate.origin.domain_validation_options).resource_record_type
  records         = [one(aws_acm_certificate.origin.domain_validation_options).resource_record_value]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cloudfront" {
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.cloudfront.arn
  validation_record_fqdns = [aws_route53_record.cloudfront_validation.fqdn]
}

resource "aws_acm_certificate_validation" "origin" {
  certificate_arn         = aws_acm_certificate.origin.arn
  validation_record_fqdns = [aws_route53_record.origin_validation.fqdn]
}
