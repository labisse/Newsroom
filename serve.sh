#!/usr/bin/env bash
# Local dev server for Editorial Signal POC.
# Usage: ./serve.sh [port]   (default 4173)

set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-4173}"

echo "Editorial Signal · POC local"
echo "  → http://localhost:${PORT}/"
echo "  → http://localhost:${PORT}/reporter.html"
echo ""
echo "Ctrl+C pour arrêter."

exec python3 -m http.server "${PORT}" --bind 127.0.0.1
