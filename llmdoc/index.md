---
id: index
title: yapi 文档地图
layer: index
tags: [index, catalog]
status: stable
---

# yapi llmdoc 全局地图

yapi 是一个 prompt-first 的声明式 HTTP 框架：开发者在 `PromptRouter` 上写 `@router.post(...)` 装饰一个普通的"有 docstring 的同步函数"，框架在请求期把签名 / docstring / 动态 prompt 转交给 PydanticAI Agent 生成结构化响应。当前代码对齐 `docs/superpowers/specs/2026-05-21-yapi-v2-design.md`。

新会话的有序读法在 [`startup.md`](./startup.md)，本文件只做分类目录。

## must/ — 每次会话都该看的最小事实

- [`must/project-shape.md`](./must/project-shape.md) — 项目是什么、对齐哪个 spec、最小运行入口、`YAPI_MODEL` 的角色。
- [`must/api-surface.md`](./must/api-surface.md) — `PromptRouter` 唯一对外类的核心契约（装饰器、签名推断、返回值、动态 prompt）。

## overview/ — 项目定位与边界

- [`overview/project-overview.md`](./overview/project-overview.md) — 产品定位、目标用户、明确不做的事、v1→v2 简史。

## architecture/ — 执行模型与不变量

- [`architecture/request-lifecycle.md`](./architecture/request-lifecycle.md) — 从装饰器到 JSON 响应的端到端深度文档：`_introspect`、handler 闭包、`__signature__` 修补、`run_in_threadpool`、`Runtime.execute`、`compose_prompt`、`response_model.model_validate`。
- [`architecture/agent-runner-contract.md`](./architecture/agent-runner-contract.md) — `agent_runner` 的 keyword 契约、默认 `build_agent_runner` 何时读 `YAPI_MODEL`、user_prompt 形状、`result.output` 双 fallback、fake runner 测试范式、`YAPI_MODEL=test` 离线驱动。

## reference/ — 稳定查询事实

- [`reference/error-catalog.md`](./reference/error-catalog.md) — `YapiError` 层级、各类错误的触发条件与示例消息、`StateStoreError` 为 v1 残留占位符的说明。
- [`reference/run-and-test.md`](./reference/run-and-test.md) — `uv sync` / `uv run pytest` / `uv run uvicorn` 三组命令、`YAPI_MODEL=test` 离线 demo 流程、15 条测试矩阵分布、deprecation warnings 来源。

## guides/ — 工作流

- [`guides/release.md`](./guides/release.md) — 发布到 PyPI：tag-driven 触发、版本号闸门、Trusted Publishing 三件套、CI 不需要 secrets。

## memory/ — 历史过程记忆

- [`memory/doc-gaps.md`](./memory/doc-gaps.md) — 已识别的文档缺口、代码残留、设计欠缺集中索引。
- `memory/decisions/` — 决策日志（recorder 维护，当前为空）。
- `memory/reflections/` — 反思记录（reflector 维护）；见 [`memory/reflections/2026-05-24-pypi-release-bootstrap.md`](./memory/reflections/2026-05-24-pypi-release-bootstrap.md)。

## 仓库外参考材料

llmdoc 文档**不会**复制以下文件的内容，仅在需要时通过相对路径引用：

- `docs/superpowers/specs/2026-05-20-yapi-design.md` — v1 设计（含 state / tool 的完整愿景）。
- `docs/superpowers/specs/2026-05-21-yapi-v2-design.md` — v2 设计（取代 v1 第 4、6、9、10 节）；**当前代码的事实来源**。
- `docs/superpowers/plans/2026-05-20-yapi-v0-implementation.md` — v0 实现 plan，**已过时**（基于 v1）；勿按此文动手。
