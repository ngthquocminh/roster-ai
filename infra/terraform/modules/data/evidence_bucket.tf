# Create-only, versioned evidence bucket (Story 6.2 D7).
#
# The three Denies name Principal "*", so they bind every principal, the
# operator's administrator role included: an explicit Deny beats any Allow.
# No application role is granted any S3 action today (no backend code calls
# AWS); the first story that writes evidence grants its writer PutObject and
# GetObject, and the create-only rule already holds for it.
#
# Not regulatory WORM: an account administrator can remove this policy. That is
# how an object is deliberately removed (docs/AWS-RUNBOOK.md).

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "evidence" {
  bucket = "${var.name_prefix}-evidence-${data.aws_caller_identity.current.account_id}"

  # Teardown must still work: destroy removes the policy (it depends on the
  # bucket), then force_destroy empties every version.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# No lifecycle rule: evidence persists until teardown (AD-17).
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  versioning_configuration {
    status = "Enabled"
  }
}

locals {
  evidence_policy_statements = [
    {
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.evidence.arn, "${aws_s3_bucket.evidence.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    },
    {
      # AWS S3 User Guide, "Enforce conditional writes", Example 2's shape with
      # if-none-match: a PutObject or CompleteMultipartUpload without the
      # header is denied, while CreateMultipartUpload and UploadPart (not
      # object-creation operations) still work. CopyObject into the bucket
      # cannot carry the header, so it is impossible by design.
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

resource "aws_s3_bucket_policy" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.evidence_policy_statements
  })

  depends_on = [aws_s3_bucket_public_access_block.evidence]
}
