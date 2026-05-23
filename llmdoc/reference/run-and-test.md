---
id: reference.run-and-test
title: 运行与测试命令
layer: reference
tags: [reference, commands, pytest, uv, examples, caplog]
status: stable
---

# 运行与测试命令

固化 yapi 仓库内"装环境 → 跑测试 → 起 example → 抓日志"的稳定命令与陷阱。

## 1. 环境准备

```bash
uv sync --extra dev          # 推荐；uv.lock 已落库
# 或
pip install -e ".[dev]"
```

Python ≥ 3.12（`pyproject.toml` `requires-python`）。`dev` extra 拉 `httpx / pytest / pytest-asyncio`。

## 2. 跑测试

```bash
uv run pytest                # 无参，pyproject.toml 已配 pythonpath=["."] 与 testpaths=["tests"]
uv run pytest -k async_def   # 跑某个用例
uv run pytest tests/test_router.py -v
```

## 3. 起 example

四个 example 都在 `examples/` 下，启动模板：

```bash
YAPI_MODEL=test uv run uvicorn examples.<name>:app --reload
```

| example | 演示重点 | 可观察现象 |
|---|---|---|
| `examples.wish_api` | 最小骨架（仅 prompt 路由） | `POST /wish` → `TestModel` 占位 JSON |
| `examples.mixed_router` | 同 router 内混挂 `router.get("/health")` + `router.prompt.post("/wish")` | `GET /v1/health` 走原生 FastAPI 通道，**不**调用 agent_runner；`POST /v1/wish` 走 prompt 管线，共享 `prefix=/v1` 与 `tags=["wishes"]` |
| `examples.with_depends` | `Depends(fetch_profile)` 注入 + `PromptContext` 收集片段（v2.2 风格） | request body 与 `Depends` 解析结果都进 `injected`；`ctx.add_section / add_kv` 片段被拼进 `<context>...</context>` 段 |
| `examples.state_via_depends` | "yapi 不集成 state"立场示例：用 `Depends(get_store)` 拿 dict store + `ctx.add_section` 塞 prompt | 演示 Redis / Mongo / SQL 这类 state 客户端如何用 FastAPI 原生 Depends 注入，避开"yapi 内置 StateStore"反模式 |
| `examples.custom_runner` | 自定义 `AgentRunner` Protocol 实现，无需 `YAPI_MODEL` | response message 含 `path=/wish method=POST prompt_chars=<N>`，演示 `RunnerContext` 字段可被 runner 直接消费 |

`wish_api / mixed_router / with_depends / state_via_depends` 在 import 时会发 `YapiUsageWarning("YAPI_MODEL not set; ...")`——这是预期信号（spec §6.4），见 [`./error-catalog.md`](./error-catalog.md) §6 与 [`../must/project-shape.md`](../must/project-shape.md)。`custom_runner` 传了自定义 runner 不触发。

## 4. 离线 smoke：`YAPI_MODEL=test`

设字面量 `test` 后 PydanticAI 内置 `TestModel` 接管，**零 API key、零网络**，按响应模型 schema 生成占位结构。CI 与 release 流水线全部依赖这个 token 做端到端冒烟，因此发版无需配置任何 LLM provider secret。

```bash
YAPI_MODEL=test uv run uvicorn examples.wish_api:app --reload &
curl -X POST http://localhost:8000/wish \
     -H 'content-type: application/json' \
     -d '{"user_id":"u-1","wish":"moon"}'
# → {"granted": <bool>, "message": "<占位>"}
```

## 5. 测试矩阵布局

`tests/` 下按职责分文件，规模较 v2 显著扩张。**不写死具体用例数**（小修就变）：

| 文件 | 覆盖范围 |
|---|---|
| `tests/test_router.py` | `_introspect` / `_classify_param` / kwarg 三档处理 / Annotated 全形态 / async def / generator 拒绝 / handler `__signature__` 保留 |
| `tests/test_runtime.py` | `compose_prompt` 拼接顺序 / `Runtime.execute` / `RuntimeContext` 形态 / runner 接到 prompt |
| `tests/test_compat.py` | PromptRouter ↔ APIRouter superset 兼容（原生路由 / 混挂 prefix+tags / `router.prompt` 命名空间 / APIRouter kwargs 透传） |
| `tests/test_runner.py` | Protocol class runner / RunnerContext `path / method` / legacy callable / `prompt_composer` 注入 / bad runner 请求期错误 / `_coerce_runner` 非 callable 拒绝 |
| `tests/test_dx.py` | DEBUG log / `RuntimeExecutionError` cause 摘要 / `build_default_runner` warning 行为 / `__init__.py` re-export 完整性 / `StateStoreError` 删除验证 |
| `tests/test_integration.py` | Depends 注入到 `injected` / dynamic prompt 流到 runner / 非 str 返回值的请求期 500 / v2.2 PromptContext 端到端 |
| `tests/test_prompt_context.py` | `PromptContext` 三方法 + `_format_value` 各类型分支 + None 拒绝 + 段序（v2.2 新建） |
| `tests/test_exports.py` | 公开符号 import smoke |
| `tests/live/` | **真实 LLM provider 端到端**（v2.2 新增）；默认 skip，需 `--run-live` flag + `YAPI_MODEL` 真实 provider 才跑。详见 §8 |
| `tests/conftest.py` | （目前无测试函数，仅 fixtures / pythonpath 准备） |

每个文件顶部 docstring 标注对应的 spec §x.y，方便回溯。

## 6. pytest 风格规范

### 6.1 抓 `yapi.runtime` 的 DEBUG log 必须 logger 双指定

`Runtime.execute` 在 module-level logger `yapi.runtime` 上打 DEBUG。pytest 的 `caplog` 默认只捕获**根 logger 上传播的 WARNING+**——`yapi.runtime` 这种命名 logger 的 DEBUG 不会自动捕获，必须双指定：

```python
import logging
import pytest

def test_runtime_logs_debug(caplog: pytest.LogCaptureFixture) -> None:
    ...
    with caplog.at_level(logging.DEBUG, logger="yapi.runtime"):
        # 触发请求
        ...
    messages = [r.getMessage() for r in caplog.records if r.name == "yapi.runtime"]
    assert any("path=/wish" in m for m in messages)
```

**反模式**：只写 `caplog.set_level(logging.DEBUG)`（漏掉 `logger=` 参数）→ 命名 logger 的 DEBUG 不传播到 root，断言永远拿不到 records，测试假绿。

回归保险：`tests/test_dx.py::test_runtime_logs_debug_at_execute_entry`。

### 6.2 验证 `YapiUsageWarning` 发与不发

发：

```python
with pytest.warns(YapiUsageWarning, match="YAPI_MODEL not set"):
    build_default_runner()
```

不发（必须用 `simplefilter("error")` 把 warning 转 error 才能检测）：

```python
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("error", YapiUsageWarning)
    runner = build_default_runner(model="openai:gpt-4o")    # 不会抛
```

`tests/test_dx.py::test_default_runner_no_warning_when_*` 系列遵循这个模板。

### 6.3 example 模块的请求期 smoke

`examples/wish_api` 等模块在 import 期就构造 `PromptRouter()`——单纯 `import examples.wish_api` 不会触发 LLM 调用，但 `YAPI_MODEL` 必须在 import 之前设好。`tests/test_router.py::test_example_application_imports` 用 `monkeypatch.setenv("YAPI_MODEL", "test")` + `importlib.reload(wish_api)` 强制重新导入应用同一份 env，是新增 example 模块时的复用模板。

## 7. CI 与 secrets

`.github/workflows/ci.yml` 在 push / PR 上跑 pytest 矩阵（Python 3.12 / 3.13）。**它不需要任何 secrets**——测试全部用 fake `agent_runner` 或 `YAPI_MODEL=test` 走 PydanticAI 的 `TestModel`。fork / 迁仓库时 CI 不需要任何配置就能绿。发布流程也无长期 API token，依赖 OIDC Trusted Publishing，详见 [`../guides/release.md`](../guides/release.md)。

CI 不跑 `tests/live/`——live tests 需要真实 provider 凭证（会烧 API quota 且 LLM 输出非确定），默认 skip 是有意为之。详见 §8。

## 8. Live tests：真实 LLM 端到端

`tests/live/`（v2.2 新增）下的测试**真实调用** PydanticAI 配置的 LLM provider（不再走 fake / TestModel），用于捕捉只能在真模型上暴露的回归——例如 prompt 拼接的语义破坏、`<context>` XML 边界被模型误读、tool_choice / structured output 兼容性退化等。

### 8.1 双重门控

`tests/live/conftest.py` 设两道门，**都过才跑**：

1. **`--run-live` CLI flag**：未传则全部 skip（保护离线 `uv run pytest` 与 CI）。
2. **`YAPI_MODEL` 真实 provider**：未设或字面量 `test` 时也 skip（避免与 TestModel 混在一起跑）。

### 8.2 运行命令

```bash
# 注入 .env（或任何含 YAPI_MODEL / OPENAI_API_KEY / OPENAI_BASE_URL 的来源）
set -a; source .env; set +a

# 仅跑 live
uv run pytest tests/live --run-live -v

# 离线全量 + 跳过 live（默认行为）
uv run pytest
# → 79 passed, 7 skipped
```

### 8.3 断言风格

LLM 输出非确定，断言原则：

- **schema 类**：`isinstance(data["granted"], bool)` / `assert resp.status_code == 200`——总是稳定。
- **强约束决策类**：响应模型 docstring 写死"当且仅当 X 时 Y"的规则 + 提供明确的事实（`ctx.add_section("User Profile", {"vip": true/false})`）→ 断言 `data["granted"] is True/False`。flake 时**先强化 prompt**，再考虑放宽断言。
- **片段透传类**：在 prompt 中要求模型"逐字回显代号/字段"（`ctx.add_kv("token", "HUMMINGBIRD-77")` + docstring 要求 echo verbatim）→ 断言 `token in resp.json()["message"]`。这种相对稳定，因为 LLM 复制字面量任务很可靠。

### 8.4 现有 7 条测试覆盖

| 测试 | 验证路径 |
|---|---|
| `test_live_minimal_route_returns_valid_response_model` | 基础 happy path：真模型返回符合 response_model schema 的 payload |
| `test_live_prompt_context_section_drives_decision` | `ctx.add_section` 注入的事实驱动 LLM 的 bool 决策（VIP vs 非 VIP） |
| `test_live_depends_data_reaches_model_via_prompt_context` | Depends 注入的 dict + `ctx.add_section` 链路完整 |
| `test_live_v21_return_str_still_reaches_model` | v2.1 `return "hint"` 兼容性：现在裹进 `<context>` 后仍正常到模型 |
| `test_live_async_def_route_works` | `async def` + `await func(**kwargs)` 真模型路径 |
| `test_live_annotated_query_param_reaches_model` | `Annotated[str, Query()]` 注入字段抵达 LLM |
| `test_live_multi_segment_prompt_context_all_reach_model` | `add_section + add_kv + add` 三种方法的片段全部进 prompt 且模型可读 |

成本参考：DeepSeek 上一轮全套约 10 秒、消耗 < 1k tokens，单次成本可忽略。
