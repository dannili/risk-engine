resource "aws_ecr_repository" "app" {
  name                 = "risk-engine"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  tags = {
    Name = "risk-engine"
  }
}
