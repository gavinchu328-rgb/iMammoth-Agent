#!/usr/bin/env bash
# 猛犸智能体服务管理脚本
# 用法: ./scripts/service.sh {start|stop|restart|status|deps}
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT="${MAMMOTH_BACKEND_PORT:-8080}"
FRONTEND_PORT="${MAMMOTH_FRONTEND_PORT:-5173}"
BACKEND_LOG="${MAMMOTH_BACKEND_LOG:-/tmp/mammoth-backend.log}"
FRONTEND_LOG="${MAMMOTH_FRONTEND_LOG:-/tmp/mammoth-frontend.log}"

pid_on_port() {
  local port="$1"
  ss -ltnp 2>/dev/null | rg ":${port}\\b" | rg -o 'pid=[0-9]+' | head -1 | cut -d= -f2 || true
}

http_code() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" 2>/dev/null || true)"
  if [[ -z "$code" || "$code" == "000" ]]; then
    echo "000"
  else
    echo "$code"
  fi
}

kill_port() {
  local port="$1"
  local pid
  pid="$(pid_on_port "$port")"
  if [[ -n "$pid" ]]; then
    echo "停止端口 ${port} (pid=${pid})"
    kill "$pid" 2>/dev/null || true
    sleep 1
    if [[ -n "$(pid_on_port "$port")" ]]; then
      kill -9 "$(pid_on_port "$port")" 2>/dev/null || true
    fi
  else
    echo "端口 ${port} 无进程"
  fi
}

start_backend() {
  if [[ -n "$(pid_on_port "$BACKEND_PORT")" ]]; then
    echo "后端已在 :${BACKEND_PORT} 运行"
    return 0
  fi
  echo "启动后端 :${BACKEND_PORT}"
  cd "$BACKEND_DIR"
  nohup uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
  sleep 2
  echo "  log: $BACKEND_LOG"
  echo "  health: $(http_code "http://127.0.0.1:${BACKEND_PORT}/api/health")"
}

start_frontend() {
  if [[ -n "$(pid_on_port "$FRONTEND_PORT")" ]]; then
    echo "前端已在 :${FRONTEND_PORT} 运行"
    return 0
  fi
  echo "启动前端 :${FRONTEND_PORT}"
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    echo "  安装前端依赖 npm install ..."
    npm install
  fi
  nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
  sleep 2
  echo "  log: $FRONTEND_LOG"
  echo "  http: $(http_code "http://127.0.0.1:${FRONTEND_PORT}/")"
}

cmd_start() {
  echo "=== 启动猛犸智能体 ==="
  echo "代码: $ROOT"
  start_backend
  start_frontend
  echo ""
  echo "前端: http://0.0.0.0:${FRONTEND_PORT}"
  echo "后端: http://0.0.0.0:${BACKEND_PORT}"
  echo "文档: $ROOT/docs/DEPLOY.md"
}

cmd_stop() {
  echo "=== 停止猛犸智能体 ==="
  kill_port "$FRONTEND_PORT"
  kill_port "$BACKEND_PORT"
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_status() {
  echo "=== 猛犸服务状态 ==="
  local bp fp
  bp="$(pid_on_port "$BACKEND_PORT")"
  fp="$(pid_on_port "$FRONTEND_PORT")"
  echo "代码目录: $ROOT"
  echo "后端 :${BACKEND_PORT}  pid=${bp:-无}  health=$(http_code "http://127.0.0.1:${BACKEND_PORT}/api/health")"
  echo "前端 :${FRONTEND_PORT}  pid=${fp:-无}  http=$(http_code "http://127.0.0.1:${FRONTEND_PORT}/")"
  if [[ -f "$BACKEND_LOG" ]]; then
    echo "后端日志尾:"
    tail -n 5 "$BACKEND_LOG" | sed 's/^/  /'
  fi
}

cmd_deps() {
  echo "=== 依赖 / 智能体相关服务 ==="
  echo "OpenClaw Gateway :18789  http=$(http_code "http://127.0.0.1:18789/")"
  if systemctl --user is-active openclaw-gateway >/dev/null 2>&1; then
    echo "  systemd: openclaw-gateway = $(systemctl --user is-active openclaw-gateway)"
  else
    echo "  systemd: openclaw-gateway = $(systemctl --user is-active openclaw-gateway 2>/dev/null || echo unknown)"
  fi
  if ss -ltn 2>/dev/null | rg -q ':5434\b'; then
    echo "PostgreSQL       :5434   LISTEN"
  else
    echo "PostgreSQL       :5434   DOWN"
  fi
  echo "Qwen 推理        :8006   http=$(http_code "http://127.0.0.1:8006/v1/models")"
  echo "AI4Drug MCP      :8000   http=$(http_code "http://127.0.0.1:8000/")"
  echo "猛犸 Backend     :${BACKEND_PORT}   health=$(http_code "http://127.0.0.1:${BACKEND_PORT}/api/health")"
  echo "猛犸 Frontend    :${FRONTEND_PORT}   http=$(http_code "http://127.0.0.1:${FRONTEND_PORT}/")"
  echo ""
  echo "OpenClaw agents (from ~/.openclaw/openclaw.json):"
  python3 - <<'PY' 2>/dev/null || echo "  (cannot read openclaw.json)"
import json
from pathlib import Path
p = Path.home() / ".openclaw/openclaw.json"
if not p.exists():
    print("  missing config")
else:
    for a in json.loads(p.read_text()).get("agents", {}).get("list", []):
        print(f"  - {a.get('id')}: {a.get('workspace')}")
PY
  echo ""
  echo "过程日志目录: $ROOT/process_logs/"
  ls -la "$ROOT/process_logs" 2>/dev/null | sed 's/^/  /' || true
  echo ""
  echo "维护提示:"
  echo "  OpenClaw: systemctl --user {status|restart} openclaw-gateway"
  echo "  猛犸:     $ROOT/scripts/service.sh {start|stop|restart|status}"
  echo "  详情:     $ROOT/docs/DEPLOY.md"
}

usage() {
  cat <<EOF
用法: $0 {start|stop|restart|status|deps}

  start     启动猛犸前端+后端（后台）
  stop      停止猛犸前端+后端
  restart   重启
  status    查看猛犸进程与健康
  deps      检查 OpenClaw / DB / 模型等依赖与 Agent 列表

环境变量（可选）:
  MAMMOTH_BACKEND_PORT   默认 8080
  MAMMOTH_FRONTEND_PORT  默认 5173
  MAMMOTH_BACKEND_LOG    默认 /tmp/mammoth-backend.log
  MAMMOTH_FRONTEND_LOG   默认 /tmp/mammoth-frontend.log
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    deps) cmd_deps ;;
    -h|--help|help) usage ;;
    "") usage; exit 1 ;;
    *) echo "未知命令: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
