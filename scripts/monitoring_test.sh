#!/usr/bin/env bash
set -euo pipefail

# Simple monitoring test for SmartMailFinder on Vercel
# - Loads env from .env.vercel (override via ENV_FILE)
# - Checks health endpoint
# - Sends a test alert to ntfy webhook

ENV_FILE="${ENV_FILE:-.env.vercel}"
DOMAIN="${DOMAIN:-smartmailfinder.jp}"

if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env from $ENV_FILE"
  set -a; source "$ENV_FILE"; set +a
else
  echo "Env file $ENV_FILE not found; using current environment variables"
fi

APP_ERROR_WEBHOOK_URL="${APP_ERROR_WEBHOOK_URL:-}"
HEALTHCHECK_TOKEN="${HEALTHCHECK_TOKEN:-}"

if [[ -z "$APP_ERROR_WEBHOOK_URL" ]]; then
  echo "ERROR: APP_ERROR_WEBHOOK_URL is empty. Set it in $ENV_FILE or environment." >&2
  exit 1
fi

echo "--- Health Check ---"
HC_URL="https://${DOMAIN}/?health=${HEALTHCHECK_TOKEN:-1}"
echo "GET $HC_URL"
curl -sS "$HC_URL" | sed 's/.*/[health] &/' || true

echo "--- Send Test Alert ---"
ts="$(date -Iseconds)"
payload=$(cat <<JSON
{
  "level": "test",
  "source": "monitoring_test.sh",
  "message": "Test alert from SmartMailFinder",
  "timestamp": "$ts"
}
JSON
)

echo "POST $APP_ERROR_WEBHOOK_URL"
curl -sS -X POST "$APP_ERROR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "$payload" | sed 's/.*/[alert] &/' || true

echo "--- Done ---"
echo "Subscribe to ntfy topic to see alerts: $APP_ERROR_WEBHOOK_URL"
echo "Web UI: https://ntfy.sh/ (enter topic path after /)"