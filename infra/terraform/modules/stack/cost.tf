# Budget and cost allocation tags (Story 6.2 D11).
#
# The budget is account-wide on purpose. A tag-filtered budget is blind to
# untagged spend and reads $0 until the tags are activated: a guard that
# cannot go red. Other workloads in the same account count against it, which
# is accepted for a practice account (docs/AWS-RUNBOOK.md).

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}

# The keys the root's default_tags put on every resource. Billing must have
# seen a key (about 24 h after first use) before it can be activated.
resource "aws_ce_cost_allocation_tag" "this" {
  for_each = toset(["Project", "Environment"])
  provider = aws.us_east_1

  tag_key = each.key
  status  = "Active"
}
