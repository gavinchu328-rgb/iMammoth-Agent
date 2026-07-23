# 猛犸智能体

本地科研 AI 对话应用：前端 + FastAPI 后端，对接 OpenClaw，会话落库 PostgreSQL。

## 代码位置

```text
/data2/mammoth-agent
```

## 快速启停

```bash
cd /data2/mammoth-agent
./scripts/service.sh start     # 后台启动前后端（开发模式）
./scripts/service.sh status    # 状态（含 API 延迟）
./scripts/service.sh deps      # OpenClaw / DB / 模型 / Agent 列表
./scripts/service.sh build     # 构建生产前端
MAMMOTH_FRONTEND_MODE=prod ./scripts/service.sh start  # 生产模式（无 HMR）
./scripts/service.sh restart
./scripts/service.sh stop
```

- 前端：http://localhost:5174
- 后端：http://localhost:8080/api/health（轻量）/ `/api/health/deep`（含 OpenClaw）
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
├── scripts/
│   ├── service.sh           # 猛犸前后端启停
│   ├── bedh-service.sh      # 数字人智能体（本机 /data1/BEDH）
│   ├── doe-service.sh       # DOE 实验设计（SSH 到 192.168.9.116）
│   └── test_*.py            # 技能 / 流式 / 过程展示测试
└── start.sh           # 前台一键启动（开发用）
```

### 外链智能体维护

```bash
./scripts/service.sh deps          # 含猛犸 / BEDH / DOE 探针
./scripts/bedh-service.sh status   # 数字人（本机）
./scripts/doe-service.sh install   # 首次同步远程脚本
./scripts/doe-service.sh status    # DOE（116 宿主机）
```

## 依赖一览（摘要）

| 服务 | 端口 | 维护 |
|------|------|------|
| 猛犸前端/后端 | 5174 / 8080 | `./scripts/service.sh` |
| OpenClaw Gateway | 18789 | `systemctl --user … openclaw-gateway` |
| PostgreSQL | 5434 | Docker `postgres` |
| Qwen 推理 | 8006 | 外部模型服务 |
| AI4Drug MCP | 8000 | `/data2/AI4Drug`（可选） |
| DOE 实验设计智能体 | 5173 @ 192.168.9.116 | `./scripts/doe-service.sh`（SSH 到 116） |
| 数字人智能体 BEDH | 5173 @ 192.168.11.209 | `/data1/BEDH`（`scripts/bedh-service.sh`） |
