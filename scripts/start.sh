#!/usr/bin/env bash
# 一键启动脚本 (Linux / macOS)
# 用法: ./scripts/start.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> 1) 启动基础设施 (Docker)"
docker compose up -d

echo "==> 2) 启动后端 (:8000)"
cd "$ROOT/backend"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m uvicorn app.main:app --port 8000 &
BACK_PID=$!

echo "==> 3) 启动前端 (:5173)"
cd "$ROOT/frontend"
npm install
npm run dev &
FRONT_PID=$!

trap "kill $BACK_PID $FRONT_PID" EXIT
wait
