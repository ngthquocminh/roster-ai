# The two database URL secrets (Story 6.2 D6). Values are write-only: built
# from ephemeral passwords at apply time and never stored in state. Both carry
# sslmode=require (D5); server-certificate verification is a ledger item.
#
# replace_triggered_by: a replaced instance has a new endpoint, so the URL
# versions are rewritten even when db_credentials_version did not move.

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${var.secret_path_prefix}/database-url"
  description             = "ROSTERAI_DATABASE_URL: shiftmind_login (API and worker)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id                = aws_secretsmanager_secret.database_url.id
  secret_string_wo         = "postgresql+psycopg://shiftmind_login:${var.login_password}@${aws_db_instance.this.address}:${local.db_port}/${local.db_name}?sslmode=require"
  secret_string_wo_version = var.db_credentials_version

  lifecycle {
    replace_triggered_by = [aws_db_instance.this.id]
  }
}

resource "aws_secretsmanager_secret" "provisioning_database_url" {
  name                    = "${var.secret_path_prefix}/provisioning-database-url"
  description             = "ROSTERAI_PROVISIONING_DATABASE_URL: the RDS master (migrate task only)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "provisioning_database_url" {
  secret_id                = aws_secretsmanager_secret.provisioning_database_url.id
  secret_string_wo         = "postgresql+psycopg://${local.migrator_user}:${var.migrator_password}@${aws_db_instance.this.address}:${local.db_port}/${local.db_name}?sslmode=require"
  secret_string_wo_version = var.db_credentials_version

  lifecycle {
    replace_triggered_by = [aws_db_instance.this.id]
  }
}
