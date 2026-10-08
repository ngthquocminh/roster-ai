variable "name_prefix" {
  description = "Prefix for resource names, e.g. shiftmind-portfolio."
  type        = string
}

variable "region" {
  description = "AWS region of the user pool; part of the OIDC issuer URL."
  type        = string
}

variable "app_domain" {
  description = "Public hostname of the app. The BFF callback is https://<app_domain>/api/v1/auth/callback."
  type        = string
}

variable "cognito_domain_prefix" {
  description = "Prefix of the Cognito hosted-login domain (<prefix>.auth.<region>.amazoncognito.com). Globally unique per region."
  type        = string
}

variable "planner_email" {
  description = "Email of the one planner user. Cognito mails the temporary password to it; no password exists in code, tfvars or state."
  type        = string
}
