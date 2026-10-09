# Modules never configure providers; only the roots have `provider` blocks.
# The edge module needs the us-east-1 alias (CloudFront certificates), and so
# does Cost Explorer (cost allocation tags).
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
