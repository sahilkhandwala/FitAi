#!/bin/bash
# Run on the VM to pull the latest code and restart services.
# Usage: bash /opt/nutrition-bot/deployment/update.sh
set -euo pipefail

APP_DIR=/opt/nutrition-bot
VENV=$APP_DIR/venv

echo "=== Stopping services ==="
systemctl stop nutrition-bot || true

echo "=== Installing updated dependencies ==="
$VENV/bin/pip install -r $APP_DIR/requirements.txt -q

echo "=== Running DB migrations (safe to re-run) ==="
cd $APP_DIR
$VENV/bin/python -c "
from db import get_engine
from db.models import Base
Base.metadata.create_all(get_engine())
print('DB up-to-date')
"

echo "=== Restarting services ==="
systemctl start nutrition-bot
systemctl status nutrition-bot --no-pager -l

echo "=== Done ==="
