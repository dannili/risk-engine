output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "web_security_group_id" {
  description = "ID of the web security group (inbound 8000 from anywhere)"
  value       = aws_security_group.web.id
}

output "postgres_security_group_id" {
  description = "ID of the postgres security group (inbound 5432 from web only)"
  value       = aws_security_group.postgres.id
}

output "redis_security_group_id" {
  description = "ID of the redis security group (inbound 6379 from web only)"
  value       = aws_security_group.redis.id
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint address (host only, no port)"
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  description = "RDS Postgres port"
  value       = aws_db_instance.postgres.port
}
