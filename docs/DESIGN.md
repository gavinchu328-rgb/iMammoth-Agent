# 猛犸智能体 — 产品设计方案

> 版本：v0.4  
> 视觉参考：飞书「慧星实验室」对话中心  
> 状态：**已实现并运行**（本地 Web + FastAPI + OpenClaw + PostgreSQL）

---

## 零、范围说明

**本地独立 Web 应用**，与飞书无关联，视觉风格沿用飞书对话中心。

| 页面 | 路径 | 说明 |
|------|------|------|
| **对话页面** | `/`、`/c/:sessionId` | 欢迎区 + 技能快捷入口 + 输入框 + 消息流；刷新可恢复会话 |
| **技能广场** | `/skills` | 技能完整展示（分类浏览，数据来自 `skills/skills.yaml`） |
| **智能体** | `/agents`、`/agents/:agentId` | 智能体列表 / 详情（展示层） |

左侧导航：**发起新对话**、**技能广场**、**智能体** + 最近对话（后端会话列表）。

---

## 一、产品定位

```
用户输入 / 点击技能卡片
         │
         ▼
   猛犸 Backend（透传 + 会话落库）
         │  Header: x-openclaw-agent-id
         │  Body:   model / user=conv:{session_id}
         ▼
      OpenClaw Agent（默认 main）
         │  自行识别意图、调用 MCP / 技能
         ▼
      返回回复 ──► 前端展示 + PostgreSQL 持久化
```

**核心原则**：
- 前端**不做**技能路由、**不做**技能与 model 映射
- 技能广场仅是**展示 + 快捷填入示例 prompt**
- 所有对话内容原样送到 OpenClaw，由 OpenClaw 决定用哪个技能
- 必须指定 OpenClaw **agent-id** 与稳定 **user（conv:会话ID）**，才能在 OpenClaw Control UI 后台看到对应对话（对齐 AI4Drug 调用方式）

---

## 二、页面结构

### 2.1 全局布局

```
┌────────────┬────────────────────────────────────────────────┐
│  [logo]    │  顶部栏（青绿色，用户区）                         │
│  猛犸智能体  ├────────────────────────────────────────────────┤
│            │                                                │
│ [发起新对话] │              主内容区                            │
│ [技能广场]  │         （对话页 / 技能广场页）                    │
│            │                                                │
│            │                                                │
│  ────────  │                                                │
│  最近对话   │                                                │
│  · 对话1   │                                                │
│  · 对话2   │                                                │
└────────────┴────────────────────────────────────────────────┘
```

### 2.2 左侧导航（主导航 + 最近对话）

| 菜单项 | 行为 |
|--------|------|
| **发起新对话** | 清空当前会话，跳转对话页欢迎态 |
| **技能广场** | 跳转 `/skills`，展示全部技能 |
| **智能体** | 跳转 `/agents` |
| 最近对话 | 后端会话列表（PostgreSQL），点击进入 `/c/:sessionId` |

### 2.3 对话页面 — 欢迎态

```
┌─────────────────────────────────────────────────────────────┐
│              [huixiang.png]                                   │
│              你好，我是猛犸智能体                               │
│     智能设计 · 文献检索 · 自动执行 · 数据分析                   │
├─────────────────────────────────────────────────────────────┤
│  技能广场                          [全部] [实验设计] [文献]... │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐               │
│  │蛋白纯化 │ │催化剂优化│ │酶工程检索│ │文献设计 │  ...         │
│  └────────┘ └────────┘ └────────┘ └────────┘               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │  描述您的科研任务，例如：帮我设计一个酶进化的实验...    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                    [发送]    │
└─────────────────────────────────────────────────────────────┘
```

- **无**四大能力卡片
- **无**对话内智能体下拉做路由
- 技能以卡片形式展示（与技能广场页相同数据源 `skills.yaml`）
- 点击技能卡片 → 将示例 prompt 填入输入框

### 2.4 对话页面 — 对话态

发送第一条消息后切换：

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─ 用户 ─────────────────────────────────────────────┐    │
│  │ 帮我设计一个酶进化的实验方案                           │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌─ 猛犸智能体 ────────────────────────────────────────┐    │
│  │ 好的，我来帮你设计酶进化实验方案。首先...  (Markdown)    │    │
│  └────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │  继续描述您的需求...                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                    [发送]    │
└─────────────────────────────────────────────────────────────┘
```

- 技能广场**收起**，专注消息流
- 底部输入区始终固定

### 2.5 技能广场页面

```
┌─────────────────────────────────────────────────────────────┐
│  技能广场                                                     │
│  选择技能快速开始，或在对话中直接描述您的需求                      │
├─────────────────────────────────────────────────────────────┤
│  [全部] [实验设计] [文献检索] [药物研发] [工艺优化] [数据分析]...  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 🧬            │  │ 🔬            │  │ 📚            │       │
│  │ 蛋白质纯化实验  │  │ 催化剂合成优化  │  │ 酶工程论文检索  │       │
│  │ 设计完整的...   │  │ 优化催化剂...   │  │ 检索酶工程...   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                         ...                                  │
└─────────────────────────────────────────────────────────────┘
```

- 展示全部技能，支持分类 Tab 过滤
- 点击技能卡片 → 跳转对话页，示例 prompt 填入输入框

---

## 三、视觉风格

完全沿用飞书对话中心：

| 元素 | 规格 |
|------|------|
| 顶部栏 | 青绿渐变 `#26B0B8` |
| 侧边栏 | 浅灰 `#F5F7FA`，激活项青绿底 |
| 主内容区背景 | `#FFFFFF` / `#F5F7FA` |
| 卡片 | 白底、圆角 12px、浅阴影 |
| 按钮 | 蓝色 `#3B82F6` |
| Logo | `huixiang.png` |
| 字体 | 系统无衬线（PingFang SC / Inter） |

---

## 四、技能列表

技能仅用于**前端展示**和**快捷填入 prompt**，与后端 model 无关。

- 数据源：`skills/skills.yaml`（当前含 AI4Drug 流水线技能 + 大量科研技能，数量随同步脚本更新）
- 对话页欢迎态可展示部分技能快捷入口；技能广场页展示全量，支持分类 Tab 过滤
- 点击技能卡片 → 将 `example` 填入输入框（技能广场页会先跳转对话页）

早期方案中的 15 个示例技能（实验设计 / 文献 / 药物等）仍可作为分类参考，但以 yaml 实际内容为准。

### 技能定义 Schema（`skills/skills.yaml`）

```yaml
skills:
  - id: ai4drug_target_discovery
    name: 靶点发现
    category: AI4Drug
    icon: "🎯"
    description: 根据疾病找出相关的药物靶点
    example: 帮我找一下肺癌的药物靶点
```

字段说明：

| 字段 | 用途 |
|------|------|
| `id` | 唯一标识（前端用，不传给 OpenClaw 做路由） |
| `name` | 卡片标题 |
| `category` | 分类 Tab 过滤 |
| `icon` | 卡片图标 |
| `description` | 卡片副标题 |
| `example` | 点击卡片时填入输入框的示例 prompt |

> **不包含** `openclaw_model`、`system_prompt`、`keywords` 等路由字段。

---

## 五、OpenClaw 对接

对齐 **AI4Drug**（`/data2/AI4Drug`）的调用约定，保证对话出现在 OpenClaw Control UI 对应 agent 下。

### 5.1 为什么必须带 agent-id 与 user

| 字段 | 作用 |
|------|------|
| `x-openclaw-agent-id` | 指定落到哪个 OpenClaw agent（如 `main` / `ai4drug`） |
| `model` | 可用 `openclaw:<agentId>` 作双重路由（与 AI4Drug 一致） |
| `user` | 固定为 `conv:<猛犸会话UUID>`，让 OpenClaw 服务端按会话复用上下文，并在后台生成可见 sessionKey |

若不指定：

- 请求会落到默认 agent，且 sessionKey 形如 `agent:main:openai:<随机UUID>`
- Control UI / agent 对话列表里**很难对应到猛犸前台那一轮对话**

指定后 sessionKey 形态（已实测）：

```
agent:main:openai-user:conv:<猛犸 session_id>
```

在 OpenClaw 后台选 **main** agent，即可看到对应会话。

### 5.2 调用方式（当前实现）

```bash
curl -X POST http://127.0.0.1:18789/v1/chat/completions \
  -H "Authorization: Bearer <OPENCLAW_API_KEY>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-agent-id: main" \
  -d '{
    "model": "openclaw:main",
    "user": "conv:<session_id>",
    "messages": [{"role": "user", "content": "帮我找一下糖尿病的药物靶点"}],
    "stream": false,
    "max_tokens": 64000
  }'
```

- 默认 agent：`main`（`OPENCLAW_AGENT_ID`）
- 若希望对话出现在 **ai4drug** agent 下，改为：

```env
OPENCLAW_AGENT_ID=ai4drug
OPENCLAW_MODEL=openclaw:ai4drug
```

- 意图识别与技能 / MCP 调度**全部由 OpenClaw 内部完成**（例如 `ai4drug__target_discovery`）
- 猛犸前端 → Vite 代理 `/api` → 后端 `:8080` → OpenClaw `:18789`

### 5.3 后端接口

#### `POST /api/chat`

```json
// 请求
{
  "session_id": "uuid 或 null（新会话）",
  "message": "帮我找一下糖尿病的药物靶点"
}

// 响应
{
  "session_id": "uuid",
  "reply": "以下是基于 AI4Drug 靶点发现工具...",
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

后端逻辑：

```python
# 1. 创建或加载 PostgreSQL 会话，写入 user message
# 2. 组装历史 messages，转发 OpenClaw：
#      Header: Authorization + x-openclaw-agent-id
#      Body:   model / user=conv:{session.id} / messages
# 3. 写入 assistant message，返回 reply
```

实现位置：`backend/openclaw_client.py`、`backend/main.py`。

#### 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 返回技能列表（读 `skills/skills.yaml`） |
| GET | `/api/sessions` | 最近会话列表 |
| GET | `/api/sessions/{id}` | 会话详情（含消息） |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| GET | `/api/health` | 检查 OpenClaw / 数据库连通性 |

### 5.4 环境变量

```env
OPENCLAW_BASE_URL=http://127.0.0.1:18789
OPENCLAW_API_KEY=...
OPENCLAW_AGENT_ID=main
OPENCLAW_MODEL=openclaw:main

DB_HOST=127.0.0.1
DB_PORT=5434
DB_USER=oakclaw
DB_PASSWORD=...
DB_NAME=mammoth_agent

BACKEND_PORT=8080
```

参考模板：`backend/.env.example`（勿将真实 `.env` 提交入库）。

### 5.5 与 AI4Drug 对照

| 项 | AI4Drug | 猛犸（当前） |
|----|---------|--------------|
| Agent | `ai4drug` | 默认 `main`（可配） |
| Header | `x-openclaw-agent-id` | 同左 |
| Model | `openclaw:ai4drug` | `openclaw:main`（可配） |
| user | `conv:{conversation_id}` | `conv:{session_id}` |
| 后台可见 | AI4Drug agent 会话列表 | 对应 agent（默认 main）会话列表 |
---

## 六、技术架构

```
┌──────────────┐     /api      ┌──────────────────┐   chat/completions  ┌─────────────┐
│  猛犸前端      │ ────────────► │  猛犸 Backend     │ ──────────────────► │  OpenClaw   │
│  React+Vite  │ ◄──────────── │  FastAPI         │ ◄────────────────── │  :18789     │
│  :5173 代理   │               │  :8080           │  agent-id + user    └──────┬──────┘
└──────────────┘               └────────┬─────────┘                            │
                                        │                                      ▼
                                        ▼                               MCP / 技能工具
                               PostgreSQL                                    │
                               mammoth_agent                                 ▼
                               sessions / messages                    如 AI4Drug :8000
```

| 层 | 技术 |
|----|------|
| 前端 | React + Vite + TypeScript + Tailwind CSS |
| 后端 | Python FastAPI + httpx |
| 会话 | PostgreSQL（独立库 `mammoth_agent`） |
| 技能定义 | `skills/skills.yaml`（仅展示） |
| 部署 | `./start.sh` 或分别启动前端 / 后端 |

### 目录结构

```
mammoth-agent/
├── huixiang.png
├── docs/DESIGN.md
├── start.sh
├── scripts/                     # 技能同步 / 测试脚本
├── frontend/src/
│   ├── components/
│   │   ├── Sidebar.tsx
│   │   ├── TopBar.tsx
│   │   ├── WelcomeHeader.tsx
│   │   ├── SkillPlaza.tsx
│   │   ├── ChatInput.tsx
│   │   └── MessageList.tsx
│   ├── pages/
│   │   ├── ChatPage.tsx
│   │   ├── SkillsPage.tsx
│   │   ├── AgentsPage.tsx
│   │   └── AgentDetailPage.tsx
│   ├── hooks/useChat.ts
│   └── api/client.ts
├── backend/
│   ├── main.py                  # /api/chat 等
│   ├── openclaw_client.py       # agent-id + user 透传
│   ├── config.py
│   ├── models.py / database.py
│   ├── init_db.py
│   └── .env.example
└── skills/skills.yaml
```

---

## 七、关键组件

| 组件 | 职责 |
|------|------|
| `Sidebar` | 发起新对话、技能广场、智能体、最近对话 |
| `TopBar` | 青绿顶栏（视觉还原飞书） |
| `WelcomeHeader` | Logo +「你好，我是猛犸智能体」 |
| `SkillPlaza` | 技能卡片网格 + 分类 Tab（两页复用） |
| `ChatInput` | 多行输入 + 发送按钮 |
| `MessageList` | 对话消息流 + Markdown 渲染 |

**已移除的组件**（相比 v0.2）：
- ~~CapabilityCards~~（四大能力卡片）
- ~~AgentSelector~~（对话内智能体下拉做路由）
- ~~WorkflowSelector~~（流程选择）
- ~~SkillBadge~~（技能匹配标签，路由由 OpenClaw 负责）
- ~~intent_router~~（后端意图识别）

---

## 八、交互细节

| 操作 | 行为 |
|------|------|
| 点击技能卡片（对话页） | 示例 prompt 填入输入框 |
| 点击技能卡片（技能广场页） | 跳转对话页 + 填入示例 prompt |
| 按 Enter | 发送（Shift+Enter 换行） |
| 发送 | 调用 `/api/chat`，展示 loading → 回复（OpenClaw 可能较久，日志在请求结束后才出现） |
| 发起新对话 | 新 session，回到欢迎态（技能广场可见） |
| 刷新 `/c/:id` | 从后端恢复会话消息 |
| 切换分类 Tab | 过滤技能卡片 |
| 进入对话态 | 技能广场收起，只显示消息流 + 输入框 |

---

## 九、开发分期

### 一期（已完成）

- [x] 设计文档（v0.3 → v0.4）
- [x] 全局布局（侧边栏 + 顶栏）
- [x] 对话页（欢迎态 + 对话态 + 技能快捷入口）
- [x] 技能广场页
- [x] 后端透传 OpenClaw + PostgreSQL 会话
- [x] Markdown 回复渲染
- [x] OpenClaw agent-id / `user=conv:` 对齐（后台可见对话）

### 二期

- [ ] 流式输出（SSE）
- [ ] 文件上传
- [ ] 技能管理后台（可视化增删技能）
- [ ] 按技能类型自动选择 OpenClaw agent（可选）

---

## 十、已确认决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 视觉风格 | ✅ 沿用飞书青绿色 |
| 2 | 四大能力卡片 | ✅ **不要** |
| 3 | 技能数量 | ✅ 以 `skills.yaml` 为准（可扩展，不限于早期 15 个） |
| 4 | 对话内智能体选择 | ✅ **不做路由选择**；技能广场只填 prompt |
| 5 | 左侧导航 | ✅ 「发起新对话」+「技能广场」+「智能体」+ 最近对话 |
| 6 | 技能可见性 | ✅ 对话页快捷入口 + 技能广场全量 |
| 7 | 对话态行为 | ✅ 发送后收起技能广场 |
| 8 | 部署方式 | ✅ 本地独立运行，与飞书无关 |
| 9 | 后端 | ✅ Python FastAPI |
| 10 | 技能与 model | ✅ **无映射**，内容送 OpenClaw，由 OpenClaw 识别技能 |
| 11 | 会话存储 | ✅ PostgreSQL 独立库 `mammoth_agent` |
| 12 | OpenClaw 可见性 | ✅ 必须带 `x-openclaw-agent-id` + `user=conv:{session_id}`（对齐 AI4Drug） |
| 13 | 默认 agent | ✅ `main`；可通过环境变量改为 `ai4drug` 等 |

---

**v0.4：补齐 OpenClaw agent 路由与会话可见性约定，并同步已落地架构（PostgreSQL / 技能扩展 / 页面路由）。**
