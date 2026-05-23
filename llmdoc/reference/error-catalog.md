---
id: reference.error-catalog
title: 错误与警告目录
layer: reference
tags: [reference, errors, warnings, exceptions, yapi-usage-warning]
status: stable
---

# 错误与警告目录

固化 yapi 暴露的所有错误 / 警告类的层级、触发位置、示例消息。源文件：`yapi/errors.py`（10 行）。

## 1. 类层级

```
Exception
└── YapiError                          ← yapi 所有错误的根
    ├── YapiDeclarationError           ← 装饰期 / 构造期签名违反
    └── RuntimeExecutionError          ← 请求期执行失败（cause 携带）

UserWarning
└── YapiUsageWarning                   ← 装饰期 / 构造期不致命提示
```

四类全部从 `yapi` 包级 re-export（`yapi/__init__.py` `__all__`）：

```python
from yapi import (
    YapiError,
    YapiDeclarationError,
    RuntimeExecutionError,
    YapiUsageWarning,
)
```

## 2. `StateStoreError` 已物理删除

v1 残留 `yapi/errors.py::StateStoreError` 在 v2.1 已**物理删除**。`from yapi.errors import StateStoreError` 现在直接抛 `ImportError`，由 `tests/test_dx.py::test_state_store_error_removed` 守护。任何下游代码或文档仍引用该名都已失效。

## 3. `YapiDeclarationError` 触发清单

装饰期同步抛，import / `include_router` 阶段就暴露。

| 触发位置 | 示例消息片段 |
|---|---|
| `_register_prompt`：method 不在 `_HTTP_METHODS` 白名单 | `Unsupported HTTP method: <method>` |
| `_validate_prompt_kwargs`：命中 `_REJECTED_KWARGS` | `yapi prompt route '<path>' rejects kwarg '<name>': <reason>` |
| `_introspect`：缺返回注解 | `yapi prompt route '<func>' must declare a return type annotation` |
| `_introspect`：返回非 BaseModel | `yapi prompt route '<func>' must return a Pydantic BaseModel subclass` |
| `_introspect`：generator / async generator 函数 | `yapi prompt route '<func>' must return None or a str, not a generator` |
| `_introspect`：第二个 REQUEST_MODEL 参数 | `yapi prompt route '<func>' may declare at most one Pydantic request model parameter` |
| `_classify_param`：`*args` / `**kwargs` | `yapi prompt route '<func>' does not support *args/**kwargs (parameter '<name>')` |
| `_classify_param`：标量 Body | `yapi prompt route '<func>' parameter '<name>': Body(...) may only be used with a Pydantic BaseModel-typed parameter; use Query/Header/Cookie/Path/Form/File for scalar fields` |
| `_classify_param`：`Annotated[PromptContext, Marker]`（v2.2 起） | `yapi prompt route '<func>' parameter '<name>': PromptContext is auto-injected by yapi and must not carry FastAPI markers` |
| `_classify_param`：非 BaseModel / 非 Depends / 非 FastAPI marker | `yapi prompt route '<func>' has parameter '<name>' that is neither a Pydantic BaseModel, a Depends() dependency, nor a FastAPI Annotated marker (Query/Header/Cookie/Path/Form/File/Body)` |
| `_introspect`：第二个 `PROMPT_CONTEXT` 参数（v2.2 起） | `yapi prompt route '<func>' may declare at most one PromptContext parameter` |

完整装饰期错误分支汇总见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md) §6。

## 4. `_REJECTED_KWARGS` 三条拒绝原因

`yapi/router.py` `_REJECTED_KWARGS`：

| kwarg | 拒绝原因（错误消息内嵌） |
|---|---|
| `response_model` | `response_model is inferred from the return annotation; do not pass it` |
| `response_class` | `yapi controls the response class; do not pass response_class` |
| `dependencies` | `declare dependencies on the function signature with Depends(...), not as a route-level dependencies= kwarg` |

设计理由：这三个 kwarg 与 yapi 核心契约冲突——`response_model` 与"返回注解推断"撞车；`response_class` 由 yapi 决定 JSON 输出形态；route-level `dependencies=` 会绕过 `Runtime.injected` 数据通道，破坏 "request 与 injected 是两条独立数据通道" 不变量（详见 spec §4.1）。

## 5. `RuntimeExecutionError` 触发清单

请求期抛出，FastAPI 默认转 HTTP 500。错误消息**总是**形如 `f"Agent execution failed: {type(exc).__name__}: {exc}"` 或更具体的"用户函数返回错误"消息，`__cause__` 保留原 traceback。

| 触发位置 | 示例消息 |
|---|---|
| handler：用户函数返回非 None/非 str | `yapi prompt route '<func>' must return None or str, got <type>` |
| `PromptContext._format_value`：`ctx.add(None)` / `add_kv(_, None)` / `add_section(_, None)`（v2.2 起） | `PromptContext does not accept None; use an empty string if you want an empty segment.` |
| `Runtime.execute`：runner 抛任何异常 | `Agent execution failed: <ExcType>: <exc message>` |
| `Runtime.execute`：未设 `YAPI_MODEL` 的默认 runner 首次 `.run` | `Agent execution failed: RuntimeError: YAPI_MODEL is not set. Set YAPI_MODEL=test for an offline smoke test, ...` |

注意 `response_model.model_validate` 抛的 `ValidationError` **不**被包装为 `RuntimeExecutionError`——直接上抛由 FastAPI 转 500，先打 `WARNING` log（`response model_validate failed: <repr(exc)>`）。这是有意的"让 pydantic 报错原样向上"行为，方便对接现有 pydantic 错误处理中间件。

`PromptContext` 拒绝 `None` 抛 `RuntimeExecutionError` 这条**不经 `Runtime.execute` 包装层**——`_format_value` 在用户函数体内被同步调用，错误直接沿用户调用栈向上冒到 FastAPI 默认 500，与 v2.1 "动态 prompt 计算发生在 `Runtime.execute` 之前的 handler 层"立场一致。

## 6. `YapiUsageWarning` 触发清单

`YapiUsageWarning` 继承 `UserWarning`，由 `warnings.warn(..., category=YapiUsageWarning)` 触发。**不影响代码继续执行**，但默认 stderr 与 pytest 都会显示。

| 触发位置 | stacklevel | 示例消息 |
|---|---|---|
| `_validate_prompt_kwargs`：未识别 kwarg | `4` | `yapi: kwargs ['<name>', ...] are not recognized and will be ignored` |
| `build_default_runner`：未设 `YAPI_MODEL` 且 `model` 参数也未传 | `2` | `YAPI_MODEL not set; the first request to a prompt route will raise. Set YAPI_MODEL=test for an offline smoke test, or YAPI_MODEL=openai:gpt-4o etc. for real models.` |

cross-ref：未设 `YAPI_MODEL` 的 warning 是 `import examples.*` 时出现 warning 的根本原因，详见 [`../must/project-shape.md`](../must/project-shape.md) "关于"为什么 import example 就有 warning""段。

### 如何静音 / 抑制

- **测试中验证不发**：用 `warnings.catch_warnings()` + `warnings.simplefilter("error", YapiUsageWarning)` 把 warning 转 error，配合 `pytest.warns` 测发 / 不发。
- **真实启动忘记 `YAPI_MODEL` 时**：**不要静音**——这是 spec §6.4 要求的"真实启动期最早预警"。
- **示例 import 触发的 warning**：这是预期的；若 noise 干扰可以临时 `YAPI_MODEL=test python -m examples.wish_api` 启动。

## 7. 错误反馈时机速查

| 时机 | 错误类型 | 例子 |
|---|---|---|
| `@router.prompt.<method>(path, **kw)` 装饰器求值期 | `YapiDeclarationError` / `YapiUsageWarning` | 签名违反、kwarg 拒绝清单、未识别 kwarg |
| `PromptRouter()` 构造期 | `YapiUsageWarning` / `TypeError` | `YAPI_MODEL` 未设；`agent_runner` 不是 callable 也无 `.run` |
| `include_router(...)` 期 | （继承装饰器期抛错） | 同上 |
| 请求期 | `RuntimeExecutionError` → HTTP 500 | runner 抛错、用户函数返回非法、`YAPI_MODEL` 缺失首次请求 |
| 请求期 | `pydantic.ValidationError` → HTTP 500（不被包装） | `response_model.model_validate(payload)` 失败 |

完整错误分支汇总见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md) §6；测试范式见 [`./run-and-test.md`](./run-and-test.md)。
