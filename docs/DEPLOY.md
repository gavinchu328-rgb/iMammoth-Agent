# 猛犸智能体 · 部署与运维

> 代码根目录：`/data2/mammoth-agent`  
> 文档版本：2026-07-20

---

## 1. 代码在哪

| 路径 | 说明 |
|------|------|
| `/data2/mammoth-agent/` | 本仓库根目录（Git） |
| `backend/` | FastAPI 后端（对话流式、会话落库、过程日志） |
| `frontend/` | React + Vite 前端 |
| `skills/skills.yaml` | 技能广场目录 |
| `data/databases.yaml` | 数据广场目录 |
| `docs/` | 设计 / 过程日志协议 / 本部署文档 |
| `process_logs/{YYYY-MM-DD}/` | **猛犸自写**的过程日志（非 OpenClaw 目录） |
| `scripts/` | 运维脚本、技能测试脚本 |

相关但不在本仓库内的依赖代码：

| 路径 / 服务 | 说明 |
|-------------|------|
| `/home/dbcloud/.openclaw/` | OpenClaw 配置、workspace、sessions |
| `/home/dbcloud/.openclaw/openclaw.json` | Agent 列表、模型、MCP 等 |
| `/home/dbcloud/.npm-global/lib/node_modules/openclaw/` | OpenClaw 运行时 |
| `/data2/AI4Drug/` | AI4Drug MCP / 药物管线（可选能力） |
| `/data1/huaxue/bin/chemistry-calc` | 化学计算 CLI（技能常用） |
| `http://127.0.0.1:8006` | 本地 Qwen 推理（OpenClaw 主模型 + 思考翻译） |

---

## 2. 架构与端口

```
浏览器 :5173
   │  /api 代理
   ▼
猛犸 Backend :8080  ──► PostgreSQL :5434 (库 mammoth_agent)
   │
   ├─► OpenClaw Gateway :18789  (agent=main)
   │         │
   │         ├─► 本地模型 :8006 (Qwen3.6-35B-A3B)
   │         ├─► AI4Drug MCP :8000（可选）
   │         └─► sessions: ~/.openclaw/agents/main/sessions/
   │
   └─► process_logs/{日期}/{session_id}.jsonl   （猛犸整理后的过程日志）
```

| 服务 | 端口 | 谁维护 |
|------|------|--------|
| 猛犸前端 | 5173 | 本仓库 `scripts/service.sh` |
| 猛犸后端 | 8080 | 本仓库 `scripts/service.sh` |
| PostgreSQL | 5434 | Docker 容器 `postgres` |
| OpenClaw Gateway | 18789 | systemd user：`openclaw-gateway.service` |
| Qwen 推理 | 8006 | 机房模型服务（外部） |
| AI4Drug MCP | 8000 | `/data2/AI4Drug`（外部，可选） |

---

## 3. 一键启停（猛犸自身）

```bash
cd /data2/mammoth-agent

# 启动前后端（后台）
./scripts/service.sh start

# 查看状态
./scripts/service.sh status

# 重启 / 停止
./scripts/service.sh restart
./scripts/service.sh stop

# 依赖健康检查（OpenClaw / DB / 模型等）
./scripts/service.sh deps
```

访问：

- 前端：http://\<host\>:5173
- 后端健康：http://\<host\>:8080/api/health

日志：

- 后端：`/tmp/mammoth-backend.log`
- 前端：`/tmp/mammoth-frontend.log`

兼容旧入口：`./start.sh`（前台同时起前后端，Ctrl+C 停止）。

---

## 4. 手动启动细节

### 4.1 数据库（首次）

```bash
# 确认 5434 上的 postgres 容器在跑
docker ps | grep 5434

cd /data2/mammoth-agent/backend
python init_db.py
```

库名：`mammoth_agent`（用户/密码默认见 `backend/config.py` 或 `backend/.env`）。

### 4.2 后端

```bash
cd /data2/mammoth-agent/backend
# 建议使用已装好依赖的 Python（需 fastapi/uvicorn/httpx/asyncpg 等）
pip install -r requirements.txt   # 首次
nohup uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/mammoth-backend.log 2>&1 &
```

### 4.3 前端

```bash
cd /data2/mammoth-agent/frontend
npm install          # 首次
nohup npm run dev -- --host 0.0.0.0 --port 5173 > /tmp/mammoth-frontend.log 2>&1 &
```

Vite 已把 `/api` 代理到 `127.0.0.1:8080`。

---

## 5. 涉及的智能体（OpenClaw）及维护

猛犸默认调用 OpenClaw **`main`** agent（`x-openclaw-agent-id: main`，`model: openclaw:main`）。

配置文件：`/home/dbcloud/.openclaw/openclaw.json`  
Workspace：`/home/dbcloud/.openclaw/workspace/`（含 `AGENTS.md` / `SOUL.md` / skills）

当前已配置的 Agent：

| Agent ID | Workspace | 典型用途 |
|----------|-----------|----------|
| **main** | `~/.openclaw/workspace` | 猛犸默认对话入口 |
| researcher | `workspace-researcher` | 研究检索 |
| coder | `workspace-coder` | 编码 |
| analyst | `workspace-analyst` | 分析 |
| creative | `workspace-creative` | 创意 / 文献产出 |
| design-agent | `workspace-design` | 设计 |
| arxiv | `workspace-arxiv` | arXiv |
| ai4drug | `workspace-ai4drug` | 药物发现管线 |
| monitor | `workspace-monitor` | 监控 |
| intern-s2-preview | `workspace-intern-s2-preview` | Intern-S2 模型 |
| domainlearning | `workspace-domainlearning` | Domainlearning MCP |

### 5.1 OpenClaw Gateway 启停

使用 **systemd --user**（推荐）：

```bash
# 状态
systemctl --user status openclaw-gateway

# 启动 / 重启 / 停止
systemctl --user start openclaw-gateway
systemctl --user restart openclaw-gateway
systemctl --user stop openclaw-gateway

# 开机自启（已一般启用）
systemctl --user enable openclaw-gateway

# 日志
journalctl --user -u openclaw-gateway -f
```

Unit 文件：`~/.config/systemd/user/openclaw-gateway.service`  
实际命令大致为：

```text
node .../openclaw/dist/index.js gateway --port 18789
```

注意：Node 版本需满足 OpenClaw 要求（当前环境常用 nvm 的 v24.18.0）。

### 5.2 会话与过程日志分工

| 日志 | 路径 | 谁写 |
|------|------|------|
| OpenClaw 原始会话 | `~/.openclaw/agents/main/sessions/*.jsonl` | OpenClaw |
| 猛犸过程日志 | `/data2/mammoth-agent/process_logs/{YYYY-MM-DD}/{session_id}.jsonl` | 猛犸后端 |

过程日志协议见：`docs/process_log_protocol.md`。

---

## 6. 其它外部依赖维护

### 6.1 PostgreSQL (:5434)

```bash
docker ps | grep 5434
# 容器名一般为 postgres；按你们现有 compose/运维方式启停
```

### 6.2 本地 Qwen (:8006)

OpenClaw 主模型与「英文思考→中文」翻译都依赖此服务。  
不可用时：对话可能失败或思考保留英文。

```bash
curl -s http://127.0.0.1:8006/v1/models | head
```

### 6.3 AI4Drug MCP (:8000)

可选。药物相关技能走此 MCP：

```bash
# 示例（以现网为准）
cd /data2/AI4Drug
# 常见：uvicorn ai4drug.mcp.server:app --host 0.0.0.0 --port 8000
curl -s http://127.0.0.1:8000/health || curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/
```

### 6.4 chemistry-calc

```bash
/data1/huaxue/bin/chemistry-calc --help
```

---

## 7. 健康检查清单

```bash
./scripts/service.sh status
./scripts/service.sh deps

curl -s http://127.0.0.1:8080/api/health
# 期望含 "openclaw": true, "database": true
```

| 检查项 | 期望 |
|--------|------|
| 前端 5173 | HTTP 200 |
| 后端 8080 `/api/health` | `status=ok`，openclaw/database 为 true |
| OpenClaw 18789 | 可连 |
| Postgres 5434 | 可连 |
| Qwen 8006 | `/v1/models` 可访问 |

---

## 8. 相关文档

| 文档 | 内容 |
|------|------|
| `docs/DESIGN.md` | 产品设计 |
| `docs/process_log_spec.md` | 模型输出「分析过程」Markdown 规范 |
| `docs/process_log_protocol.md` | 过程日志文件协议（含结束标签） |
| `docs/process_ui_template.md` | 过程 UI / 参数·输出模板说明 |
| `README.md` | 快速入口 |
