variable "region" {
  description = "AWS region of everything except the CloudFront certificate. ap-southeast-1 is closest to the site's Asia/Ho_Chi_Minh timezone and supports CloudFront VPC origins."
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Environment name; part of every resource name (shiftmind-<environment>) and the Environment tag."
  type        = string
  default     = "portfolio"
}

variable "availability_zones" {
  description = "Exactly two AZs. Null means the first two AZs of the region (<region>a, <region>b); set it to avoid an AZ that CloudFront VPC origins do not support."
  type        = list(string)
  default     = null
}

variable "vpc_cidr" {
  description = "CIDR of the VPC; must be a /16."
  type        = string
  default     = "10.20.0.0/16"
}

variable "hosted_zone_name" {
  description = "Name of an EXISTING public Route 53 hosted zone, e.g. example.com. Registering the domain and creating the zone are prerequisites (docs/AWS-RUNBOOK.md), not Terraform resources."
  type        = string
}

variable "app_domain" {
  description = "Public hostname of the app inside the hosted zone, e.g. shiftmind.example.com."
  type        = string

  validation {
    condition     = can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", var.app_domain))
    error_message = "app_domain must be a lowercase DNS name such as shiftmind.example.com."
  }
}

variable "cognito_domain_prefix" {
  description = "Prefix of the Cognito hosted-login domain; globally unique per region."
  type        = string
}

variable "planner_email" {
  description = "Email of the one planner user. Cognito mails the temporary password here."
  type        = string
}
