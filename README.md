# 猛犸智能体

本地科研 AI 对话应用：前端 + FastAPI 后端，对接 OpenClaw，会话落库 PostgreSQL。

## 代码位置

```text
/data2/mammoth-agent
```

## 快速启停

```bash
cd /data2/mammoth-agent
./scripts/service.sh start     # 后台启动前后端
./scripts/service.sh status    # 状态
./scripts/service.sh deps      # OpenClaw / DB / 模型 / Agent 列表
./scripts/service.sh restart
./scripts/service.sh stop
```

- 前端：http://localhost:5173
- 后端：http://localhost:8080/api/health
- 过程日志：`process_logs/{YYYY-MM-DD}/{session_id}.jsonl`（猛犸自写）

完整部署、依赖智能体与维护方式见：**[docs/DEPLOY.md](docs/DEPLOY.md)**。

## 其它文档

| 文档 | 说明 |
|------|------|
| [docs/DEPLOY.md](docs/DEPLOY.md) | 部署 / 端口 / OpenClaw Agent 维护 |
| [docs/DESIGN.md](docs/DESIGN.md) | 产品设计 |
| [docs/process_log_protocol.md](docs/process_log_protocol.md) | 过程日志文件协议 |
| [docs/process_log_spec.md](docs/process_log_spec.md) | 模型输出规范 |
| [docs/process_ui_template.md](docs/process_ui_template.md) | 过程 UI 模板 |

## 项目结构

```text
mammoth-agent/
├── backend/           # FastAPI
├── frontend/          # React + Vite
├── skills/            # 技能广场 YAML
├── data/              # 数据广场 YAML
├── process_logs/      # 按日过程日志
├── docs/              # 设计与部署文档
├── scripts/service.sh # 服务启停脚本
└── start.sh           # 前台一键启动（开发用）
```

## 依赖一览（摘要）

| 服务 | 端口 | 维护 |
|------|------|------|
| 猛犸前端/后端 | 5173 / 8080 | `./scripts/service.sh` |
| OpenClaw Gateway | 18789 | `systemctl --user … openclaw-gateway` |
| PostgreSQL | 5434 | Docker `postgres` |
| Qwen 推理 | 8006 | 外部模型服务 |
| AI4Drug MCP | 8000 | `/data2/AI4Drug`（可选） |
