#!/bin/bash
# 前台开发启动（Ctrl+C 同时停前后端）。生产/日常后台请用 scripts/service.sh
set -e
cd "$(dirname "$0")"

echo "提示: 日常运维请用 ./scripts/service.sh {start|status|deps}"
echo "文档: docs/DEPLOY.md"
echo ""

echo "=== 初始化数据库（如已初始化可忽略报错）==="
(cd backend && python init_db.py) || true

echo "=== 启动后端 (8080) ==="
(cd backend && uvicorn main:app --host 0.0.0.0 --port 8080 --reload) &
BACKEND_PID=$!

echo "=== 启动前端 (5174) ==="
(cd frontend && npm run dev -- --host 0.0.0.0 --port 5174) &
FRONTEND_PID=$!

echo ""
echo "猛犸智能体已启动:"
echo "  前端: http://localhost:5174"
echo "  后端: http://localhost:8080"
echo "  数据库: mammoth_agent @ localhost:5434"
echo ""
echo "按 Ctrl+C 停止"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
