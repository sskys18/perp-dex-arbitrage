variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "telegram_bot_token" {
  description = "Telegram bot token from @BotFather"
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "Telegram chat ID for notifications"
  type        = string
  sensitive   = true
}
