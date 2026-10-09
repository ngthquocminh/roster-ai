# Modules have no `provider` blocks; they receive these. (The separate bootstrap
# root configures its own.)
provider "aws" {
  region = var.region

  default_tags {
    tags = local.default_tags
  }
}

# CloudFront reads its ACM certificate from us-east-1 only (Story 6.1 D3).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.default_tags
  }
}
