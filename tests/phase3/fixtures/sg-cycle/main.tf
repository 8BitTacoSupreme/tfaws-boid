# Intentionally creates a cycle: SG-A references SG-B and vice versa
# via inline ingress blocks. This is the classic SG cycle anti-pattern
# that the Canon's sg-interactions.json documents.

resource "aws_vpc" "test" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "test-vpc"
  }
}

resource "aws_security_group" "a" {
  name        = "sg-a"
  description = "Security Group A - references SG B"
  vpc_id      = aws_vpc.test.id

  # This inline ingress creates a cycle with SG B
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.b.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-a"
  }
}

resource "aws_security_group" "b" {
  name        = "sg-b"
  description = "Security Group B - references SG A"
  vpc_id      = aws_vpc.test.id

  # This inline ingress creates the other half of the cycle
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.a.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-b"
  }
}
