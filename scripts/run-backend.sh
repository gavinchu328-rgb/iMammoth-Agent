#!/usr/bin/env bash
# 后端守护：进程退出后自动拉起，避免 8080 掉线导致页面全空
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
BACKEND_PORT="${MAMMOTH_BACKEND_PORT:-8080}"
BACKEND_LOG="${MAMMOTH_BACKEND_LOG:-/tmp/mammoth-backend.log}"
PYTHON="${MAMMOTH_PYTHON:-/home/dbcloud/anaconda3/bin/python}"
UVICORN="${MAMMOTH_UVICORN:-/home/dbcloud/anaconda3/bin/uvicorn}"

echo "[$(date -Iseconds)] mammoth backend watchdog started (port ${BACKEND_PORT})" >>"$BACKEND_LOG"

while true; do
  echo "[$(date -Iseconds)] starting uvicorn on :${BACKEND_PORT}" >>"$BACKEND_LOG"
  cd "$BACKEND_DIR"
  "$UVICORN" main:app --host 0.0.0.0 --port "$BACKEND_PORT" >>"$BACKEND_LOG" 2>&1
  code=$?
  echo "[$(date -Iseconds)] uvicorn exited code=${code}, restart in 2s" >>"$BACKEND_LOG"
  sleep 2
done
