# Partial S3 backend (Story 6.1 D7). Bucket, key and region come from the
# gitignored backend.hcl:
#
#   terraform init -backend-config=backend.hcl
#
# `use_lockfile` is S3 native locking (Terraform >= 1.10); there is no DynamoDB
# lock table. State holds the Cognito client secret, hence `encrypt`.
terraform {
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
