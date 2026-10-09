# The portfolio environment's composition (Story 6.1's env-root wiring plus
# Story 6.2's data, runtime and deploy identity).
#
# WHY A MODULE (Story 6.2, D6 as amended at implementation). The env root
# generates three passwords with ephemeral resources, and Terraform 1.15's
# `mock_provider` rejects any configuration that contains an ephemeral resource,
# even one behind `count = 0` or inside an overridden module. So the root keeps
# only providers, the ephemeral passwords and this call, and every offline test
# of the wiring targets this module directly, with the passwords supplied as
# ephemeral input variables.

locals {
  name_prefix        = "shiftmind-${var.environment}"
  secret_path_prefix = "shiftmind/${var.environment}"
  availability_zones = var.availability_zones != null ? var.availability_zones : ["${var.region}a", "${var.region}b"]
}

# The hosted zone is looked up, not created (6.1 D3): registering a domain is a
# billing act, not reproducible infrastructure. Passing zone_id into the modules
# keeps them testable without this data source.
data "aws_route53_zone" "this" {
  name         = var.hosted_zone_name
  private_zone = false
}

module "network" {
  source = "../network"

  name_prefix        = local.name_prefix
  region             = var.region
  vpc_cidr           = var.vpc_cidr
  availability_zones = local.availability_zones
}

module "edge" {
  source = "../edge"

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
  source = "../identity"

  name_prefix           = local.name_prefix
  region                = var.region
  app_domain            = var.app_domain
  cognito_domain_prefix = var.cognito_domain_prefix
  planner_email         = var.planner_email
}

module "data" {
  source = "../data"

  name_prefix            = local.name_prefix
  secret_path_prefix     = local.secret_path_prefix
  data_subnet_ids        = module.network.data_subnet_ids
  data_security_group_id = module.network.data_security_group_id
  db_instance_class      = var.db_instance_class
  force_ssl_apply_method = var.force_ssl_apply_method
  migrator_password      = var.migrator_password
  login_password         = var.login_password
  db_credentials_version = var.db_credentials_version
}

module "runtime" {
  source = "../runtime"

  name_prefix                          = local.name_prefix
  environment                          = var.environment
  region                               = var.region
  secret_path_prefix                   = local.secret_path_prefix
  database_url_secret_arn              = module.data.database_url_secret_arn
  provisioning_database_url_secret_arn = module.data.provisioning_database_url_secret_arn
  oidc_client_secret                   = module.identity.oidc_client_secret
  csrf_secret                          = var.csrf_secret
  credentials_version                  = var.db_credentials_version
  backend_image_digest                 = var.backend_image_digest
  planner_subject                      = module.identity.planner_subject
  planner_email                        = var.planner_email
}

module "github_oidc" {
  source = "../github_oidc"

  name_prefix              = local.name_prefix
  github_repository        = var.github_repository
  github_environment       = var.github_environment
  github_oidc_provider_arn = var.github_oidc_provider_arn
  backend_repository_arn   = module.runtime.backend_repository_arn
}
