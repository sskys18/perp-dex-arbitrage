#!/bin/bash
set -e

# Install Docker
apt-get update
apt-get install -y docker.io awscli
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Write environment file
cat > /opt/arbitrage.env << 'EOF'
TELEGRAM_BOT_TOKEN=${telegram_bot_token}
TELEGRAM_CHAT_ID=${telegram_chat_id}
SIGNALS_DB_PATH=/data/signals.db
EOF

# Create data directory for persistence
mkdir -p /data

# Create deploy script
cat > /opt/deploy.sh << 'SCRIPT'
#!/bin/bash
set -e
REGION=${region}
ACCOUNT_ID=${account_id}
ECR_URL="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/perp-dex-arbitrage"

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

docker pull $ECR_URL:latest || exit 1
docker stop arbitrage 2>/dev/null || true
docker rm arbitrage 2>/dev/null || true
docker run -d --name arbitrage --restart always --env-file /opt/arbitrage.env -v /data:/data $ECR_URL:latest
SCRIPT
chmod +x /opt/deploy.sh
