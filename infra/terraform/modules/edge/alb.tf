# Internal ALB (D2, D4). CloudFront reaches it through a VPC origin; it has no
# public address and no port-80 listener.

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.app_subnet_ids

  # Explicit and above the API's fixed 15 s SSE heartbeat (F6), so an idle
  # stream is never cut between heartbeats.
  idle_timeout               = 60
  drop_invalid_header_fields = true

  # Teardown must work (AD-17).
  enable_deletion_protection = false
}

# `ip` targets because ECS Fargate tasks register by ENI address. Empty until
# Story 6.3, so the ALB answers 503 on every request until then.
resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = var.api_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path     = "/health"
    protocol = "HTTP"
    matcher  = "200"
  }

  # Draining is slow by default (300 s); an empty practice target group should
  # not make teardown wait on it.
  deregistration_delay = 30
}

# One HTTPS:443 listener and no port-80 listener (D4). The listeners are a map so
# the test can iterate over every listener the ALB has.
locals {
  listeners = {
    https = { port = 443, protocol = "HTTPS" }
  }
}

resource "aws_lb_listener" "this" {
  for_each = local.listeners

  load_balancer_arn = aws_lb.this.arn
  port              = each.value.port
  protocol          = each.value.protocol
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.origin.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
