#!/usr/bin/env bash
# AI-Dashboard-Control — start supervisor server + Next.js dashboard
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Colours
GRN='\033[0;32m' DIM='\033[2m' RST='\033[0m'

echo -e "${GRN}ai-dashboard-control${RST}"
echo -e "${DIM}starting supervisor server on :8765 and dashboard on :3000${RST}"
echo ""

# Kill on exit
trap 'kill $(jobs -p) 2>/dev/null; echo "stopped."' EXIT

# Start FastAPI supervisor server
python3 "$ROOT/server.py" --port 8765 &
sleep 1.5
echo -e "${GRN}✓ supervisor server${RST}  http://localhost:8765"

# Start Next.js dashboard
cd "$ROOT/dashboard"
npm run dev -- --port 3000 &
sleep 2
echo -e "${GRN}✓ dashboard${RST}          http://localhost:3000"
echo ""
echo -e "${DIM}Press Ctrl+C to stop both.${RST}"

wait
