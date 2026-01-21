#!/bin/bash
# Load .env and run terraform apply

set -e
cd "$(dirname "$0")"

# Source parent .env file
if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
fi

# Map to Terraform variables
export TF_VAR_telegram_bot_token="$TELEGRAM_BOT_TOKEN"
export TF_VAR_telegram_chat_id="$TELEGRAM_CHAT_ID"

terraform init
terraform apply "$@"
