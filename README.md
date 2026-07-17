# 猛犸智能体

本地科研 AI 对话应用，对接 OpenClaw，数据持久化到 PostgreSQL。

## 快速启动

```bash
# 1. 确保 PostgreSQL 和 OpenClaw 已运行
# 2. 一键启动
./start.sh
```

- 前端：http://localhost:5173
- 后端：http://localhost:8080
- 数据库：`mammoth_agent` @ `localhost:5434`

## 手动启动

```bash
# 初始化数据库（首次）
cd backend && python init_db.py

# 后端
cd backend && uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 前端
cd frontend && npm run dev
```

## 数据库

使用独立库 `mammoth_agent`（与 `oakclaw` 主库分离）：

| 表 | 说明 |
|----|------|
| `sessions` | 对话会话（id, title, created_at, updated_at） |
| `messages` | 消息记录（id, session_id, role, content, token 统计） |

```bash
# 初始化
cd backend && python init_db.py
```

## 环境变量

见 `backend/.env`：

```
OPENCLAW_BASE_URL=http://127.0.0.1:18789
OPENCLAW_API_KEY=...
DB_HOST=127.0.0.1
DB_PORT=5434
DB_NAME=mammoth_agent
```

## 项目结构

```
mammoth-agent/
├── huixiang.png          # Logo
├── skills/skills.yaml    # 15 个技能定义
├── backend/              # FastAPI 后端
├── frontend/             # React 前端
├── docs/DESIGN.md        # 设计文档
└── start.sh              # 启动脚本
```
