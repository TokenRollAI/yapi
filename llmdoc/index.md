---
id: index
title: yapi 文档地图
layer: index
tags: [index, catalog]
status: stable
---

# yapi llmdoc 全局地图

yapi 是一个 prompt-first 的声明式 HTTP 框架：开发者在 `PromptRouter` 上写 `@router.prompt.post(...)` 装饰一个有 docstring 的函数（`def` 或 `async def`），框架在请求期把签名 / docstring / 动态 prompt 转交给 PydanticAI Agent 生成结构化响应。`PromptRouter` 自身是 `fastapi.APIRouter` 的**真超集**——原生 `.get/.post/...` 走 FastAPI 通道，prompt 路由收敛到显式 `router.prompt.*` 子命名空间。当前代码对齐 `docs/superpowers/specs/2026-05-24-yapi-v2.1-design.md`。

新会话的有序读法在 [`startup.md`](./startup.md)，本文件只做分类目录。

## must/ — 每次会话都该看的最小事实

- [`must/project-shape.md`](./must/project-shape.md) — 项目是什么、对齐 v2.1 spec、最小运行入口、`YAPI_MODEL` 的角色与 `YapiUsageWarning` 触发条件。
- [`must/api-surface.md`](./must/api-surface.md) — `PromptRouter` 对外契约（APIRouter superset、`.prompt.*` 子命名空间、kwarg 三档、ParamRole 4 分类、async def、动态 prompt 契约）。

## overview/ — 项目定位与边界

- [`overview/project-overview.md`](./overview/project-overview.md) — 产品定位、目标用户、明确不做的事、v1→v2→v2.1 简史。

## architecture/ — 执行模型与不变量

- [`architecture/request-lifecycle.md`](./architecture/request-lifecycle.md) — 从 `@router.prompt.<method>` 到 JSON 响应的端到端深度文档：`_register_prompt`、`_classify_param`、handler 闭包、`__signature__` 修补、`run_in_threadpool`、`Runtime.execute`、`compose_prompt`、`isinstance` 快路径、logging 通道。
- [`architecture/agent-runner-contract.md`](./architecture/agent-runner-contract.md) — `AgentRunner` Protocol、`RunnerContext` 字段（含 `path / method`）、Protocol 静态提示局限、`_coerce_runner` + `_LegacyCallableRunner` 兼容适配、`PydanticAIRunner` 默认实现、`prompt_composer` 注入点、fake runner 测试范式。

## reference/ — 稳定查询事实

- [`reference/annotated-introspection.md`](./reference/annotated-introspection.md) — `Annotated[T, *metadata]` 内省协议、`_unwrap_annotated` helper、Body 必须先于 Param 判断、handler `__signature__` 不可剥 Annotated。
- [`reference/error-catalog.md`](./reference/error-catalog.md) — `YapiError / YapiDeclarationError / RuntimeExecutionError / YapiUsageWarning` 层级、各错误的触发位置与示例消息、`StateStoreError` 已物理删除。
- [`reference/run-and-test.md`](./reference/run-and-test.md) — `uv sync` / `uv run pytest` / `uv run uvicorn` 三组命令、`YAPI_MODEL=test` 离线 smoke、四个 example 跑法、按文件维度的测试矩阵、pytest 抓 DEBUG log 的双指定陷阱。

## guides/ — 工作流

- [`guides/release.md`](./guides/release.md) — 发布到 PyPI：tag-driven 触发、版本号闸门、Trusted Publishing 三件套、CI 不需要 secrets、v0.1.0 与 v0.2.0 真实历史。

## memory/ — 历史过程记忆

- [`memory/doc-gaps.md`](./memory/doc-gaps.md) — 已识别的文档缺口、代码残留、设计欠缺集中索引（含 v2.1 已解决条目的归档）。
- `memory/decisions/` — 决策日志（recorder 维护）：
  - [`memory/decisions/2026-05-24-yapi-v2.1-surface-split.md`](./memory/decisions/2026-05-24-yapi-v2.1-surface-split.md) — 为什么从装饰器 override 转向 `.prompt` 子命名空间 + APIRouter superset；为什么保留 `_LegacyCallableRunner` 不发 deprecation。
- `memory/reflections/` — 反思记录（reflector 维护）：
  - [`memory/reflections/2026-05-24-pypi-release-bootstrap.md`](./memory/reflections/2026-05-24-pypi-release-bootstrap.md) — pyyapi 首次 PyPI 发布与 GitHub Trusted Publishing 流水线。
  - [`memory/reflections/2026-05-24-yapi-v2.1-impl.md`](./memory/reflections/2026-05-24-yapi-v2.1-impl.md) — v2.1 实施反思（PromptRouter 升 APIRouter superset / Annotated 全面化 / pydantic-ai 集成类化）。

## 仓库外参考材料

llmdoc 文档**不会**复制以下文件的内容，仅在需要时通过相对路径引用：

- `docs/superpowers/specs/2026-05-20-yapi-design.md` — v1 设计（含 state / tool 的完整愿景）；**已被 v2 + v2.1 取代**，仅作历史参考。
- `docs/superpowers/specs/2026-05-21-yapi-v2-design.md` — v2 设计（取代 v1 第 4、6、9、10 节）；v2.1 的前置阅读。
- `docs/superpowers/specs/2026-05-24-yapi-v2.1-design.md` — v2.1 设计（在 v2 基础上增量扩展）；**当前代码的事实来源**。
- `docs/superpowers/plans/2026-05-20-yapi-v0-implementation.md` — v0 实现 plan，**已过时**（基于 v1）；勿按此文动手。
