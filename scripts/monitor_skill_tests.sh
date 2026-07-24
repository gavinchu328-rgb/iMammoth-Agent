#!/usr/bin/env bash
# Monitor AI4Drug skill test sessions; append status to /tmp/skill_test_monitor.log
set -uo pipefail
LOG=/tmp/skill_test_monitor.log
BASE=http://127.0.0.1:8080

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

check_sid() {
  local name="$1" sid="$2"
  python3 - "$name" "$sid" <<'PY'
import json, sys, urllib.request
name, sid = sys.argv[1], sys.argv[2]
noise = ['Command still running', 'center_x =', 'AutoDock Vina', '<tool_call>', '执行命令']
try:
    with urllib.request.urlopen(f'http://127.0.0.1:8080/api/sessions/{sid}/process-log', timeout=20) as r:
        proc = json.load(r)
    with urllib.request.urlopen(f'http://127.0.0.1:8080/api/sessions/{sid}', timeout=20) as r:
        data = json.load(r)
except Exception as e:
    print(f'STALL {name} {sid[:8]} err={e}')
    raise SystemExit(0)
reply = [m['content'] for m in data.get('messages', []) if m.get('role') == 'assistant']
reply = reply[-1] if reply else ''
tools = [s for s in proc.get('steps', []) if s.get('kind') in ('tool', 'skill', 'web')]
running = [s.get('title') for s in tools if s.get('status') == 'running']
issues = []
if running:
    issues.append('running:' + ','.join(running[:3]))
if len(reply) < 80 and not running:
    issues.append('short_reply')
for p in noise:
    if p.lower() in reply.lower():
        issues.append('noise:' + p[:20])
if '## 最终回答' not in reply and not running:
    issues.append('no_final')
status = 'OK' if not issues else 'ISSUE'
print(f'{status} {name} {sid[:8]} tools={len(tools)} run={len(running)} reply={len(reply)} {";".join(issues)}')
PY
}

log "=== monitor start ==="
# Known sessions from test runs
declare -A SESSIONS=(
  ["靶点发现"]="a0fe3c9a-ef59-4d50-8b15-6ae77f711069"
  ["配体准备"]="cef47d7d-adb3-4764-9296-e54e868e5ff7"
  ["分子对接"]="ec258587-1237-4c16-992b-af4789479fcb"
  ["ADMET评估"]="8cbeb26d-586b-4a60-b332-fadb846b8a9c"
  ["对接盒配置"]="e07af039-3bc8-489b-beeb-36caef3e9246"
)

for round in $(seq 1 30); do
  log "--- round $round ---"
  for name in "${!SESSIONS[@]}"; do
    check_sid "$name" "${SESSIONS[$name]}" | tee -a "$LOG" || true
  done
  # Pick up newest sessions for molecule design / retrosynthesis if present
  python3 - <<'PY' | while read -r line; do log "$line"; done
import json, urllib.request
sessions = json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/sessions', timeout=20))
for key, pats in [
    ('分子设计', ['候选小分子', '设计 3', '设计 5']),
    ('逆合成分析', ['怎么合成', '分析一下吉非替尼']),
]:
    for s in sessions[:15]:
        t = s.get('title') or ''
        if any(p in t for p in pats):
            print(f'NEW {key} {s["id"]} {t[:60]}')
            break
PY
  sleep 60
done
log "=== monitor end ==="
