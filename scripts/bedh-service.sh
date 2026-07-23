#!/usr/bin/env bash
# BEDH 数字人智能体（Fay 后端 + Xmov 前端）启停脚本
# 代码目录：/data1/BEDH
# 详细说明：/data1/BEDH/README.txt

set -euo pipefail

BEDH_ROOT="${BEDH_ROOT:-/data1/BEDH}"
LOG_DIR="$BEDH_ROOT/deploy/logs"
FAY_PID_FILE="$LOG_DIR/fay.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
CONDA_ENV="${BEDH_CONDA_ENV:-/data1/Xmo}"

http_code() {
  curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 "$1" 2>/dev/null || echo "000"
}

port_listen() {
  ss -ltn 2>/dev/null | rg -q ":$1\\b"
}

cmd_start() {
  mkdir -p "$LOG_DIR"
  echo "=== 启动 BEDH 数字人智能体 ==="
  echo "目录: $BEDH_ROOT"

  if port_listen 5000 && port_listen 10003; then
    echo "Fay 已在运行 (5000/10003)，跳过"
  else
    echo "启动 Fay 后端..."
    nohup bash -c "
      source /home/dbcloud/anaconda3/etc/profile.d/conda.sh
      conda activate '$CONDA_ENV'
      cd '$BEDH_ROOT/Fay'
      export FAY_HTTP_PORT=5000 FAY_HUMAN_WS_PORT=10002 FAY_WEB_WS_PORT=10003
      python main.py start
    " >"$LOG_DIR/fay.nohup.log" 2>&1 &
    echo $! >"$FAY_PID_FILE"
    sleep 3
  fi

  if port_listen 5173; then
    echo "前端已在运行 (5173)，跳过"
  else
    echo "启动前端 (HTTPS :5173)..."
    nohup bash -c "
      cd '$BEDH_ROOT/XmovLiteAvatarJSDemo'
      npm run dev -- --host 0.0.0.0 --port 5173
    " >"$LOG_DIR/frontend.nohup.log" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
    sleep 4
  fi

  cmd_status
}

cmd_stop() {
  echo "=== 停止 BEDH 数字人智能体 ==="
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    kill "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null || true
    rm -f "$FRONTEND_PID_FILE"
  fi
  if [[ -f "$FAY_PID_FILE" ]]; then
    kill "$(cat "$FAY_PID_FILE")" 2>/dev/null || true
    rm -f "$FAY_PID_FILE"
  fi
  pkill -f "python main.py start" 2>/dev/null || true
  fuser -k 5173/tcp 2>/dev/null || true
  fuser -k 5000/tcp 2>/dev/null || true
  fuser -k 10002/tcp 2>/dev/null || true
  fuser -k 10003/tcp 2>/dev/null || true
  echo "已停止"
}

cmd_status() {
  echo "=== BEDH 数字人智能体状态 ==="
  echo "代码: $BEDH_ROOT"
  echo "访问: https://192.168.11.209:5173/  (自签名证书，浏览器需信任)"
  echo "Fay HTTP     :5000   http=$(http_code http://127.0.0.1:5000/)  listen=$(port_listen 5000 && echo yes || echo no)"
  echo "Fay WS       :10003  listen=$(port_listen 10003 && echo yes || echo no)"
  echo "Fay Avatar WS:10002  listen=$(port_listen 10002 && echo yes || echo no)"
  echo "前端 Vite    :5173   https=$(http_code https://127.0.0.1:5173/)  listen=$(port_listen 5173 && echo yes || echo no)"
  if [[ -f "$LOG_DIR/fay.nohup.log" ]]; then
    echo "Fay 日志尾:"
    tail -n 3 "$LOG_DIR/fay.nohup.log" | sed 's/^/  /'
  fi
  if [[ -f "$LOG_DIR/frontend.nohup.log" ]]; then
    echo "前端日志尾:"
    tail -n 3 "$LOG_DIR/frontend.nohup.log" | sed 's/^/  /'
  fi
}

usage() {
  cat <<EOF
用法: $0 {start|stop|restart|status}

  BEDH 数字人智能体（/data1/BEDH）
  - Fay 后端 :5000 / WS :10002,:10003
  - 前端     :5173 (HTTPS，Vite dev)

环境变量:
  BEDH_ROOT       默认 /data1/BEDH
  BEDH_CONDA_ENV  默认 /data1/Xmo

详见: /data1/BEDH/README.txt 与 docs/DEPLOY.md §5.0
EOF
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
    status) cmd_status ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
