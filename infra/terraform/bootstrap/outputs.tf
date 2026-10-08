output "state_bucket_name" {
  description = "Name of the state bucket. Put it in envs/portfolio/backend.hcl."
  value       = aws_s3_bucket.state.id
}

output "region" {
  description = "Region of the state bucket. Put it in envs/portfolio/backend.hcl."
  value       = var.region
}
