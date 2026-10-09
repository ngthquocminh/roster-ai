# Modules never configure providers; only the roots have `provider` blocks.
# CloudFront requires its ACM certificate in us-east-1, hence the alias.
terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 6.67"
      configuration_aliases = [aws.us_east_1]
    }
  }
}
