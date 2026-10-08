#!/usr/bin/env bash
# Ensure an ngrok tunnel to the local Odoo exists and store its public URL as
# the webhook Odoo's IAP servers call back into (ai.open_iap.standard_webhook_url).
# When the standard Odoo IAP is selected (no replacement connection), the URL is
# also written to ai.webhook_url and ai.endpoint is removed. Safe to run while
# Odoo is up: the "stable" ORM cache is signalled so running servers re-read
# the parameters.
#
# Usage: ngrok_webhook.sh <database> [odoo_port]
set -euo pipefail

DB="${1:?database name required}"
PORT="${2:-20069}"
API="http://127.0.0.1:4040/api/tunnels"
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logging"

tunnel_url() {
    curl -s -m 2 "$API" 2>/dev/null | python3 -c '
import json, sys
port = sys.argv[1]
try:
    tunnels = json.load(sys.stdin)["tunnels"]
except Exception:
    sys.exit(0)
for tunnel in tunnels:
    addr = tunnel.get("config", {}).get("addr", "")
    if tunnel.get("public_url", "").startswith("https://") and addr.rstrip("/").endswith(":" + port):
        print(tunnel["public_url"])
        break
' "$PORT" || true
}

URL="$(tunnel_url)"
if [ -z "$URL" ]; then
    if curl -s -m 2 -o /dev/null "$API"; then
        echo "ngrok is running but has no tunnel to port $PORT; stop it first." >&2
        exit 1
    fi
    mkdir -p "$LOG_DIR"
    setsid nohup ngrok http "$PORT" --log=stdout > "$LOG_DIR/ngrok.out" 2>&1 < /dev/null &
    for _i in $(seq 1 30); do
        URL="$(tunnel_url)"
        [ -n "$URL" ] && break
        sleep 0.5
    done
fi
if [ -z "$URL" ]; then
    echo "ngrok tunnel did not come up, see $LOG_DIR/ngrok.out" >&2
    tail -20 "$LOG_DIR/ngrok.out" >&2 || true
    exit 1
fi

psql -d "$DB" -v ON_ERROR_STOP=1 -q -v url="$URL" <<'SQL'
INSERT INTO ir_config_parameter (key, value, create_date, write_date)
VALUES ('ai.open_iap.standard_webhook_url', :'url', now(), now())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now();

-- Standard IAP is active when no replacement connection is selected.
INSERT INTO ir_config_parameter (key, value, create_date, write_date)
SELECT 'ai.webhook_url', :'url', now(), now()
WHERE NOT EXISTS (
    SELECT 1 FROM ir_config_parameter
    WHERE key = 'ai.open_iap.connection_id' AND coalesce(value, '') <> ''
)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now();

-- Without ai.endpoint Odoo uses its own IAP server (https://ai.api.odoo.com).
DELETE FROM ir_config_parameter
WHERE key = 'ai.endpoint'
    AND NOT EXISTS (
        SELECT 1 FROM ir_config_parameter
        WHERE key = 'ai.open_iap.connection_id' AND coalesce(value, '') <> ''
    );

INSERT INTO orm_signaling_stable DEFAULT VALUES;
SQL

echo "ngrok webhook for $DB: $URL"
