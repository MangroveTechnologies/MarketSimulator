#!/bin/bash
# Start the Experiment Framework dashboard.
#
# Builds the React UI, then starts (or restarts) the Docker container.
# Dashboard: http://localhost:5100/
# API docs:  http://localhost:5100/docs
#
# Usage:
#   ./start_experiment_server.sh          # build UI + start container
#   ./start_experiment_server.sh --skip-build   # start container only

set -e
cd "$(dirname "$0")"

# ── Build React UI ────────────────────────────────────────────────
if [[ "$1" != "--skip-build" ]]; then
  echo "[BUILD] Building React UI..."
  if [ -d experiment_ui/node_modules ]; then
    (cd experiment_ui && npx vite build --outDir ../experiment_ui_dist)
  else
    echo "[BUILD] Installing npm dependencies first..."
    (cd experiment_ui && npm install && npx vite build --outDir ../experiment_ui_dist)
  fi
  echo "[BUILD] Done. Output: experiment_ui_dist/"
else
  echo "[BUILD] Skipped (--skip-build)"
fi

# ── Start Docker container ────────────────────────────────────────
echo ""
echo "[DOCKER] Starting mangrove-sweep container..."

# Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q '^mangrove-sweep$'; then
  echo "[DOCKER] Stopping existing container..."
  docker stop mangrove-sweep >/dev/null 2>&1 || true
  docker rm mangrove-sweep >/dev/null 2>&1 || true
fi

docker compose up -d

echo ""
echo "=========================================="
echo "  Experiment Framework is running!"
echo "  Dashboard: http://localhost:5100/"
echo "  API docs:  http://localhost:5100/docs"
echo "=========================================="
echo ""
echo "Logs: docker logs -f mangrove-sweep"
echo "Stop: docker compose down"
