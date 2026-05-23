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
| `examples.with_depends` | `Depends(fetch_profile)` 注入 + 路由函数返回 dynamic prompt | request body 与 `Depends` 解析结果都进 `injected`，dynamic prompt 段被拼到 system prompt 末尾 |
| `examples.custom_runner` | 自定义 `AgentRunner` Protocol 实现，无需 `YAPI_MODEL` | response message 含 `path=/wish method=POST prompt_chars=<N>`，演示 `RunnerContext` 字段可被 runner 直接消费 |

`wish_api / mixed_router / with_depends` 在 import 时会发 `YapiUsageWarning("YAPI_MODEL not set; ...")`——这是预期信号（spec §6.4），见 [`./error-catalog.md`](./error-catalog.md) §6 与 [`../must/project-shape.md`](../must/project-shape.md)。`custom_runner` 传了自定义 runner 不触发。

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
| `tests/test_integration.py` | Depends 注入到 `injected` / dynamic prompt 流到 runner / 非 str 返回值的请求期 500 |
| `tests/test_exports.py` | 公开符号 import smoke |
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
