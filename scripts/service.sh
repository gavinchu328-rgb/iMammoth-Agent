#!/usr/bin/env bash
# 猛犸智能体服务管理脚本
# 用法: ./scripts/service.sh {start|stop|restart|status|deps|build}
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_PORT="${MAMMOTH_BACKEND_PORT:-8080}"
FRONTEND_PORT="${MAMMOTH_FRONTEND_PORT:-5174}"
FRONTEND_MODE="${MAMMOTH_FRONTEND_MODE:-dev}"   # dev | prod
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

# Returns "code|seconds" e.g. "200|0.042"
http_probe() {
  local url="$1" timeout="${2:-5}"
  curl -s -o /dev/null -w '%{http_code}|%{time_total}' --max-time "$timeout" "$url" 2>/dev/null || echo "000|timeout"
}

format_probe() {
  local label="$1" result="$2" warn_sec="${3:-3}"
  local code time note=""
  IFS='|' read -r code time <<<"$result"
  if [[ "$code" == "000" || "$time" == "timeout" ]]; then
    note=" DOWN"
  elif python3 -c "import sys; sys.exit(0 if float('${time}') <= float('${warn_sec}') else 1)" 2>/dev/null; then
    :
  else
    note=" SLOW"
  fi
  if [[ "$time" == "timeout" ]]; then
    echo "  ${label}: ${code} (timeout)${note}"
  else
    printf "  ${label}: %s %.3fs%s\n" "$code" "$time" "$note"
  fi
}

frontend_shell_ok() {
  local html
  html="$(curl -s --max-time 5 "http://127.0.0.1:${FRONTEND_PORT}/" 2>/dev/null || true)"
  if [[ -z "$html" ]]; then
    echo "no"
    return
  fi
  if echo "$html" | rg -q 'id="root"'; then
    echo "ok"
  else
    echo "bad-html"
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

ensure_frontend_build() {
  cd "$FRONTEND_DIR"
  local need_build=0
  if [[ ! -f dist/index.html ]]; then
    need_build=1
  elif find src index.html vite.config.ts -newer dist/index.html -print -quit 2>/dev/null | rg -q .; then
    need_build=1
  fi
  if [[ "$need_build" -eq 1 ]]; then
    echo "  构建前端 (npm run build) ..."
    npm run build
  else
    echo "  使用已有构建 frontend/dist"
  fi
}

start_backend() {
  if [[ -n "$(pid_on_port "$BACKEND_PORT")" ]]; then
    echo "后端已在 :${BACKEND_PORT} 运行"
    return 0
  fi
  echo "启动后端 :${BACKEND_PORT} (watchdog)"
  chmod +x "$ROOT/scripts/run-backend.sh"
  nohup "$ROOT/scripts/run-backend.sh" >>"$BACKEND_LOG" 2>&1 &
  sleep 2
  echo "  log: $BACKEND_LOG"
  echo "  health: $(http_code "http://127.0.0.1:${BACKEND_PORT}/api/health")"
}

start_frontend() {
  if [[ -n "$(pid_on_port "$FRONTEND_PORT")" ]]; then
    echo "前端已在 :${FRONTEND_PORT} 运行 (mode=${FRONTEND_MODE})"
    return 0
  fi
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    echo "  安装前端依赖 npm install ..."
    npm install
  fi
  if [[ "$FRONTEND_MODE" == "prod" ]]; then
    echo "启动前端 :${FRONTEND_PORT} (生产静态预览)"
    ensure_frontend_build
    nohup npm run preview -- --host 0.0.0.0 --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
  else
    echo "启动前端 :${FRONTEND_PORT} (开发 HMR)"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
  fi
  sleep 2
  echo "  log: $FRONTEND_LOG"
  echo "  http: $(http_code "http://127.0.0.1:${FRONTEND_PORT}/")"
  echo "  shell: $(frontend_shell_ok)"
}

cmd_start() {
  echo "=== 启动猛犸智能体 ==="
  echo "代码: $ROOT"
  echo "前端模式: ${FRONTEND_MODE} (MAMMOTH_FRONTEND_MODE=dev|prod)"
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

cmd_build() {
  echo "=== 构建前端 (production) ==="
  cd "$FRONTEND_DIR"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build
  echo "输出: $FRONTEND_DIR/dist"
  echo "启动生产前端: MAMMOTH_FRONTEND_MODE=prod $0 start"
}

cmd_status() {
  echo "=== 猛犸服务状态 ==="
  local bp fp shell health sessions skills deep summary
  bp="$(pid_on_port "$BACKEND_PORT")"
  fp="$(pid_on_port "$FRONTEND_PORT")"
  echo "代码目录: $ROOT"
  echo "前端模式: ${FRONTEND_MODE}"
  echo "后端 :${BACKEND_PORT}  pid=${bp:-无}"
  echo "前端 :${FRONTEND_PORT}  pid=${fp:-无}"
  echo ""
  echo "探针:"
  health="$(http_probe "http://127.0.0.1:${BACKEND_PORT}/api/health" 3)"
  sessions="$(http_probe "http://127.0.0.1:${FRONTEND_PORT}/api/sessions" 10)"
  skills="$(http_probe "http://127.0.0.1:${FRONTEND_PORT}/api/skills" 10)"
  format_probe "/api/health (fast)" "$health" 1
  format_probe "/api/sessions (via vite)" "$sessions" 3
  format_probe "/api/skills (via vite)" "$skills" 3
  deep="$(http_probe "http://127.0.0.1:${BACKEND_PORT}/api/health/deep" 5)"
  format_probe "/api/health/deep" "$deep" 4
  shell="$(frontend_shell_ok)"
  echo "  前端 HTML shell: ${shell}"
  echo ""
  summary="OK"
  if [[ -z "$bp" || -z "$fp" ]]; then summary="DOWN"; fi
  if [[ "$shell" != "ok" ]]; then summary="DEGRADED"; fi
  if [[ "$(echo "$health" | cut -d'|' -f1)" != "200" ]]; then summary="DEGRADED"; fi
  if [[ "$(echo "$sessions" | cut -d'|' -f1)" != "200" ]]; then summary="DEGRADED"; fi
  echo "综合: ${summary}"
  echo "  (index.html 200 只代表 Vite 在响应；sessions/skills 才反映页面能否正常加载数据)"
  if [[ -f "$BACKEND_LOG" ]]; then
    echo ""
    echo "后端日志尾:"
    tail -n 5 "$BACKEND_LOG" | sed 's/^/  /'
  fi
  if [[ -f "$FRONTEND_LOG" ]]; then
    echo "前端日志尾:"
    tail -n 3 "$FRONTEND_LOG" | sed 's/^/  /'
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
  echo "猛犸 deep health :${BACKEND_PORT}   $(http_code "http://127.0.0.1:${BACKEND_PORT}/api/health/deep")"
  echo "猛犸 Frontend    :${FRONTEND_PORT}   http=$(http_code "http://127.0.0.1:${FRONTEND_PORT}/")  shell=$(frontend_shell_ok)"
  echo "数字人 BEDH      :5173   https=$(curl -sk -o /dev/null -w '%{http_code}' --connect-timeout 3 https://127.0.0.1:5173/ 2>/dev/null || echo 000)  fay=$(http_code http://127.0.0.1:5000/)"
  echo "DOE 实验设计     :5173@116  http=$(http_code http://192.168.9.116:5173/)"
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
  echo "  猛犸:     $ROOT/scripts/service.sh {start|stop|restart|status|build}"
  echo "  数字人:   $ROOT/scripts/bedh-service.sh {start|stop|restart|status}"
  echo "  DOE:      $ROOT/scripts/doe-service.sh {install|start|stop|restart|status|fix-frontend}"
  echo "  生产前端: MAMMOTH_FRONTEND_MODE=prod $ROOT/scripts/service.sh start"
  echo "  详情:     $ROOT/docs/DEPLOY.md"
}

usage() {
  cat <<EOF
用法: $0 {start|stop|restart|status|deps|build}

  start     启动猛犸前端+后端（后台）
  stop      停止猛犸前端+后端
  restart   重启
  status    查看进程、API 延迟与前端 shell 是否可用
  deps      检查 OpenClaw / DB / 模型等依赖与 Agent 列表
  build     构建前端 production 静态包 (frontend/dist)

环境变量（可选）:
  MAMMOTH_BACKEND_PORT    默认 8080
  MAMMOTH_FRONTEND_PORT   默认 5174
  MAMMOTH_FRONTEND_MODE   dev（默认，HMR）| prod（build + vite preview）
  MAMMOTH_BACKEND_LOG     默认 /tmp/mammoth-backend.log
  MAMMOTH_FRONTEND_LOG    默认 /tmp/mammoth-frontend.log
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
    build) cmd_build ;;
    -h|--help|help) usage ;;
    "") usage; exit 1 ;;
    *) echo "未知命令: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
