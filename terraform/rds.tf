resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = aws_subnet.public[*].id

  tags = {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.project_name}-${var.environment}-postgres"

  engine = "postgres"
  # Major-version-only: AWS picks (and this stays pinned to) the latest
  # 16.x minor version rather than a minor version that goes stale.
  engine_version = "16"

  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.postgres.id]

  publicly_accessible = true  # so migrations can run from a local machine
  multi_az            = false # dev only, cost
  skip_final_snapshot = true  # dev only, avoids a snapshot on destroy

  tags = {
    Name = "${var.project_name}-${var.environment}-postgres"
  }
}
