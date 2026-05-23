---
id: startup
title: 启动阅读顺序
layer: startup
tags: [startup, must-read]
status: stable
---

# 新会话启动阅读顺序

按下面的有序清单读完 must/ 下两份文档，应该足以让一个新会话立即开始读源码、修代码、写测试，不需要再回到 v1/v2 spec。

## 顺序

1. [`must/project-shape.md`](./must/project-shape.md)
2. [`must/api-surface.md`](./must/api-surface.md)

## 读完后可以直接确认的事实

- yapi 是什么：prompt-first 的声明式 HTTP 框架，公开符号只有 `PromptRouter` 一个。
- 当前实现对齐 v2 spec（`docs/superpowers/specs/2026-05-21-yapi-v2-design.md`）；v0 plan 已过时，不要按它写代码。
- Python ≥ 3.12；安装 `uv sync --extra dev`；测试 `uv run pytest`；起服务 `uv run uvicorn examples.wish_api:app --reload`。
- `YAPI_MODEL` 是默认 agent runner 的唯一外部配置入口；不设置时第一次请求会变成 HTTP 500；离线 demo 用 `YAPI_MODEL=test`。
- `PromptRouter` 继承 `fastapi.APIRouter`，覆盖 `.get/.post/.put/.patch/.delete`，所有路由都是 prompt 路由。
- 装饰器不接受 `request_model=` / `response_model=` 等显式参数；契约完全从函数签名推断。
- 函数签名约束：最多一个 `BaseModel` 参数；其他参数 default 必须是 `Depends(...)`；返回注解必须是 `BaseModel` 子类；函数返回值必须是 `None` 或 `str`。
- 同一个 `PromptRouter` 内不可混挂普通 FastAPI 接口。

读完上面两份后，按当前任务的方向再去看 [`index.md`](./index.md) 选择 architecture/reference/memory 中具体文档。
