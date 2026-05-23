---
id: startup
title: 启动阅读顺序
layer: startup
tags: [startup, must-read]
status: stable
---

# 新会话启动阅读顺序

按下面的有序清单读完 must/ 下两份文档，应该足以让一个新会话立即开始读源码、修代码、写测试，不需要再回到 spec。

## 顺序

1. [`must/project-shape.md`](./must/project-shape.md)
2. [`must/api-surface.md`](./must/api-surface.md)

## 读完后可以直接确认的事实

- yapi 是什么：prompt-first 的声明式 HTTP 框架，公开符号 7 个：`PromptRouter / AgentRunner / RunnerContext / YapiError / YapiDeclarationError / RuntimeExecutionError / YapiUsageWarning`（`yapi/__init__.py` `__all__`）。
- 当前实现对齐 v2.1 spec（`docs/superpowers/specs/2026-05-24-yapi-v2.1-design.md`，在 v2 基础上增量扩展）；v0 plan 已过时，不要按它写代码。
- Python ≥ 3.12；安装 `uv sync --extra dev`；测试 `uv run pytest`；起服务 `uv run uvicorn examples.wish_api:app --reload`。
- `YAPI_MODEL` 是默认 agent runner 的唯一外部配置入口；不设置时 `PromptRouter()` 构造期会发 `YapiUsageWarning`，第一次请求 HTTP 500；离线 demo 用 `YAPI_MODEL=test`。
- `PromptRouter` 是 `fastapi.APIRouter` 的**真超集**：`.get/.post/...` 走原生 FastAPI 通道，prompt 路由通过显式 `router.prompt.{get,post,put,patch,delete}` 子命名空间。
- prompt 装饰器 kwarg 三档处理：透传白名单（10 个 OpenAPI / 路由元数据 kwarg）/ 拒绝清单（`response_model`、`response_class`、`dependencies`）装饰期报错 / 未识别 kwarg 发 `YapiUsageWarning`。
- 函数签名 4 分类（`ParamRole`）：**REQUEST_MODEL**（裸 BaseModel 或 `Annotated[BaseModel, Body()]`）、**DEPENDENCY**（`Depends()` 默认值或 `Annotated[T, Depends()]`）、**INJECTED_FIELD**（`Query/Header/Cookie/Path/Form/File` 作 default 或 Annotated metadata）；至多一个 REQUEST_MODEL，返回注解必须是 `BaseModel` 子类。
- `async def` 路由函数受支持；generator / async generator 装饰期报错。
- 同一个 `PromptRouter` 内**允许并鼓励**混挂普通 FastAPI 接口与 prompt 接口（见 `examples/mixed_router.py`）。

读完上面两份后，按当前任务的方向再去看 [`index.md`](./index.md) 选择 architecture/reference/memory 中具体文档。
