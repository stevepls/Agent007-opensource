#!/bin/bash
#
# Start Agent007 Dashboard (Local Development)
# Starts both the FastAPI backend and Next.js frontend with auth bypassed.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

echo -e "${BLUE}🚀 Starting Agent007 Dashboard (local dev)${NC}"
echo ""

# Kill any existing processes on the ports
echo -e "${DIM}Cleaning up existing processes...${NC}"
fuser -k 8502/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 1

# ── Orchestrator ──────────────────────────────────────────────
echo -e "${GREEN}Starting Orchestrator on port 8502...${NC}"
cd "$SCRIPT_DIR/Orchestrator"

# Disable auth for local dev
export AUTH_ENABLED=false

python3 -m uvicorn api:app --host 0.0.0.0 --port 8502 --log-level info &
BACKEND_PID=$!
echo -e "  ${DIM}PID: $BACKEND_PID${NC}"

# Wait for backend to be ready
echo -e "  ${DIM}Waiting for Orchestrator...${NC}"
for i in $(seq 1 30); do
    if curl -s http://localhost:8502/health >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ Orchestrator ready${NC}"
        break
    fi
    sleep 1
done

# ── Dashboard ─────────────────────────────────────────────────
echo -e "${GREEN}Starting Dashboard on port 3000...${NC}"
cd "$SCRIPT_DIR/dashboard"

# Ensure BYPASS_AUTH is set for local dev
export BYPASS_AUTH=true

npm run dev &
FRONTEND_PID=$!
echo -e "  ${DIM}PID: $FRONTEND_PID${NC}"

sleep 3

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Agent007 is running!${NC}"
echo ""
echo -e "  🖥️  Dashboard:    ${BLUE}http://localhost:3000${NC}"
echo -e "  ⚙️  API:          ${BLUE}http://localhost:8502${NC}"
echo -e "  📊  API Docs:     ${BLUE}http://localhost:8502/docs${NC}"
echo -e "  🔑  Settings:     ${BLUE}http://localhost:3000/settings${NC}"
echo -e "  📋  Queue API:    ${BLUE}http://localhost:8502/api/queue${NC}"
echo -e "  📰  Briefing API: ${BLUE}http://localhost:8502/api/briefing${NC}"
echo ""
echo -e "  ${DIM}Auth: bypassed (local dev mode)${NC}"
echo -e "  ${DIM}Press ${YELLOW}Ctrl+C${NC}${DIM} to stop all services${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Trap to clean up on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    fuser -k 8502/tcp 2>/dev/null || true
    fuser -k 3000/tcp 2>/dev/null || true
    echo -e "${GREEN}Done.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for either process to exit
wait
