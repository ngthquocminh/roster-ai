# Offline proof of the state bucket's protections: mock provider, no credentials.
mock_provider "aws" {}

variables {
  state_bucket_name = "shiftmind-tfstate-test"
}

run "state_bucket_is_private_versioned_and_encrypted" {
  command = apply

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "All four Block Public Access flags must be on."
  }

  assert {
    condition     = one(aws_s3_bucket_ownership_controls.state.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled with BucketOwnerEnforced."
  }

  assert {
    condition     = one(aws_s3_bucket_versioning.state.versioning_configuration).status == "Enabled"
    error_message = "State bucket versioning must be enabled."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "State bucket must be encrypted at rest."
  }
}

run "state_bucket_policy_denies_plaintext_transport" {
  command = apply

  assert {
    condition = anytrue([
      for st in jsondecode(aws_s3_bucket_policy.state.policy).Statement :
      st.Effect == "Deny" && st.Condition.Bool["aws:SecureTransport"] == "false"
    ])
    error_message = "The state bucket policy must Deny when aws:SecureTransport is false."
  }

  # The Deny must cover every principal, every action, and both the bucket and its
  # objects: a Deny narrowed to one action or to the bucket ARN alone would still
  # carry the condition and pass the assertion above.
  assert {
    condition = alltrue([
      for st in jsondecode(aws_s3_bucket_policy.state.policy).Statement :
      st.Principal == "*" && st.Action == "s3:*" &&
      toset(flatten([st.Resource])) == toset([aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"])
      if st.Effect == "Deny"
    ])
    error_message = "The plaintext Deny must be Principal *, Action s3:*, on the bucket and every object."
  }
}

run "bucket_name_validation_rejects_uppercase" {
  command = plan

  variables {
    state_bucket_name = "Bad_Name"
  }

  expect_failures = [var.state_bucket_name]
}
