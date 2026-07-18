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

output "redis_endpoint" {
  description = "ElastiCache Redis node address (host only, no port)"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "redis_port" {
  description = "ElastiCache Redis port"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].port
}

output "db_password_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the RDS master password (for the ECS task definition)"
  value       = aws_secretsmanager_secret.db_password.arn
}

output "ecr_repository_url" {
  description = "URL of the risk-engine ECR repository (for docker push / task definition image)"
  value       = aws_ecr_repository.app.repository_url
}
