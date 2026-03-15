#!/usr/bin/env bash
# CardioKB Web Interface Launcher
#
# Usage:
#   ./run.sh              # Start on default port 5050
#   ./run.sh 8080         # Start on custom port
#
# For remote access via ngrok:
#   ngrok http 5050

set -e

PORT="${1:-5050}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  CardioKB Web Interface"
echo "  ======================"
echo ""
echo "  Starting Flask on http://127.0.0.1:${PORT}"
echo ""
echo "  For remote access, run in another terminal:"
echo "    ngrok http ${PORT}"
echo ""

# Open browser after a short delay (background)
(sleep 1.5 && open "http://127.0.0.1:${PORT}" 2>/dev/null || true) &

# Activate conda and run
cd "$DIR"
conda run --no-banner -n cardiokb python src/api.py --port "$PORT"
