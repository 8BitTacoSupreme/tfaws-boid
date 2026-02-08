# VPC Demo: 3-AZ VPC with public/private subnets and NAT gateways
#
# Intentional pitfall: uses inline ingress/egress rules on security groups,
# which triggers the Canon's SG cycle and inline-vs-standalone patterns.

variable "project" {
  default = "boid-demo"
}

variable "azs" {
  default = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# --- VPC ---

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project}-igw"
  }
}

# --- Public Subnets ---

resource "aws_subnet" "public" {
  count = 3

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet("10.0.0.0/16", 8, count.index)
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project}-public-${var.azs[count.index]}"
    Tier = "public"
  }
}

# --- Private Subnets ---

resource "aws_subnet" "private" {
  count = 3

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index + 100)
  availability_zone = var.azs[count.index]

  tags = {
    Name = "${var.project}-private-${var.azs[count.index]}"
    Tier = "private"
  }
}

# --- NAT Gateways (one per AZ) ---

resource "aws_eip" "nat" {
  count  = 3
  domain = "vpc"

  tags = {
    Name = "${var.project}-nat-eip-${var.azs[count.index]}"
  }
}

resource "aws_nat_gateway" "main" {
  count = 3

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "${var.project}-nat-${var.azs[count.index]}"
  }
}

# --- Security Groups (intentional pitfall: inline rules) ---

# PITFALL: Using inline ingress/egress blocks instead of separate
# aws_security_group_rule resources. This pattern causes:
# 1. Perpetual diffs if mixed with standalone rules later
# 2. Dependency cycles if groups reference each other
# Canon: "Inline vs Standalone Rule Conflict" + "Mutual Security Group Reference Cycle"

resource "aws_security_group" "web" {
  name        = "${var.project}-web-sg"
  description = "Web tier security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-web-sg"
  }
}

resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "App tier security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTP from web tier"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-app-sg"
  }
}
