output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (IGW route and NAT only), in availability_zones order."
  value       = [for az in var.availability_zones : aws_subnet.public[az].id]
}

output "app_subnet_ids" {
  description = "Private app subnet IDs (ALB, later API and worker tasks), in availability_zones order."
  value       = [for az in var.availability_zones : aws_subnet.app[az].id]
}

output "data_subnet_ids" {
  description = "Private data subnet IDs (no default route; RDS in Story 6.2), in availability_zones order."
  value       = [for az in var.availability_zones : aws_subnet.data[az].id]
}

output "alb_security_group_id" {
  description = "Security group of the internal ALB."
  value       = aws_security_group.alb.id
}

output "api_security_group_id" {
  description = "Security group of the API tasks."
  value       = aws_security_group.api.id
}

output "worker_security_group_id" {
  description = "Security group of the worker tasks (no ingress rule)."
  value       = aws_security_group.worker.id
}

output "data_security_group_id" {
  description = "Security group of the data tier."
  value       = aws_security_group.data.id
}

output "public_route_table_id" {
  description = "Route table of the public subnets."
  value       = aws_route_table.public.id
}

output "app_route_table_id" {
  description = "Route table of the private app subnets."
  value       = aws_route_table.app.id
}

output "data_route_table_id" {
  description = "Route table of the private data subnets (no default route)."
  value       = aws_route_table.data.id
}
