#!/usr/bin/env bash
# DOE 实验设计智能体 — 从猛犸宿主机经 SSH 管理 192.168.9.116 上的 DOEAgent
# 远程实际逻辑见 scripts/doe-remote-service.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOE_SSH_HOST="${DOE_SSH_HOST:-192.168.9.116}"
DOE_SSH_USER="${DOE_SSH_USER:-admin}"
DOE_ROOT="${DOE_ROOT:-/home/admin/AIProject/DOEAgent}"
REMOTE_SCRIPT="${DOE_REMOTE_SCRIPT:-$DOE_ROOT/scripts/mammoth-doe-service.sh}"
LOCAL_REMOTE_SCRIPT="$ROOT/scripts/doe-remote-service.sh"
FRONTEND_URL="${DOE_FRONTEND_URL:-http://${DOE_SSH_HOST}:5173/}"

http_code() {
  curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 "$1" 2>/dev/null || echo "000"
}

ssh_opts() {
  local opts=(-o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=no)
  if [[ -n "${DOE_SSH_KEY:-}" ]]; then
    opts+=(-i "$DOE_SSH_KEY")
  fi
  printf '%s\n' "${opts[@]}"
}

run_ssh() {
  if [[ -n "${DOE_SSH_PASSWORD:-}" ]]; then
    python3 "$ROOT/scripts/doe-ssh-runner.py" exec "$*"
    return $?
  fi
  local -a opts
  mapfile -t opts < <(ssh_opts)
  ssh "${opts[@]}" "${DOE_SSH_USER}@${DOE_SSH_HOST}" "$@"
}

run_scp() {
  local src="$1" dst="$2"
  if [[ -n "${DOE_SSH_PASSWORD:-}" ]]; then
    python3 "$ROOT/scripts/doe-ssh-runner.py" scp "$src" "$dst"
    return $?
  fi
  local -a opts
  mapfile -t opts < <(ssh_opts)
  scp "${opts[@]}" "$src" "${DOE_SSH_USER}@${DOE_SSH_HOST}:$dst"
}

cmd_install() {
  echo "=== 同步远程启停脚本到 ${DOE_SSH_HOST} ==="
  run_ssh "mkdir -p $(dirname "$REMOTE_SCRIPT")"
  run_scp "$LOCAL_REMOTE_SCRIPT" "$REMOTE_SCRIPT"
  run_ssh "chmod +x '$REMOTE_SCRIPT'"
  echo "已安装: $REMOTE_SCRIPT"
}

cmd_remote() {
  local action="${1:-status}"
  if ! run_ssh "test -x '$REMOTE_SCRIPT'"; then
    echo "远程脚本不存在，正在 install ..."
    cmd_install
  fi
  run_ssh "DOE_ROOT='$DOE_ROOT' bash '$REMOTE_SCRIPT' '$action'"
}

cmd_status() {
  echo "=== DOE（从猛犸宿主机探测）==="
  echo "远程: ${DOE_SSH_USER}@${DOE_SSH_HOST}"
  echo "广场 URL: $FRONTEND_URL  http=$(http_code "$FRONTEND_URL")"
  echo ""
  cmd_remote status || true
}

cmd_start() { cmd_remote start; }
cmd_stop() { cmd_remote stop; }
cmd_restart() { cmd_remote restart; }
cmd_fix_frontend() { cmd_remote fix-frontend; }

usage() {
  cat <<EOF
用法: $0 {install|start|stop|restart|status|fix-frontend}

  经 SSH 管理 DOE 实验设计智能体（${DOE_SSH_HOST}）
  代码: ${DOE_ROOT}
  广场: ${FRONTEND_URL}

  install        同步 scripts/doe-remote-service.sh 到远程
  fix-frontend   仅重启前端并绑定 0.0.0.0（常见外网不可达修复）

环境变量:
  DOE_SSH_HOST      默认 192.168.9.116
  DOE_SSH_USER      默认 admin
  DOE_SSH_PASSWORD  可选；通过 doe-ssh-runner.py 传入（勿写入仓库；推荐 ssh-copy-id）
  DOE_SSH_KEY       可选 SSH 私钥路径
  DOE_ROOT          远程项目目录

示例:
  $0 status
  DOE_SSH_PASSWORD='***' $0 restart
  ssh-copy-id ${DOE_SSH_USER}@${DOE_SSH_HOST} && $0 start

详见: docs/DEPLOY.md §5.0
EOF
}

main() {
  case "${1:-}" in
    install) cmd_install ;;
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    fix-frontend) cmd_fix_frontend ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
