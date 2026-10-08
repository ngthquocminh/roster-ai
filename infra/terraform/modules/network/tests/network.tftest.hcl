# Offline proof of the network boundary (Story 6.1 D5, AC2 second clause).
# Mock provider, no credentials. `command = apply` is deliberate: against a mock
# it never contacts AWS, and it is the only mode in which computed IDs are
# generated, which the SG-to-SG comparisons below need.
mock_provider "aws" {}

override_data {
  target = data.aws_ec2_managed_prefix_list.cloudfront
  values = {
    id = "pl-cloudfront-origin-facing"
  }
}

variables {
  name_prefix        = "shiftmind-test"
  region             = "ap-southeast-1"
  availability_zones = ["ap-southeast-1a", "ap-southeast-1b"]
}

run "data_tier_has_no_internet_route" {
  command = apply

  assert {
    condition = alltrue([
      for r in values(aws_route.default) : r.route_table_id != aws_route_table.data.id
    ])
    error_message = "No default route may target the data route table."
  }

  assert {
    condition     = length(aws_route_table.data.route) == 0
    error_message = "The data route table must carry no inline routes."
  }

  assert {
    condition     = alltrue([for a in values(aws_route_table_association.data) : a.route_table_id == aws_route_table.data.id])
    error_message = "Every data subnet must be associated with the data route table."
  }

  assert {
    condition     = alltrue([for a in values(aws_route_table_association.app) : a.route_table_id == aws_route_table.app.id])
    error_message = "Every app subnet must be associated with the app route table, not the public one."
  }

  assert {
    condition     = aws_route.default["app"].nat_gateway_id != null && aws_route.default["app"].gateway_id == null
    error_message = "The app tier must reach the internet through the NAT gateway, not the IGW."
  }
}

run "no_subnet_assigns_public_ips" {
  command = apply

  assert {
    condition = alltrue([
      for s in concat(values(aws_subnet.public), values(aws_subnet.app), values(aws_subnet.data)) : !s.map_public_ip_on_launch
    ])
    error_message = "No subnet may set map_public_ip_on_launch."
  }

  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.app) == 2 && length(aws_subnet.data) == 2
    error_message = "Each tier must span exactly two AZs."
  }
}

run "s3_gateway_endpoint_is_on_app_and_data_tables" {
  command = apply

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway" && aws_vpc_endpoint.s3.service_name == "com.amazonaws.ap-southeast-1.s3"
    error_message = "The S3 endpoint must be a Gateway endpoint for the region."
  }

  assert {
    condition     = toset(aws_vpc_endpoint.s3.route_table_ids) == toset([aws_route_table.app.id, aws_route_table.data.id])
    error_message = "The S3 endpoint must attach to the app and data route tables only."
  }
}

run "worker_has_no_ingress_rule" {
  command = apply

  assert {
    condition = length([
      for r in values(aws_vpc_security_group_ingress_rule.this) : r if r.security_group_id == aws_security_group.worker.id
    ]) == 0
    error_message = "The worker security group must have no ingress rule at all."
  }
}

run "api_ingress_comes_only_from_the_alb" {
  command = apply

  assert {
    condition = length([
      for r in values(aws_vpc_security_group_ingress_rule.this) : r if r.security_group_id == aws_security_group.api.id
    ]) == 1
    error_message = "The api security group must have exactly one ingress rule."
  }

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_ingress_rule.this) :
      r.referenced_security_group_id == aws_security_group.alb.id && r.from_port == 8000 && r.to_port == 8000
      if r.security_group_id == aws_security_group.api.id
    ])
    error_message = "The api ingress rule must be port 8000 from the ALB security group only."
  }
}

run "alb_ingress_is_only_443_from_the_cloudfront_prefix_list" {
  command = apply

  assert {
    condition = length([
      for r in values(aws_vpc_security_group_ingress_rule.this) : r if r.security_group_id == aws_security_group.alb.id
    ]) == 1
    error_message = "The ALB security group must have exactly one ingress rule (the prefix list counts as ~55 rules against the quota)."
  }

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_ingress_rule.this) :
      r.prefix_list_id == "pl-cloudfront-origin-facing" && r.from_port == 443 && r.to_port == 443 && r.cidr_ipv4 == null && r.referenced_security_group_id == null
      if r.security_group_id == aws_security_group.alb.id
    ])
    error_message = "The ALB ingress rule must be 443 from the CloudFront origin-facing prefix list, not a CIDR or another security group."
  }

  assert {
    condition     = data.aws_ec2_managed_prefix_list.cloudfront.name == "com.amazonaws.global.cloudfront.origin-facing"
    error_message = "The prefix list must be the AWS-managed CloudFront origin-facing list."
  }
}

run "data_ingress_is_only_5432_from_api_and_worker" {
  command = apply

  assert {
    condition = toset([
      for r in values(aws_vpc_security_group_ingress_rule.this) : r.referenced_security_group_id
      if r.security_group_id == aws_security_group.data.id
    ]) == toset([aws_security_group.api.id, aws_security_group.worker.id])
    error_message = "The data security group must accept traffic from the api and worker security groups only."
  }

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_ingress_rule.this) : r.from_port == 5432 && r.to_port == 5432
      if r.security_group_id == aws_security_group.data.id
    ])
    error_message = "The data security group must accept port 5432 only."
  }
}

run "data_has_no_egress_and_default_sg_has_no_rules" {
  command = apply

  assert {
    condition = length([
      for r in values(aws_vpc_security_group_egress_rule.this) : r if r.security_group_id == aws_security_group.data.id
    ]) == 0
    error_message = "The data security group must have no egress rule."
  }

  assert {
    condition     = length(aws_default_security_group.this.ingress) == 0 && length(aws_default_security_group.this.egress) == 0
    error_message = "The adopted default security group must carry no rules."
  }
}

run "workloads_egress_only_443_and_5432" {
  command = apply

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_egress_rule.this) : contains([443, 5432, 8000], r.from_port) && r.from_port == r.to_port
      if r.security_group_id != aws_security_group.data.id
    ])
    error_message = "Egress is limited to 443, 5432 (to data) and 8000 (ALB to api)."
  }

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_egress_rule.this) : r.referenced_security_group_id == aws_security_group.data.id
      if r.from_port == 5432
    ])
    error_message = "Port 5432 egress must target the data security group only."
  }

  assert {
    condition = alltrue([
      for r in values(aws_vpc_security_group_egress_rule.this) : r.referenced_security_group_id == aws_security_group.api.id
      if r.security_group_id == aws_security_group.alb.id
    ])
    error_message = "The ALB may send traffic to the api security group only."
  }
}

run "az_count_is_validated" {
  command = plan

  variables {
    availability_zones = ["ap-southeast-1a"]
  }

  expect_failures = [var.availability_zones]
}
