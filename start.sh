#!/usr/bin/env bash
# ==============================================================================
# AgentPay All-in-One Local Development Launcher
# Starts Docker (PostgreSQL), FastAPI Backend, and Vite Frontend together.
# ==============================================================================

set -e

# Find the repository root regardless of current working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

cd "$ROOT_DIR"

# Text styles
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}${BLUE}===================================================================${NC}"
echo -e "${BOLD}${BLUE}           🛡️  Starting AgentPay Full Stack Environment            ${NC}"
echo -e "${BOLD}${BLUE}===================================================================${NC}"

# 1. Check Docker & PostgreSQL
echo -e "\n${BOLD}${YELLOW}[1/4] Checking PostgreSQL Docker Container...${NC}"
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running. Please launch Docker Desktop and retry.${NC}"
    exit 1
fi

docker compose up -d
echo -e "${GREEN}✓ PostgreSQL container is active on port 5432${NC}"

# 2. Setup Python environment & run migrations
echo -e "\n${BOLD}${YELLOW}[2/4] Checking Backend Environment & Migrations...${NC}"
cd "$ROOT_DIR/backend"

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

.venv/bin/alembic upgrade head
echo -e "${GREEN}✓ Database schema is up-to-date${NC}"

# 3. Check Frontend node_modules
echo -e "\n${BOLD}${YELLOW}[3/4] Checking Frontend Dependencies...${NC}"
cd "$ROOT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend node dependencies...${NC}"
    npm install
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

# 4. Start Services in Parallel
echo -e "\n${BOLD}${YELLOW}[4/4] Starting Backend and Frontend Servers...${NC}"

# Trap SIGINT / SIGTERM to cleanly kill child processes
cleanup() {
    echo -e "\n${BOLD}${YELLOW}Shutting down AgentPay services...${NC}"
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ All services stopped cleanly.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Start backend
cd "$ROOT_DIR/backend"
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

sleep 2

echo -e "\n${BOLD}${GREEN}===================================================================${NC}"
echo -e "${BOLD}${GREEN}  🚀 AgentPay Services are Running!                                ${NC}"
echo -e "${BOLD}${GREEN}===================================================================${NC}"
echo -e "  🌐 Frontend Dashboard: ${BOLD}http://localhost:5173${NC}"
echo -e "  ⚙️  Backend API & Docs:  ${BOLD}http://127.0.0.1:8000/docs${NC}"
echo -e "  🩺 Health Endpoint:     ${BOLD}http://127.0.0.1:8000/health${NC}"
echo -e "${BOLD}${YELLOW}-------------------------------------------------------------------${NC}"
echo -e "  Press ${BOLD}Ctrl+C${NC} in this terminal to stop all services."
echo -e "${BOLD}${YELLOW}-------------------------------------------------------------------${NC}\n"

# Wait for both processes
wait
