#!/bin/bash
# Start the experiment framework server inside the Docker container.
# Serves the dashboard at http://localhost:5100/
#
# Usage:
#   docker exec mangrove-sweep /app/MarketSimulator/start_experiment_server.sh

set -e

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

export EXP_DATA_DIR=/app/MarketSimulator/data
export EXP_OHLCV_DIR=/app/MarketSimulator/data/ohlcv
export EXP_SIGNALS_METADATA_PATH=/app/MarketSimulator/data/signals_metadata.json
export EXP_TRADING_DEFAULTS_PATH=/app/MarketSimulator/data/trading_defaults.json

cd /app/MarketSimulator

# Install Python deps if not already installed
pip install -q fastapi uvicorn duckdb pyarrow pydantic pydantic-settings 2>/dev/null

echo "[EXPERIMENT SERVER] Starting on port 5100..."
echo "[EXPERIMENT SERVER] Dashboard: http://localhost:5100/"
echo "[EXPERIMENT SERVER] API docs:  http://localhost:5100/docs"

exec uvicorn experiment_server.app:app --host 0.0.0.0 --port 5100
