#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "[setup] Creating Python virtual environment in .venv"
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r backend/requirements.txt >/dev/null

if [[ ! -d "frontend/node_modules" ]]; then
  echo "[setup] Installing frontend dependencies"
  (cd frontend && npm install)
fi

if [[ ! -f ".env" ]]; then
  echo "[setup] No .env file found. Copying backend/.env.example to .env"
  cp backend/.env.example .env
fi

export GRAPH_DATA_PATH="${GRAPH_DATA_PATH:-frontend/src/assets/processed_graph.json}"

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 >/tmp/dodgeai_backend.log 2>&1 &
BACKEND_PID=$!

pushd frontend >/dev/null
npm run dev -- --host 0.0.0.0 --port 5173 >/tmp/dodgeai_frontend.log 2>&1 &
FRONTEND_PID=$!
popd >/dev/null

echo "Dodge AI FDE Task is live at http://localhost:5173"

echo "[info] Backend log: /tmp/dodgeai_backend.log"
echo "[info] Frontend log: /tmp/dodgeai_frontend.log"

after_exit() {
  kill "$BACKEND_PID" "$FRONTEND_PID" >/dev/null 2>&1 || true
}
trap after_exit EXIT INT TERM

wait
