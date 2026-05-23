---
id: memory.doc-gaps
title: 已识别的文档缺口
layer: memory
tags: [memory, gaps, todo]
status: living
---

# 已识别的文档缺口

集中登记 yapi llmdoc 当前已知但尚未补齐的洞。每条只写一两行，发现新缺口时直接追加。

## 当前条目

- **`architecture/agent-runner-contract.md`**：被 `index.md` 与 `must/api-surface.md` 引用，但文件实际不存在。
- **`reference/error-catalog.md`**：被 `index.md` 与 `must/api-surface.md` 引用，文件不存在。
- **`reference/run-and-test.md`**：被 `index.md` 与 `must/project-shape.md` 引用，文件不存在。
- **`llmdoc/` 已纳入版本控制**（2026-05-24 决定）：从本次起 llmdoc 与代码一起进 git，外部 contributor 与 fork 都可见。原先"未入库 + 与历史一致"的策略作废。
- **`memory/decisions/` 仍空**：命名决策（`yapi` → 中间态 `yapi-py` → 最终 `pyyapi`）值得在未来沉淀一条 decision，避免有人提议"改回 yapi"时白做工。
- **装饰器静默丢弃 FastAPI 原生 kwargs**（`tags=` / `summary=` / `status_code=` 等）：`must/api-surface.md` 已点出这是开发者陷阱，但代码层没有任何 warning——是否在 router 里加运行时提示待定。
- **`async def` 用户函数在请求期必然 500**：`must/api-surface.md` 已记录，但当前测试矩阵无覆盖。
