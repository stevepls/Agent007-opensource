#!/bin/bash
#
# Start Agent007 Dashboard
# Starts both the FastAPI backend and Next.js frontend
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🚀 Starting Agent007 Dashboard${NC}"
echo ""

# Kill any existing processes on the ports
echo -e "${YELLOW}Cleaning up existing processes...${NC}"
fuser -k 8502/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 1

# Start FastAPI backend (api.py loads .env itself)
echo -e "${GREEN}Starting FastAPI backend on port 8502...${NC}"
cd "$SCRIPT_DIR/Orchestrator"
python3 -m uvicorn api:app --host 0.0.0.0 --port 8502 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 3

# Start Next.js dashboard
echo -e "${GREEN}Starting Next.js dashboard on port 3000...${NC}"
cd "$SCRIPT_DIR/dashboard"
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Wait for frontend to be ready
sleep 5

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Agent007 Dashboard is running!${NC}"
echo ""
echo -e "  🖥️  Dashboard:  ${BLUE}http://localhost:3000${NC}"
echo -e "  ⚙️  API:        ${BLUE}http://localhost:8502${NC}"
echo -e "  📊  API Docs:   ${BLUE}http://localhost:8502/docs${NC}"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop all services"
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
