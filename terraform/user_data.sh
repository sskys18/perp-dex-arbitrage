#!/bin/bash
set -e

# Install Python 3.12 and git
dnf install -y python3.12 python3.12-pip git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:$PATH"

# Clone repository
cd /opt
git clone https://github.com/sskys18/perp-dex-arbitrage.git
cd perp-dex-arbitrage

# Create virtual environment and install dependencies
uv venv --python python3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# Write environment variables
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=${telegram_bot_token}
TELEGRAM_CHAT_ID=${telegram_chat_id}
SIGNALS_DB_PATH=/opt/perp-dex-arbitrage/signals.db
EOF

# Create systemd service
cat > /etc/systemd/system/arbitrage.service << 'EOF'
[Unit]
Description=Perp DEX Arbitrage Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/perp-dex-arbitrage
EnvironmentFile=/opt/perp-dex-arbitrage/.env
ExecStart=/opt/perp-dex-arbitrage/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl daemon-reload
systemctl enable arbitrage
systemctl start arbitrage
