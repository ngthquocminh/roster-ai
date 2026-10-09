# One VPC, two AZs, three subnet tiers (Story 6.1 D5):
#   public  - internet gateway route and the single NAT gateway; nothing else.
#   app     - internal ALB now; API and worker tasks later; egress via NAT.
#   data    - NO default route; RDS arrives in Story 6.2.

locals {
  az_index = { for i, az in var.availability_zones : az => i }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name_prefix }
}

# CloudFront VPC origins require an internet gateway on the VPC (D2).
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = var.name_prefix }
}

resource "aws_subnet" "public" {
  for_each = local.az_index

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false

  tags = { Name = "${var.name_prefix}-public-${each.key}", Tier = "public" }
}

resource "aws_subnet" "app" {
  for_each = local.az_index

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 10 + each.value)
  map_public_ip_on_launch = false

  tags = { Name = "${var.name_prefix}-app-${each.key}", Tier = "app" }
}

resource "aws_subnet" "data" {
  for_each = local.az_index

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 20 + each.value)
  map_public_ip_on_launch = false

  tags = { Name = "${var.name_prefix}-data-${each.key}", Tier = "data" }
}

# A single NAT gateway: a deliberate single-AZ point of failure for Gate C
# (AD-24 scope note; recorded by Story 6.3's environment-limitations AC).
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = { Name = "${var.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[var.availability_zones[0]].id

  tags = { Name = var.name_prefix }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-public" }
}

resource "aws_route_table" "app" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-app" }
}

# Deliberately has no default route and no `route {}` block: RDS must not be
# able to reach, or be reached from, the internet.
resource "aws_route_table" "data" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "${var.name_prefix}-data" }
}

# Default routes live in standalone aws_route resources, keyed by tier, so a
# test can prove that none of them targets the data route table.
locals {
  default_routes = {
    public = { route_table_id = aws_route_table.public.id, gateway_id = aws_internet_gateway.this.id, nat_gateway_id = null }
    app    = { route_table_id = aws_route_table.app.id, gateway_id = null, nat_gateway_id = aws_nat_gateway.this.id }
  }
}

resource "aws_route" "default" {
  for_each = local.default_routes

  route_table_id         = each.value.route_table_id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = each.value.gateway_id
  nat_gateway_id         = each.value.nat_gateway_id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "app" {
  for_each = aws_subnet.app

  subnet_id      = each.value.id
  route_table_id = aws_route_table.app.id
}

resource "aws_route_table_association" "data" {
  for_each = aws_subnet.data

  subnet_id      = each.value.id
  route_table_id = aws_route_table.data.id
}

# Free, and keeps S3 traffic (ECR layers, later) off the NAT gateway.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.app.id, aws_route_table.data.id]

  tags = { Name = "${var.name_prefix}-s3" }
}
