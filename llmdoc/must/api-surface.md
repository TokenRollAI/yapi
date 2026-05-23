---
id: must.api-surface
title: PromptRouter 对外契约
layer: must
tags: [must, api, contract, declarative, apirouter, annotated]
status: stable
---

# PromptRouter 对外契约

`PromptRouter`（`yapi/router.py` (`PromptRouter`)）是 `fastapi.APIRouter` 的**真超集**：

- 原生 `.get/.post/.put/.patch/.delete` 是普通 FastAPI 路由通道（**不**经过 yapi 内省，不调用 `agent_runner`）。
- prompt 路由收敛到 `router.prompt.{get,post,put,patch,delete}` 五个装饰器；这才是 yapi 接管的入口。
- 同一个 `PromptRouter` 实例上**允许并鼓励**普通路由与 prompt 路由混挂（见 `examples/mixed_router.py`）。

完整执行链路见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md)。本文只固化"开发者必须遵守的硬约束"。

## prompt 装饰器表面

- 入口：`@router.prompt.<method>(path, **kwargs)`，由 `_PromptDecorators` 派发到 `PromptRouter._register_prompt`。
- 白名单 method：`("GET", "POST", "PUT", "PATCH", "DELETE")`（`yapi/router.py` `_HTTP_METHODS`）。该常量只在 `_register_prompt` 内部被检查，五个 `.prompt.<method>` 之外的方法（`OPTIONS / HEAD / TRACE`）通过原生 APIRouter 路径仍然可挂，只是不会进 prompt 管线。
- 装饰器**只**接受一个 path positional 参数 + kwargs，kwarg 走三档处理（见下节）。

## kwargs 三档处理

`yapi/router.py` (`_validate_prompt_kwargs`)：

| 档位 | 触发条件 | 行为 |
|---|---|---|
| **透传白名单**（`_PASSTHROUGH_KWARGS`） | `tags / summary / description / status_code / deprecated / operation_id / name / include_in_schema / responses / openapi_extra` | 原样透传给 `add_api_route` |
| **拒绝清单**（`_REJECTED_KWARGS`） | `response_model / response_class / dependencies` | 装饰期同步抛 `YapiDeclarationError`，错误消息含拒绝理由 |
| **未识别 kwarg** | 上面两档之外的任何 kwarg | 装饰期 `warnings.warn(..., YapiUsageWarning, stacklevel=4)`，kwarg 被忽略 |

拒绝理由：`response_model=` 与"从返回注解推断"冲突；`response_class=` 由 yapi 控制；`dependencies=` 会绕过 `Runtime.injected` 数据通道，应改写为函数签名上的 `Depends(...)`。

`YapiUsageWarning` 继承 `UserWarning`，从 `yapi` 直接 re-export。完整错误层级与触发位置见 [`../reference/error-catalog.md`](../reference/error-catalog.md)。

## 构造签名

```python
PromptRouter(
    agent_runner: AgentRunner | Callable | None = None,
    prompt_composer: PromptComposer | None = None,
    **apirouter_kwargs,
)
```

- `agent_runner=None`：调用 `build_default_runner()`（读 `YAPI_MODEL`，未设置时构造期发 `YapiUsageWarning`）。详见 [`./project-shape.md`](./project-shape.md) 的 `YAPI_MODEL` 段。
- `agent_runner=<obj>`：可以是任何"有 `.run(ctx)` 方法的对象"（Protocol 鸭子类型），也可以是 v2 风格 `lambda **_: {...}`，后者由 `_LegacyCallableRunner` 适配。Protocol 与 `RunnerContext` 契约见 [`../architecture/agent-runner-contract.md`](../architecture/agent-runner-contract.md)。
- `prompt_composer=`：可注入的 `(endpoint, dynamic_prompt) -> str` 函数，默认 `compose_prompt`。
- `**apirouter_kwargs`：原样透传到 `APIRouter.__init__`（`prefix / tags / dependencies / default_response_class / ...`）。这些 router 级别配置同时影响原生路由与 prompt 路由。

## 函数签名推断契约

定义在 `yapi/router.py` (`_introspect`) + (`_classify_param`)。装饰期同步抛 `YapiDeclarationError`，应用 import / startup 即失败。详细分类规则与 Annotated 内省协议见 [`../reference/annotated-introspection.md`](../reference/annotated-introspection.md)。

### 返回注解硬约束

- **必须**有返回注解：`def f(...)` 不允许。
- 返回注解**必须**是 `BaseModel` 子类：`-> dict` / `-> str` / `-> Optional[WishOut]` 都不允许。
- 该类的 `__doc__` 会被纳入 system prompt。

### 函数形态硬约束

- `def` 与 `async def` 都允许；handler 内用 `inspect.iscoroutinefunction(func)` 分支决定是否 `await`。
- 生成器 / 异步生成器（`def f(): yield` 或 `async def f(): yield`）→ 装饰期 `YapiDeclarationError("... must return None or a str, not a generator")`。
- `*args` / `**kwargs` → 装饰期 `YapiDeclarationError("... does not support *args/**kwargs")`。

### 参数四分类（`ParamRole`）

按声明顺序遍历，每个参数被 `_classify_param` 分到三类之一（外加 REQUEST_MODEL 是其中一类）：

1. **`REQUEST_MODEL`**：annotation（去 Annotated 外层后）是 `BaseModel` 子类。允许形态：
   - 裸 BaseModel：`req: WishIn`
   - `Annotated[WishIn, Body(...)]` / `Annotated[WishIn, Body(embed=True)]`
   - **最多一个**；第二个 REQUEST_MODEL 参数抛 `YapiDeclarationError("may declare at most one Pydantic request model parameter")`。
2. **`DEPENDENCY`**：`default` 是 `fastapi.params.Depends`，或 Annotated metadata 含 `Depends(...)`。允许 `Annotated[T, Depends(...)]` 形态。
3. **`INJECTED_FIELD`**：`default` 或 Annotated metadata 是 `fastapi.params.{Query,Header,Cookie,Path,Form,File}` 实例之一（`_INJECTED_FIELD_TYPES`）。

任何不匹配上述分类的参数（包括 `q: str` 裸标量、`q: int = 0` 默认值标量、`q: str = Body(...)` 标量 Body）都装饰期报错。**`Body(...)` 只允许配合 BaseModel 参数使用**，非 BaseModel 配 `Body` 抛 `YapiDeclarationError("Body() may only annotate a Pydantic BaseModel-typed parameter")`。

### handler `__signature__` 不可剥 Annotated

handler 闭包的 `__signature__` 必须**原样**复用用户函数的 `inspect.Parameter`（含 `Annotated[T, marker]` 元数据），否则 FastAPI 无法做请求体 / Query / Header 等解析。详见 [`../reference/annotated-introspection.md`](../reference/annotated-introspection.md)。

## 动态 prompt 契约

用户函数在请求期被 handler 闭包调用：

- `def` → `func(**kwargs)` 同步调用。
- `async def` → `await func(**kwargs)`（v2.1 新增；v2 不支持 async def）。

返回值**只能**是 `None` 或 `str`：

- `None`（包括无 `return`）：合法，无动态段。
- `str`：作为动态 prompt 段拼到 system prompt 末尾。空串等同无段（`if dynamic_prompt` 为假）。
- 其他任意值（`int / dict / BaseModel / 0 / False / [...]`）→ handler 内抛 `RuntimeExecutionError("... must return None or str, got <type>")`，FastAPI 转 HTTP 500。

用户函数可从 kwargs 拿到完整的 request_model 实例与 Depends / 注入字段解析结果，用于拼接 dynamic prompt。

## 用户原函数不被绑定

装饰器**返回 `func` 原物**，FastAPI 真正调用的是闭包内的 `handler`。用户仍可在模块外直接调用原函数。`add_api_route` 通过给 `handler.__signature__` 还原原签名让 FastAPI 内省（请求体解析、OpenAPI 生成）保持正常。

## 错误反馈时机

- **装饰期 `YapiDeclarationError`**：所有签名违反与 kwarg 拒绝清单命中在 import / `include_router` 阶段就暴露。
- **装饰期 `YapiUsageWarning`**：未识别 kwarg 与默认 runner 在未设置 `YAPI_MODEL` 时构造期触发。不影响代码继续执行。
- **请求期 `RuntimeExecutionError`**：动态 prompt 非法、agent_runner 抛错、`YAPI_MODEL` 未设置等。错误消息包含原始异常的 `repr`（`f"Agent execution failed: {type(exc).__name__}: {exc}"`），`__cause__` 仍保留原 traceback。

完整错误目录见 [`../reference/error-catalog.md`](../reference/error-catalog.md)。
