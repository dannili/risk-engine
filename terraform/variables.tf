variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name, used for resource naming and tagging"
  type        = string
  default     = "risk-engine"
}

variable "environment" {
  description = "Deployment environment (e.g. dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "db_name" {
  description = "Name of the default database created on the RDS instance"
  type        = string
  default     = "riskengine"
}

variable "db_username" {
  description = "Master username for the RDS instance"
  type        = string
  default     = "riskadmin"
}

variable "db_password" {
  description = "Master password for the RDS instance"
  type        = string
  sensitive   = true
}
