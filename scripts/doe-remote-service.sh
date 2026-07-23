#!/usr/bin/env bash
# DOE 实验设计智能体 — 在 192.168.9.116 本机执行的启停脚本
# 由猛犸仓库 scripts/doe-service.sh 通过 SSH 调用（或直接在 DOEAgent 目录运行）

set -euo pipefail

DOE_ROOT="${DOE_ROOT:-/home/admin/AIProject/DOEAgent}"
BACKEND_PORT="${DOE_BACKEND_PORT:-8000}"
FRONTEND_PORT="${DOE_FRONTEND_PORT:-5173}"
CONDA_ENV="${DOE_CONDA_ENV:-doe_env}"
BACKEND_LOG="${DOE_BACKEND_LOG:-$DOE_ROOT/backend.log}"
FRONTEND_LOG="${DOE_FRONTEND_LOG:-$DOE_ROOT/frontend.log}"

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 "$1" 2>/dev/null || echo "000"
}

port_listen() {
  ss -ltn 2>/dev/null | grep -q ":${1}\\b" || \
    netstat -ltn 2>/dev/null | grep -q ":${1}\\b"
}

# 前端必须监听 0.0.0.0，仅 127.0.0.1 时外网 iframe 会 connection refused
frontend_public_ok() {
  ss -ltnp 2>/dev/null | grep ":${FRONTEND_PORT}\\b" | grep -q '0.0.0.0' || \
    netstat -ltnp 2>/dev/null | grep ":${FRONTEND_PORT}\\b" | grep -q '0.0.0.0'
}

activate_conda() {
  if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
  else
    echo "未找到 conda，请设置 DOE_CONDA_ENV 或手动激活环境" >&2
    return 1
  fi
  conda activate "$CONDA_ENV"
}

stop_frontend() {
  pkill -f "${DOE_ROOT}/frontend/node_modules/.bin/vite" 2>/dev/null || true
  fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true
}

stop_backend() {
  pkill -f "${DOE_ROOT}/backend.*uvicorn app.main:app" 2>/dev/null || true
  fuser -k "${BACKEND_PORT}/tcp" 2>/dev/null || true
}

start_backend() {
  if port_listen "$BACKEND_PORT"; then
    echo "后端已在运行 (:${BACKEND_PORT})，跳过"
    return 0
  fi
  echo "启动后端 (uvicorn :${BACKEND_PORT})..."
  activate_conda
  cd "$DOE_ROOT/backend"
  export CORS_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
  nohup python -m uvicorn app.main:app \
    --host 0.0.0.0 --port "$BACKEND_PORT" \
    >"$BACKEND_LOG" 2>&1 &
  sleep 2
}

start_frontend() {
  if frontend_public_ok; then
    echo "前端已在运行 (0.0.0.0:${FRONTEND_PORT})，跳过"
    return 0
  fi
  echo "启动前端 (vite preview 0.0.0.0:${FRONTEND_PORT})..."
  stop_frontend
  sleep 1
  cd "$DOE_ROOT/frontend"
  if [[ ! -d dist ]]; then
    echo "未找到 frontend/dist，执行 npm run build ..."
    npm run build
  fi
  nohup npx vite preview --host 0.0.0.0 --port "$FRONTEND_PORT" \
    >"$FRONTEND_LOG" 2>&1 &
  sleep 3
}

cmd_start() {
  echo "=== 启动 DOE 实验设计智能体 ==="
  echo "目录: $DOE_ROOT"
  start_backend
  start_frontend
  cmd_status
}

cmd_stop() {
  echo "=== 停止 DOE 实验设计智能体 ==="
  stop_frontend
  stop_backend
  sleep 1
  echo "已停止"
}

cmd_status() {
  local lan_ip
  lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "=== DOE 实验设计智能体状态 ==="
  echo "目录: $DOE_ROOT"
  echo "访问: http://${lan_ip:-127.0.0.1}:${FRONTEND_PORT}/"
  echo "后端 :${BACKEND_PORT}  listen=$(port_listen "$BACKEND_PORT" && echo yes || echo no)  http=$(http_code "http://127.0.0.1:${BACKEND_PORT}/docs")"
  if frontend_public_ok; then
    echo "前端 :${FRONTEND_PORT}  listen=0.0.0.0  http=$(http_code "http://127.0.0.1:${FRONTEND_PORT}/")"
  elif port_listen "$FRONTEND_PORT"; then
    echo "前端 :${FRONTEND_PORT}  listen=127.0.0.1 ONLY  (外网不可达，请 restart)"
  else
    echo "前端 :${FRONTEND_PORT}  listen=no"
  fi
  if [[ -f "$BACKEND_LOG" ]]; then
    echo "后端日志尾:"
    tail -n 3 "$BACKEND_LOG" | sed 's/^/  /'
  fi
  if [[ -f "$FRONTEND_LOG" ]]; then
    echo "前端日志尾:"
    tail -n 4 "$FRONTEND_LOG" | sed 's/^/  /'
  fi
}

cmd_fix_frontend() {
  echo "=== 修复前端监听地址（127.0.0.1 → 0.0.0.0）==="
  stop_frontend
  sleep 1
  start_frontend
  cmd_status
}

usage() {
  cat <<EOF
用法: $0 {start|stop|restart|status|fix-frontend}

  DOE 实验设计智能体（本机 $DOE_ROOT）
  - 后端 FastAPI  :${BACKEND_PORT}
  - 前端 Vite     :${FRONTEND_PORT}  (必须 0.0.0.0，供智能体广场 iframe)

环境变量:
  DOE_ROOT           项目根目录
  DOE_CONDA_ENV      conda 环境名（默认 doe_env）
  DOE_BACKEND_PORT   后端端口
  DOE_FRONTEND_PORT  前端端口
EOF
}

main() {
  case "${1:-}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
    status) cmd_status ;;
    fix-frontend) cmd_fix_frontend ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
