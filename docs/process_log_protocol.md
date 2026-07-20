# OpenClaw 过程日志文件协议

日志目录：`/data2/mammoth-agent/process_logs/{YYYY-MM-DD}/`  
文件名：`{session_id}.jsonl`

按本地日期分目录，例如 `process_logs/2026-07-20/xxx.jsonl`。

## 事件类型

| type | 含义 |
|------|------|
| `session` | 本轮开始 |
| `step` | 思考 / 工具步骤（实时） |
| `delta` | 最终回答文本增量 |
| `error` | 出错 |
| **`mammoth_done`** | **本轮结束（必须停止监听）** |

## 结束标签（硬约定）

本轮结束后，文件末尾固定写入：

1. JSON 行：

```json
{"type":"mammoth_done","tag":"<<<MAMMOTH_DONE>>>","session_id":"...","reply":"...","error":null,"ok":true}
```

2. 纯文本行（便于 `grep` / 脚本）：

```text
<<<MAMMOTH_DONE>>>
```

### 监听方规则

- 读到 `type == "mammoth_done"` **或** `tag == "<<<MAMMOTH_DONE>>>"` **或** 纯文本行 `<<<MAMMOTH_DONE>>>` 时：
  - **立刻停止** tail / 轮询 / SSE
  - **禁止**再继续「询问结果」
- 未见到该标记前，才继续等待新内容

常量（代码里）：

- `PROCESS_LOG_DONE_TYPE = "mammoth_done"`
- `PROCESS_LOG_DONE_TAG = "<<<MAMMOTH_DONE>>>"`
