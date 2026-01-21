terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

resource "tls_private_key" "arbitrage" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "arbitrage" {
  key_name   = "perp-dex-arbitrage"
  public_key = tls_private_key.arbitrage.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.arbitrage.private_key_pem
  filename        = "${path.module}/arbitrage.pem"
  file_permission = "0400"
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_security_group" "arbitrage" {
  name        = "perp-dex-arbitrage"
  description = "Security group for arbitrage bot"

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "perp-dex-arbitrage"
  }
}

resource "aws_iam_role" "arbitrage" {
  name = "perp-dex-arbitrage"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.arbitrage.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr" {
  role       = aws_iam_role.arbitrage.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_ecr_repository" "arbitrage" {
  name                 = "perp-dex-arbitrage"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_iam_instance_profile" "arbitrage" {
  name = "perp-dex-arbitrage"
  role = aws_iam_role.arbitrage.name
}

resource "aws_instance" "arbitrage" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.arbitrage.key_name
  iam_instance_profile   = aws_iam_instance_profile.arbitrage.name
  vpc_security_group_ids = [aws_security_group.arbitrage.id]

  user_data = templatefile("${path.module}/user_data.sh", {
    telegram_bot_token = var.telegram_bot_token
    telegram_chat_id   = var.telegram_chat_id
    region             = var.aws_region
    account_id         = data.aws_caller_identity.current.account_id
  })

  tags = {
    Name = "perp-dex-arbitrage"
  }
}
