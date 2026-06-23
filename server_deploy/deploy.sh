#!/bin/bash
# Voice Flow License Server — one-command deploy
# Usage: bash deploy.sh

set -e

echo "=== Voice Flow License Server Deploy ==="

# 1. System packages
echo "[1/5] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# 2. App directory
echo "[2/5] Setting up app directory..."
mkdir -p /opt/voice-flow-server/data
cp *.py /opt/voice-flow-server/
cp -r keys /opt/voice-flow-server/
cp requirements.txt /opt/voice-flow-server/

# 3. Python dependencies
echo "[3/5] Installing Python dependencies..."
pip3 install --break-system-packages -r /opt/voice-flow-server/requirements.txt

# 4. systemd service
echo "[4/5] Setting up systemd service..."
cp voiceflow-server.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable voiceflow-server
systemctl restart voiceflow-server

# 5. Done
echo "[5/5] Done!"
echo ""
echo "Service status:"
systemctl status voiceflow-server --no-pager || true
echo ""
echo "Test: curl http://localhost:8000/api/ping"
curl -s http://localhost:8000/api/ping || echo "(service may need a moment to start)"
