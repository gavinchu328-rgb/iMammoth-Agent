# 猛犸智能体 · 部署与运维

> 代码根目录：`/data2/mammoth-agent`  
> 文档版本：2026-07-23

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
浏览器 :5174
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
| 猛犸前端 | 5174 | 本仓库 `scripts/service.sh` |
| 猛犸后端 | 8080 | 本仓库 `scripts/service.sh` |
| PostgreSQL | 5434 | Docker 容器 `postgres` |
| OpenClaw Gateway | 18789 | systemd user：`openclaw-gateway.service` |
| Qwen 推理 | 8006 | 机房模型服务（外部） |
| AI4Drug MCP | 8000 | `/data2/AI4Drug`（外部，可选） |

---

## 3. 一键启停（猛犸自身）

```bash
cd /data2/mammoth-agent

# 启动前后端（后台，默认开发模式 HMR）
./scripts/service.sh start

# 生产模式：先 build，再用 vite preview 提供静态页（无 HMR）
./scripts/service.sh build
MAMMOTH_FRONTEND_MODE=prod ./scripts/service.sh start

# 查看状态（含 API 延迟、前端 shell 是否可用）
./scripts/service.sh status

# 重启 / 停止
./scripts/service.sh restart
./scripts/service.sh stop

# 依赖健康检查（OpenClaw / DB / 模型等）
./scripts/service.sh deps
```

访问：

- 前端：http://\<host\>:5174
- 后端健康（轻量）：http://\<host\>:8080/api/health
- 后端深度探针：http://\<host\>:8080/api/health/deep

### 3.0 浏览器「不安全」与 localhost 转发

| 访问方式 | 浏览器显示 | 说明 |
|----------|------------|------|
| `http://localhost:5174`（SSH / Cursor 端口转发） | 通常可用 | **localhost 属于安全上下文**，流式对话等功能正常 |
| `http://192.168.x.x:5174`（直连局域网 IP） | 「不安全」 | 纯 HTTP 非安全上下文，旧版前端可能因 `crypto.randomUUID()` 失败导致发送按钮一直转圈 |

**推荐用法（开发）：**

1. 用 Cursor / SSH 把服务器 `5174` 转发到本机，浏览器打开 `http://localhost:5174`。
2. 或刷新到已修复的前端（`newId` 兼容非安全上下文），直连 `http://192.168.11.209:5174` 也可正常发送。

**若需局域网直连且地址栏显示安全（HTTPS）：**

在内网用反向代理终止 TLS，例如 Caddy（自签证书，内网够用）：

```bash
# 示例：/etc/caddy/Caddyfile
192.168.11.209 {
    tls internal
    reverse_proxy /api/* 127.0.0.1:8080
    reverse_proxy /* 127.0.0.1:5174
}
```

或使用 `mkcert` 为内网 IP 签发受信任证书后配置 Nginx/Caddy。有公网域名时可用 Let's Encrypt。

日志：

- 后端：`/tmp/mammoth-backend.log`
- 前端：`/tmp/mammoth-frontend.log`

兼容旧入口：`./start.sh`（前台同时起前后端，Ctrl+C 停止）。

### 3.1 开发 vs 生产前端

| 模式 | 环境变量 | 命令 | 说明 |
|------|----------|------|------|
| **开发**（默认） | `MAMMOTH_FRONTEND_MODE=dev` | `npm run dev` | 热更新 HMR，改代码方便；偶发白屏属正常现象 |
| **生产** | `MAMMOTH_FRONTEND_MODE=prod` | `npm run build` + `vite preview` | 静态构建，稳定，适合长期对外提供 |

```bash
# 仅构建
./scripts/service.sh build

# 以生产模式启动（会自动 build，源码有变更时重建）
MAMMOTH_FRONTEND_MODE=prod ./scripts/service.sh restart
```

### 3.2 运维脚本一览

| 脚本 | 作用 | 典型命令 |
|------|------|----------|
| `scripts/service.sh` | 猛犸前后端、deps 探针 | `start` / `status` / `deps` |
| `scripts/bedh-service.sh` | 数字人智能体（本机 BEDH） | `start` / `status` |
| `scripts/doe-service.sh` | DOE 实验设计（SSH 到 116） | `install` / `status` / `fix-frontend` |
| `scripts/doe-remote-service.sh` | DOE 在 116 本机执行（由 install 同步） | — |
| `scripts/test_ai4drug_process_display.py` | AI4Drug 技能过程展示回归 | 手动跑单技能 |

**近期行为说明（2026-07-23）：**

- 刷新 `/c/:sessionId` 时，`loadSession` 不再阻塞于过程日志 tail；消息先展示，流式恢复在后台进行。
- 模型若把折叠模板写进「最终回答」，前后端会从工具步骤合成 ADMET 表格等可读结果（`reply_rebuild` / `parseProcessLog`）。
- MCP / 流式超时统一为 10 分钟（`mcp_tool_timeout_ms=600000`）；分子设计按分子数延长预算。
- DOE 前端须监听 `0.0.0.0:5173`；仅 `127.0.0.1` 时智能体广场 iframe 会 connection refused，用 `doe-service.sh fix-frontend` 修复。

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

**开发模式（默认）**

```bash
cd /data2/mammoth-agent/frontend
npm install          # 首次
nohup npm run dev -- --host 0.0.0.0 --port 5174 > /tmp/mammoth-frontend.log 2>&1 &
```

**生产模式**

```bash
cd /data2/mammoth-agent/frontend
npm install
npm run build
nohup npm run preview -- --host 0.0.0.0 --port 5174 > /tmp/mammoth-frontend.log 2>&1 &
```

Vite 已把 `/api` 代理到 `127.0.0.1:8080`（dev 与 preview 均生效）。

### 4.4 技能广场与 OpenClaw Skill 映射

技能广场数据来自 `skills/skills.yaml`，由后端 `GET /api/skills` 提供。点击卡片会将 `example` 填入对话并附带技能提示，由 OpenClaw 调度对应 skill。

| 广场名称 | skills.yaml `id` | OpenClaw Skill 路径 |
|----------|------------------|---------------------|
| 化学计算 | `chemistry-calculation` | `~/.openclaw/workspace/skills/chemistry-calculation/` |
| **化学智能中心** | `chemical_reaction` | `~/.openclaw/workspace/skills/chemical_reaction/SKILL.md` |
| 智能实验设计 | `exp_design` | workspace skills（同名目录） |

**化学智能中心**（`chemical_reaction`）对接 huaxue Nest `:3010` AI 中心，覆盖性质预测、虚拟筛选、分子生成、反应预测、逆合成、催化剂预测等；代码根目录 `/data1/huaxue`。

新增技能：在 `skills/skills.yaml` 增加条目（`id` 建议与 OpenClaw skill 名一致），确保 OpenClaw workspace 中已安装对应 `SKILL.md`，刷新前端即可在 `/skills` 看到。

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

### 5.0 智能体广场（外链服务）

智能体广场（`/agents`）除 OpenClaw 对话外，还嵌入独立部署的外部 Web 应用（iframe）。配置见 `frontend/src/pages/AgentsPage.tsx` 与 `AgentDetailPage.tsx`。

| 展示名称 | ID | 前端地址 | 代码位置 | 宿主机 |
|----------|-----|----------|----------|--------|
| 药物研发智能体 | `ai4drug` | http://192.168.11.209:8888/ai4drug-pipeline.html | （现网 AI4Drug 管线页） | 192.168.11.209 |
| 物质科学智能体 | `huaxue` | http://192.168.11.209:3011/ | `/data1/huaxue` 等 | 192.168.11.209 |
| 领域学习智能体 | `domainlearning` | 广场内 `/domainlearning-embed.html`（经猛犸代理）；直连 `http://192.168.11.209:8866/` | `/data1/Domainlearning` | 192.168.11.209 |
| **DOE 实验设计智能体** | `doe` | http://192.168.9.116:5173/ | `/home/admin/AIProject/DOEAgent` | **192.168.9.116** |
| **数字人智能体** | `bedh` | https://192.168.11.209:5173/ | `/data1/BEDH`（Fay + XmovLiteAvatarJSDemo） | **192.168.11.209** |

**DOE 实验设计智能体**（Design of Experiments）提供 DOE+ 贝叶斯优化：创建实验、多轮条件建议、结果记录与可视化。技术栈为 FastAPI + SQLite 后端、React 前端。

**数字人智能体**（BEDH）基于 Fay 对话后端与星云数字人 SDK 前端，支持语音唤醒、实时播报与大屏展示（`/screen/index.html`）。前端 Vite 开发服务默认 **HTTPS :5173**（自签名证书）；Fay HTTP API **:5000**，WebSocket **:10002 / :10003**。

```bash
# 健康检查
curl -sk -o /dev/null -w '%{http_code}\n' https://192.168.11.209:5173/
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.11.209:5000/

# 启停（猛犸仓库封装脚本，推荐）
/data2/mammoth-agent/scripts/bedh-service.sh status
/data2/mammoth-agent/scripts/bedh-service.sh start
/data2/mammoth-agent/scripts/bedh-service.sh stop
/data2/mammoth-agent/scripts/bedh-service.sh restart

# 或直接在 BEDH 目录（详见 /data1/BEDH/README.txt）
cd /data1/BEDH
bash deploy/scripts/start_fay.sh
cd XmovLiteAvatarJSDemo && npm run dev -- --host 0.0.0.0 --port 5173

# 后台常驻日志
tail -f /data1/BEDH/deploy/logs/fay.nohup.log
tail -f /data1/BEDH/deploy/logs/frontend.nohup.log
ss -ltnp | rg '5000|10002|10003|5173'
```

| 组件 | 端口 | 说明 |
|------|------|------|
| Xmov 前端 | 5173 | HTTPS，智能体广场 iframe 入口 |
| Fay HTTP | 5000 | 对话 / ASR / TTS API |
| Fay 数字人 WS | 10002 | 数字人链路 |
| Fay 面板 WS | 10003 | 前端 WebSocket |
| Conda 环境 | — | `/data1/Xmo` |
| 配置主文件 | — | `Fay/system.conf`、`XmovLiteAvatarJSDemo/public/xmov_config.json` |
| 完整文档 | — | `/data1/BEDH/README.txt` |

```bash
# DOE 健康检查（从猛犸宿主机或同网段）
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.9.116:5173/

# 启停（猛犸仓库封装脚本，经 SSH 管理 116 宿主机，推荐）
/data2/mammoth-agent/scripts/doe-service.sh install    # 首次：同步远程启停脚本
/data2/mammoth-agent/scripts/doe-service.sh status
/data2/mammoth-agent/scripts/doe-service.sh start
/data2/mammoth-agent/scripts/doe-service.sh restart
/data2/mammoth-agent/scripts/doe-service.sh fix-frontend   # 前端只绑 127.0.0.1 时用

# 认证：优先 ssh-copy-id；或临时 DOE_SSH_PASSWORD='…'（勿写入仓库，经 doe-ssh-runner.py 传递）
# 环境变量：DOE_SSH_HOST DOE_SSH_USER DOE_SSH_KEY DOE_ROOT

# 或 SSH 登录宿主机后本地维护
ssh admin@192.168.9.116
bash /home/admin/AIProject/DOEAgent/scripts/mammoth-doe-service.sh status
```

接入新外链智能体：在 `AgentsPage.tsx` 增加卡片，在 `AgentDetailPage.tsx` 的 `AGENTS` 增加同名 `id`，并更新本表。

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

`openclaw.json` 中 `mcp.servers.ai4drug` 建议设置 `requestTimeoutMs: 300000`（默认 60s 会导致靶点发现等长任务超时 `-32001`）。

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

### 6.5 物质科学数据（huixiang_db）

| 数据 | 路径 | 检索方式 |
|------|------|----------|
| **化学反应库** | `/data1/huixiang_db/unified_reactions.duckdb` | 数据广场 `unified-reactions-duckdb`；或 `reaction-db-api` `:9306` |
| 分子参考库 | `/data1/huixiang_db/molecules.duckdb` | 数据广场登记（部分表待接入 Web 检索） |
| DFT 描述符 | `/data1/huixiang_db/descriptors.csv` | 数据广场 `dft-descriptors-csv` |

```bash
# 反应检索 API（读取 unified_reactions.duckdb）
curl -s 'http://127.0.0.1:9306/api/rxn/search?keyword=aspirin&pageSize=3'

# 猛犸数据广场代理
curl -s -X POST http://127.0.0.1:8080/api/databases/unified-reactions-duckdb/search \
  -H 'Content-Type: application/json' -d '{"query":"aspirin"}'
```

---

## 7. 健康检查清单

```bash
./scripts/service.sh status    # 推荐：含 /api/sessions 延迟与前端 shell
./scripts/service.sh deps

# 轻量（不打 OpenClaw LLM，毫秒级）
curl -s http://127.0.0.1:8080/api/health

# 深度（含 OpenClaw gateway / DB）
curl -s http://127.0.0.1:8080/api/health/deep
```

| 检查项 | 期望 |
|--------|------|
| 前端 5174 `/` | HTTP 200，且 HTML 含 `id="root"` |
| `/api/sessions`（经 5174 代理） | HTTP 200，通常 < 3s |
| 后端 `/api/health` | `status=ok`，`database=true`（快速） |
| 后端 `/api/health/deep` | 另含 `openclaw=true` |
| OpenClaw 18789 | 可连 |
| Postgres 5434 | 可连 |
| Qwen 8006 | `/v1/models` 可访问 |

> **注意**：仅 `curl :5174/` 返回 200 不代表页面可用；若 `/api/sessions` 超时或前端 shell 异常，浏览器仍会白屏或一直加载。

---

## 8. 相关文档

| 文档 | 内容 |
|------|------|
| `docs/DESIGN.md` | 产品设计 |
| `docs/process_log_spec.md` | 模型输出「分析过程」Markdown 规范 |
| `docs/process_log_protocol.md` | 过程日志文件协议（含结束标签） |
| `docs/process_ui_template.md` | 过程 UI / 参数·输出模板说明 |
| `README.md` | 快速入口 |
