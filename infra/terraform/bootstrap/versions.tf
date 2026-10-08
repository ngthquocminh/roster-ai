# Bootstrap root: creates the one S3 bucket that holds the Terraform state of
# envs/portfolio. It uses LOCAL state (gitignored) because it is the thing that
# makes remote state possible; if that local state is lost the bucket is
# re-adopted with `terraform import` (docs/AWS-RUNBOOK.md).
terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }
}
