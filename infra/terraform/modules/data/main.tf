# RDS PostgreSQL (Story 6.2 D5). Private, encrypted, TLS-only, and moved only
# by a reviewed plan: no automatic minor or major version upgrade.

locals {
  db_name       = "rosterai"
  db_port       = 5432
  migrator_user = "shiftmind_migrator"
}

resource "aws_db_subnet_group" "this" {
  name        = "${var.name_prefix}-data"
  description = "Private data subnets only"
  subnet_ids  = var.data_subnet_ids
}

resource "aws_db_parameter_group" "this" {
  name        = "${var.name_prefix}-postgres18"
  family      = "postgres18"
  description = "TLS-only connections"

  # No statement logging is configured here on purpose: the hosted bootstrap
  # sends the login password in an ALTER ROLE statement.
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = var.force_ssl_apply_method
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = "18.4"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 0 # no storage autoscaling
  storage_type          = "gp3"
  storage_encrypted     = true # AWS-managed key

  db_name  = local.db_name
  port     = local.db_port
  username = local.migrator_user
  # Write-only (D6): sent to AWS when the version changes, never stored.
  password_wo         = var.migrator_password
  password_wo_version = var.db_credentials_version

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.data_security_group_id]
  publicly_accessible    = false
  multi_az               = false
  parameter_group_name   = aws_db_parameter_group.this.name

  auto_minor_version_upgrade  = false
  allow_major_version_upgrade = false

  # AD-17's values on the instance this story creates; 6.5 proves them.
  backup_retention_period   = 7
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-db-final"
  deletion_protection       = false
  copy_tags_to_snapshot     = true
  apply_immediately         = true

  # D10's not-added list.
  iam_database_authentication_enabled = false
  performance_insights_enabled        = false
  monitoring_interval                 = 0
  enabled_cloudwatch_logs_exports     = []
}
