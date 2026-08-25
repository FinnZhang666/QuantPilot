#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${QUANTPILOT_APP_DIR:-/opt/quantpilot}"
SERVICE="${QUANTPILOT_SERVICE:-quantpilot-web.service}"
HEALTH_URL="${QUANTPILOT_HEALTH_URL:-http://127.0.0.1:8100/health}"

cd "$APP_DIR"
test -f .env
test "$(stat -c '%a' .env)" = "600"
grep -Eq '^APP_ROLE=cloud_web$' .env
grep -Eq '^REAL_AUTO_TRADING=false$' .env
grep -Eq '^MOOMOO_LIVE_TRADING_ENABLED=false$' .env
grep -Eq '^MOOMOO_ALLOW_ORDER_SUBMISSION=false$' .env

git fetch origin
git pull --ff-only origin main
"$APP_DIR/.venv/bin/python" -m pip install -r requirements.txt
"$APP_DIR/.venv/bin/python" -m compileall -q app

systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE"
curl --fail --silent --show-error "$HEALTH_URL"

echo "QuantPilot Cloud Web deployment complete. IndexLabs and Nginx were not restarted."
