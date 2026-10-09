# Offline proof of the data tier's configuration intent (Story 6.2 D5-D7).
# Mock provider, no credentials; `command = apply` so computed IDs and ARNs
# exist for the comparisons below. That AWS accepted it is proved by the
# operator-run apply and infra/scripts/smoke-data.sh.
#
# Write-only values are never visible to an assertion. These runs assert the
# *_wo_version attributes and the ABSENCE of the plain attributes instead.
# replace_triggered_by is a lifecycle argument, not a value, so it is asserted
# by backend/tests/architecture/test_infra_source_guards.py from the source, as
# is the absence of an evidence lifecycle rule (a resource that must not exist).
mock_provider "aws" {}

variables {
  name_prefix            = "shiftmind-test"
  secret_path_prefix     = "shiftmind/test"
  data_subnet_ids        = ["subnet-data-a", "subnet-data-b"]
  data_security_group_id = "sg-data"
  db_instance_class      = "db.t4g.micro"
  migrator_password      = "MigratorLiteral0123456789"
  login_password         = "LoginLiteral0123456789"
  db_credentials_version = 1
}

run "rds_is_private_encrypted_and_pinned" {
  command = apply

  assert {
    condition     = aws_db_instance.this.publicly_accessible == false && aws_db_instance.this.storage_encrypted == true
    error_message = "RDS must be non-public and encrypted at rest."
  }

  assert {
    condition     = aws_db_instance.this.multi_az == false
    error_message = "Multi-AZ is deferred (spine \"Deferred\")."
  }

  assert {
    condition     = aws_db_instance.this.engine == "postgres" && aws_db_instance.this.engine_version == "18.4"
    error_message = "The engine must be PostgreSQL 18.4, the spine's seed."
  }

  assert {
    condition     = aws_db_instance.this.auto_minor_version_upgrade == false && aws_db_instance.this.allow_major_version_upgrade == false
    error_message = "A version may move only through a reviewed plan."
  }

  assert {
    condition     = aws_db_instance.this.storage_type == "gp3" && aws_db_instance.this.allocated_storage == 20 && aws_db_instance.this.max_allocated_storage == 0
    error_message = "Storage is 20 GB gp3 with no autoscaling."
  }

  assert {
    condition     = aws_db_instance.this.iam_database_authentication_enabled == false && aws_db_instance.this.performance_insights_enabled == false && aws_db_instance.this.monitoring_interval == 0 && length(aws_db_instance.this.enabled_cloudwatch_logs_exports) == 0
    error_message = "IAM auth, Performance Insights, Enhanced Monitoring and log exports are on D10's not-added list."
  }
}

run "rds_backups_and_teardown_values" {
  command = apply

  assert {
    condition     = aws_db_instance.this.backup_retention_period == 7
    error_message = "Backups are retained for 7 days (AD-17)."
  }

  assert {
    condition     = aws_db_instance.this.skip_final_snapshot == false && aws_db_instance.this.final_snapshot_identifier == "shiftmind-test-db-final"
    error_message = "A destroy must take a named final snapshot."
  }

  assert {
    condition     = aws_db_instance.this.deletion_protection == false && aws_db_instance.this.copy_tags_to_snapshot == true
    error_message = "Teardown must work (no deletion protection) and snapshots carry the cost tags."
  }
}

run "rds_sits_only_in_the_data_tier" {
  command = apply

  assert {
    condition     = toset(aws_db_subnet_group.this.subnet_ids) == toset(["subnet-data-a", "subnet-data-b"]) && length(aws_db_subnet_group.this.subnet_ids) == 2
    error_message = "The DB subnet group must be exactly the input data subnets."
  }

  assert {
    condition     = aws_db_instance.this.db_subnet_group_name == aws_db_subnet_group.this.name
    error_message = "The instance must use the data subnet group."
  }

  assert {
    condition     = length(aws_db_instance.this.vpc_security_group_ids) == 1 && toset(aws_db_instance.this.vpc_security_group_ids) == toset(["sg-data"])
    error_message = "The instance's only security group must be the data security group."
  }
}

run "rds_requires_tls" {
  command = apply

  assert {
    condition     = aws_db_instance.this.parameter_group_name == aws_db_parameter_group.this.name && aws_db_parameter_group.this.family == "postgres18"
    error_message = "The instance must use the custom postgres18 parameter group."
  }

  assert {
    condition = length([
      for p in aws_db_parameter_group.this.parameter : p if p.name == "rds.force_ssl" && p.value == "1"
    ]) == 1
    error_message = "The parameter group must set rds.force_ssl = 1."
  }

  assert {
    condition     = length([for p in aws_db_parameter_group.this.parameter : p if p.name == "log_statement"]) == 0
    error_message = "No statement logging: the hosted bootstrap sends a password in DDL."
  }
}

run "credentials_are_write_only" {
  command = apply

  assert {
    condition     = aws_db_instance.this.password == null && aws_db_instance.this.password_wo_version == 1
    error_message = "The master password must be write-only (password_wo), never the stored password argument."
  }

  assert {
    condition = alltrue([
      for v in [aws_secretsmanager_secret_version.database_url, aws_secretsmanager_secret_version.provisioning_database_url] :
      v.secret_string == null && v.secret_binary == null && v.secret_string_wo_version == 1
    ])
    error_message = "Both URL secrets must be written only through secret_string_wo."
  }

  assert {
    condition     = aws_db_instance.this.username == "shiftmind_migrator" && aws_db_instance.this.db_name == "rosterai"
    error_message = "The master user is shiftmind_migrator and the database is rosterai."
  }
}

# kms_key_id and policy are Computed, so a mock fills them with random strings;
# smoke-data.sh check 9 proves "no resource policy" on the live secrets.
run "secrets_are_named_and_immediately_deletable" {
  command = apply

  assert {
    condition = [aws_secretsmanager_secret.database_url.name, aws_secretsmanager_secret.provisioning_database_url.name] == [
      "shiftmind/test/database-url", "shiftmind/test/provisioning-database-url"
    ]
    error_message = "Secret names follow shiftmind/<env>/<name>."
  }

  assert {
    condition = alltrue([
      for s in [aws_secretsmanager_secret.database_url, aws_secretsmanager_secret.provisioning_database_url] :
      s.recovery_window_in_days == 0
    ])
    error_message = "Secrets have no recovery window, so a teardown then re-apply does not collide."
  }
}

run "evidence_bucket_is_private_encrypted_and_versioned" {
  command = apply

  assert {
    condition = (
      aws_s3_bucket_public_access_block.evidence.block_public_acls &&
      aws_s3_bucket_public_access_block.evidence.block_public_policy &&
      aws_s3_bucket_public_access_block.evidence.ignore_public_acls &&
      aws_s3_bucket_public_access_block.evidence.restrict_public_buckets
    )
    error_message = "All four Block Public Access flags must be on."
  }

  assert {
    condition     = one(aws_s3_bucket_ownership_controls.evidence.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled (BucketOwnerEnforced)."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.evidence.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The bucket must use SSE-S3."
  }

  assert {
    condition     = one(aws_s3_bucket_versioning.evidence.versioning_configuration).status == "Enabled"
    error_message = "Versioning must be Enabled."
  }

  assert {
    condition     = startswith(aws_s3_bucket.evidence.bucket, "shiftmind-test-evidence-") && aws_s3_bucket.evidence.force_destroy == true
    error_message = "The bucket is <prefix>-evidence-<account> and teardown can empty it."
  }
}

# The whole policy, not a subset: narrowing an action, a resource or a
# condition must redden this run (the Story 6.1 review finding).
run "evidence_policy_is_exactly_the_three_denies" {
  command = apply

  assert {
    condition = jsondecode(aws_s3_bucket_policy.evidence.policy) == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid       = "DenyInsecureTransport"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource  = [aws_s3_bucket.evidence.arn, "${aws_s3_bucket.evidence.arn}/*"]
          Condition = { Bool = { "aws:SecureTransport" = "false" } }
        },
        {
          Sid       = "DenyOverwrite"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:PutObject"
          Resource  = "${aws_s3_bucket.evidence.arn}/*"
          Condition = {
            Null = { "s3:if-none-match" = "true" }
            Bool = { "s3:ObjectCreationOperation" = "true" }
          }
        },
        {
          Sid       = "DenyDelete"
          Effect    = "Deny"
          Principal = "*"
          Action    = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
          Resource  = "${aws_s3_bucket.evidence.arn}/*"
        },
      ]
    }
    error_message = "The evidence policy must be exactly D7's three Deny statements."
  }

  assert {
    condition     = aws_s3_bucket_policy.evidence.bucket == aws_s3_bucket.evidence.id
    error_message = "The policy must attach to the evidence bucket."
  }
}

run "subnet_count_is_validated" {
  command = plan

  variables {
    data_subnet_ids = ["subnet-data-a"]
  }

  expect_failures = [var.data_subnet_ids]
}
