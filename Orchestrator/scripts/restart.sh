#!/bin/bash
# Auto-restart script for Orchestrator API
# Flushes cache and restarts the uvicorn process

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRATOR_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${ORCHESTRATOR_PORT:-8502}"

echo "🔄 Restarting Orchestrator API..."

# 1. Kill existing uvicorn process
echo "  Stopping existing processes..."
pkill -f "uvicorn.*api:app.*$PORT" 2>/dev/null || true
fuser -k $PORT/tcp 2>/dev/null || true
sleep 2

# 2. Clear Python cache
echo "  Clearing Python cache..."
find "$ORCHESTRATOR_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$ORCHESTRATOR_DIR" -name "*.pyc" -delete 2>/dev/null || true

# 3. Start fresh
echo "  Starting API on port $PORT..."
cd "$ORCHESTRATOR_DIR"
nohup python3 -m uvicorn api:app --host 0.0.0.0 --port $PORT > /tmp/orchestrator_api.log 2>&1 &

# 4. Wait and verify
sleep 5
if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
    echo "✅ Orchestrator API running on port $PORT"
else
    echo "❌ Failed to start. Check /tmp/orchestrator_api.log"
    tail -20 /tmp/orchestrator_api.log
    exit 1
fi
