variable "name_prefix" {
  description = "Prefix for resource names, e.g. shiftmind-portfolio."
  type        = string
}

variable "region" {
  description = "AWS region, used to build the S3 gateway endpoint service name."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR of the VPC. Subnets are carved from it with cidrsubnet(…, 8, n), so it must be a /16."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && endswith(var.vpc_cidr, "/16")
    error_message = "vpc_cidr must be a valid IPv4 /16 CIDR."
  }
}

variable "availability_zones" {
  description = "Exactly two AZs. Passed in rather than looked up so tests are deterministic and the operator can avoid an AZ that CloudFront VPC origins do not support."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "availability_zones must list exactly two AZs (RDS subnet groups need two; Gate C is not multi-AZ beyond that)."
  }
}
