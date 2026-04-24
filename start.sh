#!/bin/bash
# Start both backend and frontend dev servers

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting HockeyData backend..."
cd "$ROOT/backend"
python3 -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Starting HockeyData frontend..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers."

cleanup() {
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
