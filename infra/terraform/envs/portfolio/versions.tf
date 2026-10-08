# Terraform seed version is 1.15.8 (ARCHITECTURE-SPINE "Stack"); developed and
# validated on the newest 1.15.x (recorded in Story 6.1's Completion Notes).
terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }
}
