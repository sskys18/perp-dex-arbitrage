output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.arbitrage.id
}

output "public_ip" {
  description = "EC2 public IP address"
  value       = aws_instance.arbitrage.public_ip
}

output "ecr_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.arbitrage.repository_url
}
