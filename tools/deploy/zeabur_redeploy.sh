#!/usr/bin/env bash
# One-shot Zeabur redeploy for btc-auto (Pure AI + Console UI).
set -euo pipefail
PROJECT_ID="${ZEABUR_PROJECT_ID:-69d559b62696d526abde8cd9}"
SERVICE_ID="${ZEABUR_SERVICE_ID:-69d559cb2696d526abde8cda}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  npx zeabur variable env -f .env --id "$SERVICE_ID" -i=false
fi
npx zeabur deploy --service-id "$SERVICE_ID" --project-id "$PROJECT_ID" -i=false
echo "Done. Verify: /health console_assets.ok and /api/nexus/pure-ai-status"
