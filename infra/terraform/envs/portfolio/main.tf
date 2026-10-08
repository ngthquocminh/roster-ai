locals {
  name_prefix        = "shiftmind-${var.environment}"
  availability_zones = var.availability_zones != null ? var.availability_zones : ["${var.region}a", "${var.region}b"]

  default_tags = {
    Project     = "shiftmind"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# The hosted zone is looked up, not created (D3): registering a domain is a
# billing act, not reproducible infrastructure. Passing zone_id into the modules
# keeps them testable without this data source.
data "aws_route53_zone" "this" {
  name         = var.hosted_zone_name
  private_zone = false
}

module "network" {
  source = "../../modules/network"

  name_prefix        = local.name_prefix
  region             = var.region
  vpc_cidr           = var.vpc_cidr
  availability_zones = local.availability_zones
}

module "edge" {
  source = "../../modules/edge"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix           = local.name_prefix
  app_domain            = var.app_domain
  zone_id               = data.aws_route53_zone.this.zone_id
  vpc_id                = module.network.vpc_id
  app_subnet_ids        = module.network.app_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
}

module "identity" {
  source = "../../modules/identity"

  name_prefix           = local.name_prefix
  region                = var.region
  app_domain            = var.app_domain
  cognito_domain_prefix = var.cognito_domain_prefix
  planner_email         = var.planner_email
}
