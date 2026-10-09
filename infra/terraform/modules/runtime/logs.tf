# CloudWatch log groups (Story 6.2 D11). 30-day retention (AD-17); CloudWatch
# Logs encrypts at rest by default, so no CMK is added.

locals {
  log_services = toset(["api", "worker", "migrate"])
}

resource "aws_cloudwatch_log_group" "this" {
  for_each = local.log_services

  name              = "/shiftmind/${var.environment}/${each.key}"
  retention_in_days = 30
}
