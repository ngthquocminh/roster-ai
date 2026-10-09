variable "name_prefix" {
  description = "Prefix for resource names, e.g. shiftmind-portfolio."
  type        = string
}

variable "app_domain" {
  description = "Public hostname of the app, e.g. shiftmind.example.com. Must sit inside the hosted zone."
  type        = string
}

variable "zone_id" {
  description = "ID of the existing public Route 53 hosted zone that contains app_domain (looked up by the env root)."
  type        = string
}

variable "vpc_id" {
  description = "VPC that holds the internal ALB."
  type        = string
}

variable "app_subnet_ids" {
  description = "Private app subnets for the internal ALB (two AZs)."
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group of the ALB (inbound 443 from the CloudFront prefix list only)."
  type        = string
}

variable "api_port" {
  description = "Port the API listens on (Dockerfile CMD, docker-compose healthcheck)."
  type        = number
  default     = 8000
}
