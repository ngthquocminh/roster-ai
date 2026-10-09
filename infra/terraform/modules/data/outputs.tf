output "db_instance_identifier" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.identifier
}

output "db_address" {
  description = "RDS endpoint hostname (private)."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Application database name."
  value       = aws_db_instance.this.db_name
}

output "db_parameter_group_name" {
  description = "Custom postgres18 parameter group (rds.force_ssl = 1)."
  value       = aws_db_parameter_group.this.name
}

output "db_subnet_group_name" {
  description = "DB subnet group over the data subnets."
  value       = aws_db_subnet_group.this.name
}

output "database_url_secret_arn" {
  description = "Secret holding ROSTERAI_DATABASE_URL."
  value       = aws_secretsmanager_secret.database_url.arn
}

output "provisioning_database_url_secret_arn" {
  description = "Secret holding ROSTERAI_PROVISIONING_DATABASE_URL (migrate task only)."
  value       = aws_secretsmanager_secret.provisioning_database_url.arn
}

output "evidence_bucket_name" {
  description = "Create-only versioned evidence bucket."
  value       = aws_s3_bucket.evidence.bucket
}

output "evidence_bucket_arn" {
  description = "ARN of the evidence bucket."
  value       = aws_s3_bucket.evidence.arn
}


# For the env-root wiring tests (assertions reach a module only through its
# outputs).
output "db_subnet_ids" {
  description = "Subnets of the DB subnet group."
  value       = aws_db_subnet_group.this.subnet_ids
}

output "db_security_group_ids" {
  description = "Security groups of the RDS instance."
  value       = aws_db_instance.this.vpc_security_group_ids
}
