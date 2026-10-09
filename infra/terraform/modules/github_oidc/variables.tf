variable "name_prefix" {
  description = "Prefix for resource names, e.g. shiftmind-portfolio."
  type        = string
}

variable "github_repository" {
  description = "owner/name of the GitHub repository allowed to assume the deploy role."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository is owner/name, with no wildcard."
  }
}

variable "github_environment" {
  description = "GitHub environment whose jobs may assume the deploy role (the token's sub is repo:<repo>:environment:<env>)."
  type        = string
  default     = "portfolio"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+$", var.github_environment))
    error_message = "github_environment is a plain environment name, with no wildcard."
  }
}

variable "github_oidc_provider_arn" {
  description = "ARN of an EXISTING token.actions.githubusercontent.com provider in the account. Null creates one; set, it is looked up and never managed, so a teardown cannot delete a provider another project uses."
  type        = string
  default     = null
}

variable "backend_repository_arn" {
  description = "ARN of the backend ECR repository, the only repository the deploy role may push to."
  type        = string
}
