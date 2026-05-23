---
id: architecture.request-lifecycle
title: 请求生命周期
layer: architecture
tags: [architecture, lifecycle, runtime, fastapi, introspection, paramrole, annotated]
status: stable
---

# 请求生命周期：从 `@router.prompt.post(...)` 到 JSON 响应

本文档串清楚 yapi 全部执行模型，覆盖**装饰期**与**请求期**两段。所有不变量和边界都在这里集中。

## 0. 关键组件清单

- `yapi/router.py` (`PromptRouter`)：开发者入口，**继承 `fastapi.APIRouter` 但不再覆盖原生 `.get/.post/...`**；持有 `Runtime` 与 `_PromptDecorators` 实例。
- `yapi/router.py` (`_PromptDecorators`)：`router.prompt` 子命名空间的实现，把 5 个方法派发到 `_register_prompt`。
- `yapi/router.py` (`_register_prompt`)：prompt 路由注册入口，校验 method 白名单、kwarg 三档处理、调用 `_introspect`、构造 handler 闭包、`add_api_route`。
- `yapi/router.py` (`_classify_param`) + (`ParamRole`)：参数 4 分类（`REQUEST_MODEL / DEPENDENCY / INJECTED_FIELD / PROMPT_CONTEXT`）。
- `yapi/router.py` (`_introspect`)：返回 `(request_model, response_model, param_roles, request_param_name, ctx_param_name)`（v2.2 5-tuple）。
- `yapi/router.py` (`_validate_prompt_kwargs`)：kwarg 三档处理（透传白名单 / 拒绝清单 / `YapiUsageWarning`）。
- `yapi/router.py` (`_unwrap_annotated`) + (`_is_prompt_context_type`)：Annotated 内省 helper + PromptContext 类型检测；详见 [`../reference/annotated-introspection.md`](../reference/annotated-introspection.md)。
- `yapi/prompt_context.py` (`PromptContext`) + (`_format_value`)：自动注入的 prompt 增量收集器，三方法表面 `add / add_kv / add_section`；详见 [`../reference/prompt-context.md`](../reference/prompt-context.md)。
- `yapi/endpoint.py` (`PromptEndpoint`)：frozen dataclass，封装一条路由的全部静态信息。
- `yapi/runner.py` (`AgentRunner`) + (`RunnerContext`) + (`_LegacyCallableRunner`) + (`_coerce_runner`)：runner Protocol、上下文对象、v2 callable 兼容适配；详见 [`./agent-runner-contract.md`](./agent-runner-contract.md)。
- `yapi/runtime.py` (`Runtime`)：执行引擎，持有 `_agent_runner` 与 `_compose_prompt`；module-level `logger = logging.getLogger("yapi.runtime")`。
- `yapi/runtime.py` (`compose_prompt`) / (`DEFAULT_SYSTEM_PREFIX`) / (`_adapt_composer`)：system prompt 拼接（v2.2 起新签名 `(endpoint, prompt_context, dynamic_prompt) -> str`，外裹 `<context>` XML 边界）；可被 `prompt_composer` 注入点覆盖，`_adapt_composer` 兼容旧 2-arg 签名。
- `yapi/models.py` (`RuntimeContext`)：非 frozen dataclass，仅 `request` / `injected` 两段 dict。
- `yapi/agent.py` (`PydanticAIRunner`) + (`build_default_runner`)：默认 runner 类化实现 + 工厂；`build_agent_runner` 为别名。

## 1. 装饰期（应用启动 / import 时）

以 `examples/wish_api.py` 为例：

```python
router = PromptRouter()

@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""
```

### 1.1 `PromptRouter.__init__`

```python
def __init__(self, agent_runner=None, prompt_composer=None, **apirouter_kwargs):
    super().__init__(**apirouter_kwargs)
    self._runtime = Runtime(
        agent_runner=agent_runner if agent_runner is not None else build_default_runner(),
        prompt_composer=prompt_composer,
    )
    self.prompt = _PromptDecorators(self)
```

要点：

- **不再覆盖**原生 `.get/.post/.put/.patch/.delete`，APIRouter 的所有原生行为保留。
- `**apirouter_kwargs` 透传到 `APIRouter.__init__`（`prefix / tags / dependencies / default_response_class / ...`），router 级别配置同时影响原生路由与 prompt 路由。
- `agent_runner=None` 时调用 `build_default_runner()`，未设 `YAPI_MODEL` 会同步发 `YapiUsageWarning`——这是 spec §6.4 要求的"真实启动期最早预警"。
- `Runtime.__init__` 调用 `_coerce_runner(agent_runner)`：有 `.run` 属性的对象走鸭子类型，callable 包成 `_LegacyCallableRunner`，否则 `TypeError`。

### 1.2 装饰器调用链

`router.prompt.post("/wish")` → `_PromptDecorators.post` → `PromptRouter._register_prompt("POST", "/wish", **kwargs)` → 返回 `decorator`。

`_register_prompt` 先校验 method 在 `_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")` 白名单内，否则抛 `YapiDeclarationError("Unsupported HTTP method: ...")`；然后 `_validate_prompt_kwargs(path, kwargs)` 做 kwarg 三档处理（见 §1.3）；最后返回内层 `decorator(func)` 闭包。

注意：v2 的 `_register` 名字已删除；prompt 路由的统一入口是 `_register_prompt`。

### 1.3 kwarg 三档处理

`yapi/router.py` (`_validate_prompt_kwargs`)：

1. 遍历 `_REJECTED_KWARGS`（`response_model / response_class / dependencies`），命中即抛 `YapiDeclarationError(f"yapi prompt route '{path}' rejects kwarg '{rejected}': {reason}")`。
2. 收集"既不在白名单也不在拒绝清单"的 kwarg，按字典序排序后 `warnings.warn(f"yapi: kwargs {unknown} are not recognized and will be ignored", YapiUsageWarning, stacklevel=4)`。
3. 返回 `_PASSTHROUGH_KWARGS` 过滤后的 dict，原样传给 `add_api_route`。

完整 kwarg 表见 [`../must/api-surface.md`](../must/api-surface.md) "kwargs 三档处理"段。

### 1.4 `_introspect` + `_classify_param`（签名内省）

`_introspect(func)` 工作流：

1. 取 `inspect.signature(func)`。
2. **返回注解检查**：
   - 缺注解 → `YapiDeclarationError("must declare a return type annotation")`。
   - 不是 `BaseModel` 子类 → `YapiDeclarationError("must return a Pydantic BaseModel subclass")`。
3. **生成器形态检查**：`inspect.isgeneratorfunction(func)` 或 `inspect.isasyncgenfunction(func)` → `YapiDeclarationError("... must return None or a str, not a generator")`。
4. **参数遍历**：对每个 `inspect.Parameter` 调 `_classify_param(name, param, func.__name__)`，结果记入 `param_roles: dict[str, ParamRole]`：
   - REQUEST_MODEL 同时记入 `request_model` + `request_param_name`（已有则 `YapiDeclarationError("may declare at most one ...")`）。
   - PROMPT_CONTEXT 同时记入 `ctx_param_name`（已有则 `YapiDeclarationError("may declare at most one PromptContext parameter")`）。
5. 返回 5-tuple `(request_model, response_model, param_roles, request_param_name, ctx_param_name)`（v2.2 起；v2.1 是 4-tuple，无 ctx）。

`_classify_param` 的匹配顺序（先匹配先生效）：

1. `param.kind` 是 `VAR_POSITIONAL / VAR_KEYWORD` → `YapiDeclarationError("does not support *args/**kwargs")`。
2. **PromptContext 检测（v2.2 新增，必须先于 `_unwrap_annotated`）**：
   - 裸 `annotation` 是 `PromptContext`（或其子类）→ `PROMPT_CONTEXT`。
   - `_unwrap_annotated` 后 base 是 `PromptContext` 且 metadata 非空 → `YapiDeclarationError("PromptContext is auto-injected by yapi and must not carry FastAPI markers")`。
3. **读 `param.default`**：
   - 是 `params.Depends` 实例 → `DEPENDENCY`。
   - 是 `_INJECTED_FIELD_TYPES`（`Query / Header / Cookie / Path / Form / File`）实例 → `INJECTED_FIELD`。
   - 是 `params.Body` 实例：base annotation 是 BaseModel → `REQUEST_MODEL`；否则报错"Body(...) may only be used with a Pydantic BaseModel-typed parameter"。
4. **读 Annotated metadata**（`_unwrap_annotated`）：按顺序找 `Depends / Body / Query/Header/Cookie/Path/Form/File` 标记，命中规则同上。
5. **base annotation 是 BaseModel 子类** → `REQUEST_MODEL`。
6. 都不匹配 → `YapiDeclarationError("neither a Pydantic BaseModel, a Depends() dependency, nor a FastAPI Annotated marker ...")`。

**关键不变量**：
- `isinstance(default, params.Body)` 必须在 `params.Param`（覆盖 6 个注入字段类型）之前判断，因为 `Body` 与 `Param` 在 `fastapi.params` 中是兄弟而非父子。详见 [`../reference/annotated-introspection.md`](../reference/annotated-introspection.md)。
- PromptContext 检测必须**先于** `_unwrap_annotated`，否则裸 `ctx: PromptContext` 与 `Annotated[PromptContext, ...]` 不可区分（后者要报错）。

### 1.5 构造 `PromptEndpoint`

```python
endpoint = PromptEndpoint(
    path=path,
    method=upper,
    request_model=request_model,       # 已 _unwrap_annotated 取 base type
    response_model=return_annotation,
    function_doc=(func.__doc__ or "").strip(),
)
```

`PromptEndpoint` 是 `@dataclass(frozen=True)`（`yapi/endpoint.py`），承载路由"静态描述"。属性 `response_doc` 返回 `response_model.__doc__` 的 strip 结果。

### 1.6 构造异步 handler 闭包

```python
is_async = inspect.iscoroutinefunction(func)
original_signature = inspect.signature(func)
original_params = list(original_signature.parameters.values())

async def handler(**kwargs):
    injected = {}
    request_instance = None
    ctx = PromptContext() if ctx_param_name else None

    for name, role in param_roles.items():
        if name == ctx_param_name:
            continue                              # ctx 不进 kwargs（已从 __signature__ 过滤）
        if name not in kwargs:
            continue
        if role is ParamRole.REQUEST_MODEL:
            request_instance = kwargs[name]
        else:                                     # DEPENDENCY + INJECTED_FIELD
            injected[name] = kwargs[name]

    user_kwargs = dict(kwargs)
    if ctx_param_name is not None:
        user_kwargs[ctx_param_name] = ctx         # 把新建的 ctx 插回去交给用户函数

    if is_async:
        dynamic_prompt = await func(**user_kwargs)
    else:
        dynamic_prompt = func(**user_kwargs)

    if dynamic_prompt is not None and not isinstance(dynamic_prompt, str):
        raise RuntimeExecutionError(
            f"yapi prompt route '{func.__name__}' must return None or str, "
            f"got {type(dynamic_prompt).__name__}"
        )

    return await run_in_threadpool(
        self._runtime.execute,
        endpoint=endpoint,
        request_model=request_instance,
        injected=injected,
        prompt_context=ctx,                       # v2.2 新增
        dynamic_prompt=dynamic_prompt,
    )
```

要点：

- handler 接受 `**kwargs`，不直接声明参数；FastAPI 按 `__signature__` 注入（**ctx 参数已被过滤**，FastAPI 看不到）。
- `param_roles` 决定 kwargs 分流：`REQUEST_MODEL` 进 `request_instance`，`DEPENDENCY + INJECTED_FIELD` 合并进 `injected` dict，`PROMPT_CONTEXT` 既不进 `injected` 也不进 `request_instance`——单独新建实例放进 `user_kwargs` 交给用户函数。这是"用 dict 区分独立数据通道"的设计，agent_runner 看到的 `injected` 形如 `{"profile": {...}, "x_token": "abc", "user_id": "u-7"}`。
- `is_async` 与 `ctx_param_name` 在装饰期一次性算好；请求期不再走 `iscoroutinefunction` 检查。
- 用户函数错误地返回非 None/str → handler 内立即 `RuntimeExecutionError`，错误消息含返回值类型名。
- 用户函数内 `await` 抛错（如 `httpx.ConnectError`）直接向上冒，不会被 `RuntimeExecutionError` 包装——属"用户代码错误"，让 FastAPI 默认 500 + 干净 traceback。
- 用户函数内 `ctx.add(None)` 抛 `RuntimeExecutionError` 也是这条同路径——`_format_value` 同步抛，沿用户调用栈冒出。

### 1.7 `__signature__` 修补（过滤 PROMPT_CONTEXT）

```python
fastapi_visible_params = [
    p for p in original_params
    if param_roles.get(p.name) is not ParamRole.PROMPT_CONTEXT
]
handler.__signature__ = inspect.Signature(
    parameters=fastapi_visible_params,           # 含 Annotated metadata，但不含 ctx 参数
    return_annotation=response_model,
)
handler.__annotations__ = {
    p.name: p.annotation
    for p in fastapi_visible_params
    if p.annotation is not inspect.Parameter.empty
}
handler.__annotations__["return"] = response_model
handler.__name__ = func.__name__
handler.__doc__ = func.__doc__
```

**两条硬约束**：

1. `fastapi_visible_params` 复用 `inspect.signature(func).parameters.values()`，**不剥 Annotated 也不丢 default**——FastAPI body / query / header 解析全靠 `Annotated[T, marker]` 元数据驱动。
2. **PROMPT_CONTEXT 参数从 `__signature__` 与 `__annotations__` 中剔除**（v2.2 起）——若不过滤，FastAPI 会试图把 `ctx: PromptContext` 当 query / body 解析并失败；同时 OpenAPI schema 也不会出现 `PromptContext` 字段。

回归保险：`tests/test_router.py::test_prompt_handler_signature_preserves_annotated`（Annotated 保留）+ `::test_router_prompt_context_not_in_openapi`（ctx 不在 OpenAPI 中）。详见 [`../reference/annotated-introspection.md`](../reference/annotated-introspection.md)。

### 1.8 `add_api_route` + 装饰器返回

```python
logger.debug("registering prompt route method=%s path=%s handler=%s async=%s", ...)
self.add_api_route(path, handler, methods=[upper], response_model=response_model, **passthrough)
return func
```

装饰器**返回用户原函数**而不是 handler。FastAPI 真正调用的是闭包内的 `handler`，但用户仍可在模块外直接调用原函数。`response_model=` 显式传入，FastAPI 据此生成 OpenAPI schema 并做响应阶段的二次序列化。

## 2. `app.include_router(router)`

FastAPI 把 `router.routes` 复制进 `app.routes`，路由真正生效。原生 FastAPI 行为，yapi 不介入。注意原生 `router.get(...)` 注册的路由与 `router.prompt.post(...)` 注册的路由**都落在同一个 `router.routes` 列表上**——OpenAPI 与 prefix / tags 共享。

## 3. 请求期

客户端 `POST /wish {"user_id": "u-1", "wish": "moon"}`：

### 3.1 FastAPI 解析

FastAPI 按 `handler.__signature__` 解析请求：

- 看到 `req: WishIn` 或 `req: Annotated[WishIn, Body()]` → 用 `WishIn` 校验请求体。
- 看到 `Depends(...)` / `Annotated[T, Depends(...)]` → 解析对应依赖。
- 看到 `Annotated[str, Query()/Header()/Cookie()/Path()/Form()/File()]` 或 `= Query(...)` 等 default → FastAPI 按对应来源解析。

handler 是 `async def`，FastAPI 直接 `await handler(req=..., q=..., x_token=..., ...)`。

### 3.2 handler 内部

参见 1.6 节代码。重点：

- `dynamic_prompt = func(**kwargs)` 或 `await func(**kwargs)` 取决于装饰期算好的 `is_async`。
- 类型守卫：非 None 非 str → `RuntimeExecutionError`。空串等同无段（`compose_prompt` 内 `if dynamic_prompt` 为假）。
- 通过 `run_in_threadpool` 把同步的 `Runtime.execute` 卸到 starlette/anyio 的工作线程池——因为 `PydanticAIRunner.run` 最终调用 `agent.run_sync(...)`（阻塞 API），不能在事件循环里直接跑。自定义 runner 的 `.run` 也按 sync 处理。
- **隐含性能特性**：每个请求会占用一个工作线程直到 LLM 返回，线程池大小是 yapi 的可见并发上限。

### 3.3 `Runtime.execute`

`yapi/runtime.py` (`Runtime.execute`)：

```python
request_data = {} if request_model is None else request_model.model_dump()
context = self.build_context(request_data, injected)
prompt = self._compose_prompt(endpoint, prompt_context, dynamic_prompt)  # v2.2 新签名

logger.debug("execute path=... method=... has_request_model=... injected_keys=...")
logger.debug("prompt composed prompt_length=... sections=...")

ctx = RunnerContext(
    prompt=prompt, request=context.request, injected=context.injected,
    response_model=endpoint.response_model, path=endpoint.path, method=endpoint.method,
)

logger.debug("invoking runner=%s", type(self._agent_runner).__name__)
try:
    payload = self._agent_runner.run(ctx)
except Exception as exc:
    logger.warning("runner failed: %r", exc)
    raise RuntimeExecutionError(f"Agent execution failed: {type(exc).__name__}: {exc}") from exc

if isinstance(payload, endpoint.response_model):
    return payload                               # 快路径，省一次 model_validate
try:
    return endpoint.response_model.model_validate(payload)
except Exception as exc:
    logger.warning("response model_validate failed: %r", exc)
    raise
```

关键点：

- request 没有 BaseModel 参数时（GET 等）`request_data = {}`，`injected` 同理可能为 `{}`。
- `build_context` 用 `dict(request_data)` / `dict(injected)` 做**浅拷贝**塞进 `RuntimeContext`（非 frozen）。
- `self._compose_prompt` 可被 `prompt_composer=` 注入点替换；默认是 v2.2 的 3-arg `compose_prompt`。v2.1 形态 `(endpoint, dynamic_prompt) -> str` 的旧 composer 由 `_adapt_composer` 包一层，请求期先按 3-arg 尝试，失败（TypeError）后回退到 2-arg。
- runner 通过 `.run(ctx)` 调用；`ctx` 是 `RunnerContext` frozen dataclass，含 `path / method`，方便自定义 runner 做 tracing / 多模型路由。
- **agent_runner 抛任何异常都被包装为 `RuntimeExecutionError(f"Agent execution failed: {type(exc).__name__}: {exc}") from exc`**——错误消息含 cause 摘要，调试时 `str(exc)` 即可看出原始类型与消息，`__cause__` 仍保留完整 traceback。
- `isinstance(payload, endpoint.response_model)` 快路径：如果 runner 直接返回 BaseModel 实例就跳过二次 `model_validate`。
- `model_validate` 失败抛出的 `ValidationError` **没有**被 yapi 捕获，由 FastAPI 转 HTTP 500，但 `WARNING` 日志会先打出。

### 3.4 `compose_prompt` 的拼接顺序（v2.2 起含 `<context>` 外裹）

`yapi/runtime.py` (`compose_prompt`)：

```python
sections = [DEFAULT_SYSTEM_PREFIX]
if endpoint.response_doc: sections.append(endpoint.response_doc)
if endpoint.function_doc: sections.append(endpoint.function_doc)

ctx_segments = list(prompt_context.segments()) if prompt_context else []
if dynamic_prompt:
    ctx_segments.append(dynamic_prompt)
if ctx_segments:
    body = "\n\n".join(ctx_segments)
    sections.append(f"<context>\n{body}\n</context>")

return "\n\n".join(sections)
```

顺序固定（**空段直接跳过**）：

1. **`DEFAULT_SYSTEM_PREFIX`**（永远存在）：`"You are the execution engine behind a declarative HTTP endpoint. Return data that strictly matches the required response model."`。
2. **`response_model.__doc__`**（通过 `endpoint.response_doc`）。
3. **`endpoint.function_doc`**。
4. **`<context>...</context>`**（v2.2 起）：内含按 `ctx.add*` 调用顺序的所有片段 + 末尾追加的 `dynamic_prompt`（若非空 str），段间用 `\n\n`。**只要至少有一个 segment 就出现**；ctx 无任何 add 且 dynamic_prompt 也无时整段省略。

段间用 `"\n\n"` 拼接。该函数可被 `PromptRouter(prompt_composer=<callable>)` 替换；v2.2 起新签名 `(endpoint, prompt_context, dynamic_prompt) -> str`，v2.1 旧 2-arg 形态由 `_adapt_composer` 兼容。

**v2.1 → v2.2 user-visible 破坏点**：v2.1 路由 `return "hint"` 在 system prompt 中的形态从"末尾追加 `\n\nhint`"变成"末尾追加 `\n\n<context>\nhint\n</context>`"。绝大多数 prompt 对 XML 边界鲁棒，无需迁移；但若用户 prompt 含字面"看 prompt 末尾的一段话"这种位置依赖措辞需重述为"看 `<context>` 内的内容"。

### 3.5 agent runner 调用

详细契约见 [`./agent-runner-contract.md`](./agent-runner-contract.md)。

## 4. logging 通道

v2.1 起框架在关键节点打 log，**不**调 `logging.basicConfig`，不污染用户日志栈：

| logger | 级别 | 位置 | 内容 |
|---|---|---|---|
| `yapi.router` | DEBUG | `_register_prompt` 内 `add_api_route` 之前 | `registering prompt route method=... path=... handler=... async=...` |
| `yapi.runtime` | DEBUG | `Runtime.execute` 进入 | `execute path=... method=... has_request_model=... injected_keys=...` |
| `yapi.runtime` | DEBUG | `compose_prompt` 完成 | `prompt composed prompt_length=... sections=...`（**不打 prompt 内容**，避免日志泄露） |
| `yapi.runtime` | DEBUG | runner 调用前 | `invoking runner=<type>` |
| `yapi.runtime` | WARNING | runner 抛错 | `runner failed: <repr(exc)>` |
| `yapi.runtime` | WARNING | `model_validate` 失败 | `response model_validate failed: <repr(exc)>` |

pytest 中抓 `yapi.runtime` DEBUG log **必须** `caplog.at_level(logging.DEBUG, logger="yapi.runtime")` 双指定，详见 [`../reference/run-and-test.md`](../reference/run-and-test.md)。

## 5. 不变量清单

下列条件在当前实现下恒成立，可作为未来重构的护栏：

1. **`PromptEndpoint` 装饰期冻结**（frozen dataclass）；请求期不变更。
2. **用户函数原物保留**：装饰器返回 `func` 本身；FastAPI 调用的是 handler 闭包。
3. **handler 永远是 async**；同步 `Runtime.execute` 通过 `run_in_threadpool` 卸载。
4. **`Runtime.execute` 接口向后兼容**：v2.2 起新签名 `(endpoint, request_model, injected, dynamic_prompt, prompt_context=None) -> BaseModel`，`prompt_context` 是可选 keyword 参数，旧调用方仍可工作；内部组装 `RunnerContext` 是实现细节。
5. **响应永远是 BaseModel 实例**：`isinstance` 快路径或 `model_validate` 保证类型。
6. **agent_runner 入参形式**：`.run(ctx: RunnerContext)`；返回 `dict | BaseModel`。v2 风格 4-keyword callable 由 `_LegacyCallableRunner` 翻译。
7. **`request` 与 `injected` 是两条独立数据通道**；REQUEST_MODEL 不会进 `injected`，DEPENDENCY/INJECTED_FIELD 不会进 `request`，PROMPT_CONTEXT 既不进 `injected` 也不进 `request`。
8. **声明错误同步抛**：所有签名违反 + kwarg 拒绝清单命中在 import / `include_router` 阶段就暴露。
9. **handler `__signature__` 原样保留 Annotated**，base type / default 都不剥；唯一例外是 `ParamRole.PROMPT_CONTEXT` 参数被剔除（v2.2 起）。
10. **`PromptRouter.<原生 method>` 走 FastAPI 原生通道**，不经过 `_runtime`、不调用 `agent_runner`。
11. **`PromptContext` 严格请求局部**（v2.2 起）：每次请求新建实例，不跨请求、不共享；纯 append-only，无 mutation API；段序与调用序一致。
12. **`<context>...</context>` 是唯一的 prompt 增量边界**（v2.2 起）：所有 ctx 片段 + `return str` 动态段被统一外裹；无任何段时整段省略。RunnerContext 看到的仍只是已经拼装好的 `prompt: str`。

## 6. `_introspect` / `_classify_param` / `_register_prompt` 报错分支汇总

| 触发条件 | 错误消息片段 | 错误期 |
|---|---|---|
| HTTP method 不在白名单 | `Unsupported HTTP method: ...` | 装饰期 |
| kwarg 命中拒绝清单 | `rejects kwarg '...'` | 装饰期 |
| 缺返回注解 | `must declare a return type annotation` | 装饰期 |
| 返回非 BaseModel | `must return a Pydantic BaseModel subclass` | 装饰期 |
| 生成器 / 异步生成器函数 | `must return None or a str, not a generator` | 装饰期 |
| 第二个 REQUEST_MODEL 参数 | `may declare at most one Pydantic request model parameter` | 装饰期 |
| `*args` / `**kwargs` | `does not support *args/**kwargs` | 装饰期 |
| 标量 Body（`Body()` default 或 Annotated metadata） | `Body() may only ... use Query/Header/Cookie/Path/Form/File for scalar fields` | 装饰期 |
| 非 BaseModel / 非 Depends / 非 FastAPI marker 的参数 | `neither a Pydantic BaseModel, a Depends() dependency, nor a FastAPI Annotated marker` | 装饰期 |
| `Annotated[PromptContext, Marker]`（带 FastAPI marker） | `PromptContext is auto-injected by yapi and must not carry FastAPI markers` | 装饰期 |
| 第二个 `PROMPT_CONTEXT` 参数 | `may declare at most one PromptContext parameter` | 装饰期 |
| 用户函数返回非 None/非 str | `must return None or str, got <type>` | 请求期 `RuntimeExecutionError` |
| `ctx.add(None) / add_kv(_, None) / add_section(_, None)` | `PromptContext does not accept None; use an empty string if you want an empty segment.` | 请求期 `RuntimeExecutionError`（沿用户调用栈向上冒，不被 `Runtime.execute` 包装） |
| runner 抛任何异常 | `Agent execution failed: <type>: <msg>` | 请求期 `RuntimeExecutionError` |
| `model_validate` 失败 | `ValidationError`（不包装） | 请求期 → HTTP 500，warning 先打 |

未识别 kwarg 不抛错而是 `YapiUsageWarning`，见 §1.3。

## 7. 反例与边界用例速查

- 写 `-> dict` / `-> str` / 缺返回注解 → import 期 `YapiDeclarationError`。
- 写两个 BaseModel 参数（含 `Annotated[T, Body()]` 第二份）→ import 期 `YapiDeclarationError`。
- 写 `q: str = Query(...)` 或 `q: Annotated[str, Query()]` → **合法**，进 `injected` 通道。
- 写 `Annotated[WishIn, Body(...)]` 或 `Annotated[WishIn, Body(embed=True)]` → **合法**，识别为 REQUEST_MODEL。
- 写 `q: str = Body(...)` / `Annotated[str, Body()]`（标量 Body） → import 期 `YapiDeclarationError`，引导改用 Query/Header/...。
- 写裸 `q: str` 无 default → import 期 `YapiDeclarationError`，明确拒绝 FastAPI 隐式 Query 推断。
- 写 `async def make_a_wish(...) -> WishOut: return "..."` → **合法**，handler 内 `await`。
- 写 `def f(...) -> WishOut: yield "..."` 或异步 generator → import 期 `YapiDeclarationError`。
- 用户函数返回 `""` / `None` → 合法，无动态段。
- 用户函数返回 `0` / `False` / `[]` → `RuntimeExecutionError` → HTTP 500。
- 未设置 `YAPI_MODEL` 但用了默认 runner → 构造期 `YapiUsageWarning` + 第一次请求 `RuntimeExecutionError("Agent execution failed: RuntimeError: YAPI_MODEL is not set. ...")` → HTTP 500。
- `agent_runner` 返回字段缺失的 dict → `response_model.model_validate` 抛 `ValidationError`（**未被 yapi 捕获**） → HTTP 500，先打 WARNING log。
- `router.prompt.post("/x", tags=["foo"])` → `tags` 透传，OpenAPI 中可见。
- `router.prompt.post("/x", response_model=Foo)` → 装饰期 `YapiDeclarationError`（拒绝清单）。
- `router.prompt.post("/x", does_not_exist=True)` → 装饰期 `YapiUsageWarning`，kwarg 被忽略。
- `router.post("/health") def health() -> dict: ...` → **合法**，走 FastAPI 原生通道（不经过 yapi 内省），与 `router.prompt.*` 在同一 router 内混挂。
- `def f(req: WishIn, ctx: PromptContext) -> WishOut: ctx.add_section("u", req.user_id)` → **合法**（v2.2 起），ctx 由 yapi 自动注入，片段裹进 `<context>` 段。
- `def f(req: WishIn, ctx: Annotated[PromptContext, Body()]) -> WishOut: ...` → 装饰期 `YapiDeclarationError("must not carry FastAPI markers")`。
- `def f(req: WishIn, c1: PromptContext, c2: PromptContext) -> WishOut: ...` → 装饰期 `YapiDeclarationError("may declare at most one PromptContext parameter")`。
- `ctx.add(None) / ctx.add_kv("k", None) / ctx.add_section("n", None)` → 请求期 `RuntimeExecutionError("PromptContext does not accept None; ...")`。
