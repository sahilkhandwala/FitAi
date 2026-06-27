#!/bin/bash
# Run once on the VM to set up everything from scratch.
# Usage: bash setup_vm.sh
set -euo pipefail

APP_DIR=/opt/nutrition-bot
VENV=$APP_DIR/venv

echo "=== Creating app directory ==="
mkdir -p $APP_DIR/logs/traces
mkdir -p $APP_DIR/knowledge_base

echo "=== Installing system packages ==="
apt-get update -q
apt-get install -y -q python3.11 python3.11-venv python3.11-dev docker.io sqlite3

echo "=== Creating virtualenv ==="
python3.11 -m venv $VENV

echo "=== Installing Python dependencies ==="
$VENV/bin/pip install --upgrade pip -q
$VENV/bin/pip install -r $APP_DIR/requirements.txt -q

echo "=== Running DB migration ==="
cd $APP_DIR
$VENV/bin/python -c "
from db import get_engine, get_session_factory
from db.models import Base
engine = get_engine()
Base.metadata.create_all(engine)
print('DB tables created')
"

echo "=== Installing systemd services ==="
cp $APP_DIR/deployment/nutrition-bot.service /etc/systemd/system/
cp $APP_DIR/deployment/prefect-server.service /etc/systemd/system/
cp $APP_DIR/deployment/prefect-worker.service /etc/systemd/system/
systemctl daemon-reload

echo "=== Enabling services ==="
systemctl enable nutrition-bot prefect-server prefect-worker

echo "=== Starting Docker (Uptime Kuma) ==="
systemctl enable docker
systemctl start docker
docker run -d --restart=always \
  -p 3001:3001 \
  -v uptime-kuma:/app/data \
  --name uptime-kuma \
  louislam/uptime-kuma:1
echo "Uptime Kuma started on port 3001"

echo ""
echo "=== Setup complete! ==="
echo "Next steps:"
echo "  1. Edit /opt/nutrition-bot/.env with your secrets"
echo "  2. Run: systemctl start prefect-server && sleep 15"
echo "  3. Run: cd /opt/nutrition-bot && $VENV/bin/python deployment/deploy_flows.py"
echo "  4. Run: systemctl start prefect-worker nutrition-bot"
echo "  5. Open http://VM_EXTERNAL_IP:4200 for Prefect UI"
echo "  6. Open http://VM_EXTERNAL_IP:3001 for Uptime Kuma"
