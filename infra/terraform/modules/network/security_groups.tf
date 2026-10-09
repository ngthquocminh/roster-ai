# Security groups (Story 6.1 D5), built from standalone rule resources.
#   alb    in 443 from the CloudFront origin-facing prefix list; out 8000 to api
#   api    in 8000 from alb only; out 443 anywhere; out 5432 to data
#   worker NO ingress rule at all; out 443 anywhere; out 5432 to data
#   migrator NO ingress rule at all; out 443 anywhere; out 5432 to data (6.2 D12)
#   data   in 5432 from api, worker and migrator; no egress

# Counts as roughly 55 rules against the per-SG rule quota, so `alb` keeps this
# as its only ingress rule.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Internal ALB: HTTPS from CloudFront only"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-alb" }
}

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api"
  description = "API tasks: port 8000 from the ALB only"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-api" }
}

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker"
  description = "Worker tasks: no inbound listener"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-worker" }
}

# The one-off migrate/bootstrap task (Story 6.2 D12). Egress 443 is anywhere
# because ECR, Secrets Manager and Logs are reached through the single NAT, not
# interface endpoints.
resource "aws_security_group" "migrator" {
  name        = "${var.name_prefix}-migrator"
  description = "Migrate task: no inbound listener"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-migrator" }
}

resource "aws_security_group" "data" {
  name        = "${var.name_prefix}-data"
  description = "Data tier (RDS in Story 6.2): 5432 from api and worker only"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-data" }
}

# Adopted with no rules so nothing can silently fall back to the VPC default SG.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-default-unused" }
}

locals {
  ingress_rules = {
    alb_https_from_cloudfront = {
      security_group_id = aws_security_group.alb.id
      port              = 443
      source_sg_id      = null
      prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
    }
    api_from_alb = {
      security_group_id = aws_security_group.api.id
      port              = 8000
      source_sg_id      = aws_security_group.alb.id
      prefix_list_id    = null
    }
    data_from_api = {
      security_group_id = aws_security_group.data.id
      port              = 5432
      source_sg_id      = aws_security_group.api.id
      prefix_list_id    = null
    }
    data_from_worker = {
      security_group_id = aws_security_group.data.id
      port              = 5432
      source_sg_id      = aws_security_group.worker.id
      prefix_list_id    = null
    }
    data_from_migrator = {
      security_group_id = aws_security_group.data.id
      port              = 5432
      source_sg_id      = aws_security_group.migrator.id
      prefix_list_id    = null
    }
  }

  egress_rules = {
    alb_to_api = {
      security_group_id = aws_security_group.alb.id
      port              = 8000
      dest_sg_id        = aws_security_group.api.id
      cidr              = null
    }
    api_https_out = {
      security_group_id = aws_security_group.api.id
      port              = 443
      dest_sg_id        = null
      cidr              = "0.0.0.0/0"
    }
    api_to_data = {
      security_group_id = aws_security_group.api.id
      port              = 5432
      dest_sg_id        = aws_security_group.data.id
      cidr              = null
    }
    worker_https_out = {
      security_group_id = aws_security_group.worker.id
      port              = 443
      dest_sg_id        = null
      cidr              = "0.0.0.0/0"
    }
    worker_to_data = {
      security_group_id = aws_security_group.worker.id
      port              = 5432
      dest_sg_id        = aws_security_group.data.id
      cidr              = null
    }
    migrator_https_out = {
      security_group_id = aws_security_group.migrator.id
      port              = 443
      dest_sg_id        = null
      cidr              = "0.0.0.0/0"
    }
    migrator_to_data = {
      security_group_id = aws_security_group.migrator.id
      port              = 5432
      dest_sg_id        = aws_security_group.data.id
      cidr              = null
    }
  }
}

resource "aws_vpc_security_group_ingress_rule" "this" {
  for_each = local.ingress_rules

  security_group_id            = each.value.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = each.value.source_sg_id
  prefix_list_id               = each.value.prefix_list_id
  description                  = each.key
}

resource "aws_vpc_security_group_egress_rule" "this" {
  for_each = local.egress_rules

  security_group_id            = each.value.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = each.value.dest_sg_id
  cidr_ipv4                    = each.value.cidr
  description                  = each.key
}
