---
id: memory.doc-gaps
title: 已识别的文档缺口
layer: memory
tags: [memory, gaps, todo]
status: living
---

# 已识别的文档缺口

集中登记 yapi llmdoc 当前已知但尚未补齐的洞。每条只写一两行，发现新缺口时直接追加；解决后划掉但保留原文以便回溯。

## 当前条目

- **`llmdoc/` 已纳入版本控制**（2026-05-24 决定）：从本次起 llmdoc 与代码一起进 git，外部 contributor 与 fork 都可见。原先"未入库 + 与历史一致"的策略作废。
- **`memory/decisions/` 仍空**：命名决策（`yapi` → 中间态 `yapi-py` → 最终 `pyyapi`）值得在未来沉淀一条 decision，避免有人提议"改回 yapi"时白做工。

## 已解决（保留以便回溯）

- ~~**`architecture/agent-runner-contract.md`**：被 `index.md` 与 `must/api-surface.md` 引用，但文件实际不存在。~~（2026-05-24 v2.1 实施后落地。）
- ~~**`reference/error-catalog.md`**：被 `index.md` 与 `must/api-surface.md` 引用，文件不存在。~~（2026-05-24 v2.1 实施后落地。）
- ~~**`reference/run-and-test.md`**：被 `index.md` 与 `must/project-shape.md` 引用，文件不存在。~~（2026-05-24 v2.1 实施后落地。）
- ~~**装饰器静默丢弃 FastAPI 原生 kwargs**（`tags=` / `summary=` / `status_code=` 等）：代码层没有任何 warning。~~（v2.1 已解决，`yapi/router.py` `_PASSTHROUGH_KWARGS` 透传白名单 + `_REJECTED_KWARGS` 装饰期报错 + 未识别 kwarg `YapiUsageWarning`；回归保险 `tests/test_router.py::test_prompt_passthrough_tags_summary_status_code` 与 `::test_prompt_warns_on_unknown_kwarg`。）
- ~~**`async def` 用户函数在请求期必然 500**：当前测试矩阵无覆盖。~~（v2.1 已解决，`yapi/router.py` 装饰期 `is_async = inspect.iscoroutinefunction(func)` 分支 + 请求期 `await func(**kwargs)`；回归保险 `tests/test_router.py::test_prompt_supports_async_def_handler`。）

## v2.1 落地后新增的事实记录（不是 gap，避免下次再次提出）

- v2.1 spec §9.2 列出的破坏点（`@router.post = prompt` → 原生 FastAPI；`response_model= / response_class= / dependencies=` kwarg 由静默丢弃改为装饰期报错；`from yapi.errors import StateStoreError` 由可导入改为 `ImportError`）已在 README 迁移段落与本 llmdoc 各处显性化。
- v1 残留 `yapi/agent.py::DEFAULT_SYSTEM_PREFIX` 死代码警告：v2.1 已物理删除该常量（`yapi/agent.py` 不再定义 `DEFAULT_SYSTEM_PREFIX`），唯一实际生效的是 `yapi/runtime.py::DEFAULT_SYSTEM_PREFIX`。
- v2.1 测试矩阵较 v2 显著扩张（8 个 test 文件，覆盖 router / runtime / compat / runner / dx / integration / exports；具体用例数会随后续小修而变，不写死数字）。

## v2.2 落地后新增的事实记录（不是 gap，避免下次再次提出）

- **v2.1 → v2.2 唯一 user-visible 破坏点**：v2.1 路由 `return "hint"` 现在被裹进 `<context>...</context>`（之前裸拼在 system prompt 末尾）。绝大多数 prompt 对 XML 边界鲁棒——substring assertions 仍成立——若 prompt 含字面"看 prompt 末尾的一段话"这种位置依赖措辞，重述为"看 `<context>` 内的内容"即可。版本号 `0.2.0 → 0.3.0`（按 v2.2 spec §9.3：0.x 期允许 MINOR bump 引入小破坏）。
- **state 集成是有意为之不做**：v2.2 spec §1 / §10 再次明确 yapi 不集成 `StateStore` Protocol、不做 `Annotated[T, FromState(...)]`、不做装饰器 `state=` 参数。state 这件事留给开发者用 FastAPI 原生 `Depends` + 任意客户端解决。下次有人再提"加 state 集成"前先重读这条；示例见 `examples/state_via_depends.py`。
- **PromptContext 是 yapi 唯一感知 ctx 参数的地方**：FastAPI / OpenAPI 都看不到（handler `__signature__` 过滤），runner 也只看到拼好的 `prompt: str`——`RunnerContext` 字段集合**没变**。需要 segment 级粒度的 runner 自行 parse `<context>`（YAGNI 推迟）。
- **`prompt_composer=` 旧 2-arg 签名仍可用**：`_adapt_composer` 包一层 adapter，请求期先按 v2.2 的 3-arg 试，TypeError 后回退到 2-arg。与 `_LegacyCallableRunner` 同思路。
- **v2.2 测试矩阵新增 ~20 用例**：`tests/test_prompt_context.py` 新建（11 条）+ `test_runtime.py` 增补 4 条 compose 用例 + `test_router.py` 增补 6 条 ctx 用例 + `test_integration.py` 增补 3 条 e2e；共 79 passed。

## 待复核 / 待跟进

- **`Runtime` 内 `model_validate` 失败的错误反馈策略**：当前只打 WARNING log 后让 `ValidationError` 上抛，FastAPI 转 HTTP 500，错误体里看不到字段细节。未来是否包装为 `RuntimeExecutionError` 带字段路径 hint 待定。
- **多个 `<context>` 块**（如 `<user_context>` / `<item_context>` 分离）：v2.2 spec §10 明确不做，一个路由一个 `<context>`，里面用 `add_section(name, ...)` 区分子段。如果未来 LLM 实测对子段分隔不敏感导致需求出现，再考虑。
