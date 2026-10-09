variable "region" {
  description = "AWS region for the state bucket. Keep it equal to the env root's region."
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Environment name, used in tags only."
  type        = string
  default     = "portfolio"
}

variable "state_bucket_name" {
  description = "Globally unique name of the Terraform state bucket, e.g. shiftmind-tfstate-<account-id>."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "state_bucket_name must be a valid S3 bucket name (3-63 chars, lowercase letters, digits, dots, hyphens)."
  }
}
