#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== 初始化数据库 ==="
cd backend && python init_db.py && cd ..

echo "=== 启动后端 (8080) ==="
cd backend && uvicorn main:app --host 0.0.0.0 --port 8080 --reload &
BACKEND_PID=$!

echo "=== 启动前端 (5173) ==="
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "猛犸智能体已启动:"
echo "  前端: http://localhost:5173"
echo "  后端: http://localhost:8080"
echo "  数据库: mammoth_agent @ localhost:5434"
echo ""
echo "按 Ctrl+C 停止"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
