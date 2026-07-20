# 过程信息模板（参考 MatVenus）

不依赖 OpenClaw 自己「写好看」；由猛犸在**写日志 / 读日志展示**时套模板。

## MatVenus 观察结论

1. **折叠列表**：`分析过程 · N 个工具` → 深度思考 + 多条 `MCP 已执行 <工具名>`
2. **点击工具**：右侧/弹层展示两块固定结构  
   - **参数**（查询语句 / 输入）  
   - **输出**（结构化结果：条数、耗时、表格/JSON 摘要）
3. **结果卡片**：可再点开实体详情（如 UniProt Q8WXI7、PDB 7SA9）
4. 过程与最终回答交错：中间穿插自然语言进度，工具条是「证据锚点」

## 猛犸落地方案（已实现骨架）

每条过程步骤统一字段：

| 字段 | 含义 | 来源 |
|------|------|------|
| title | 中文步骤名（如「化学性质计算」） | `tool_summarize.friendly_tool_step` |
| name | 展示用工具名 | 同上 |
| input | 参数摘要（脱敏路径） | 同上 |
| result | 输出摘要 | `toolResult` + `summarize_tool_result` |
| detail | 展开区「输出」正文 | 同上 |
| status | running / done / failed | toolCall → toolResult |

展开 UI（对齐 MatVenus）：

```
步骤：化学性质计算
名称：chemistry-calculation (properties)
参数
  SMILES "O=C=O"，查询分子量
输出
  分子量 44.009 g/mol
```

## 为何不必强依赖「万能模板」

用户问题开放时，固定叙事模板难覆盖；更稳的是：

1. **通用外壳固定**：参数 / 输出 / 状态（本方案）
2. **按工具特化摘要**：chemistry-calc、read skill、exec…（已有）
3. **未知工具**：降级为「脱敏后的输入 + 输出截断」
4. 可选后续：同名工具合并为 `×N`（MatVenus 有，我们可下一迭代）
