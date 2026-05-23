---
id: architecture.request-lifecycle
title: 请求生命周期
layer: architecture
tags: [architecture, lifecycle, runtime, fastapi, introspection]
status: stable
---

# 请求生命周期：从 `@router.post(...)` 到 JSON 响应

本文档串清楚 yapi 全部执行模型，覆盖**装饰期**与**请求期**两段。所有不变量和边界都在这里集中。

## 0. 关键组件清单

- `yapi/router.py` (`PromptRouter`)：开发者入口，继承 `fastapi.APIRouter`，持有 `Runtime`。
- `yapi/router.py` (`_introspect`)：函数签名内省，返回 `(request_model, response_model, dependency_params)`。
- `yapi/endpoint.py` (`PromptEndpoint`)：frozen dataclass，封装一条路由的全部静态信息。
- `yapi/runtime.py` (`Runtime`)：执行引擎，持有 `agent_runner`。
- `yapi/runtime.py` (`compose_prompt`) / (`DEFAULT_SYSTEM_PREFIX`)：system prompt 拼接。
- `yapi/models.py` (`RuntimeContext`)：非 frozen dataclass，仅 `request` / `injected` 两段 dict。
- `yapi/agent.py` (`build_agent_runner`)：默认 agent runner 工厂，详见 [`agent-runner-contract.md`](./agent-runner-contract.md)。

## 1. 装饰期（应用启动 / import 时）

以 `examples/wish_api.py` 为例：

```python
router = PromptRouter()

@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""
```

### 1.1 `PromptRouter.__init__`

`yapi/router.py` (`PromptRouter.__init__`)：

```python
self._runtime = Runtime(agent_runner=agent_runner or build_agent_runner())
```

`agent_runner` 为 None 时立刻调用 `build_agent_runner()` —— 此时**绑定**当时 `os.getenv("YAPI_MODEL")` 到 runner 闭包。之后修改环境变量不再生效。这是 yapi 唯一的"延迟失败"点（详见 [`agent-runner-contract.md`](./agent-runner-contract.md)）。

### 1.2 装饰器调用链

`router.post("/wish")` → `_register("POST", "/wish")` → 返回 `decorator`。

`_register` 先校验 method 在 `_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")` 白名单内，否则抛 `YapiDeclarationError("Unsupported HTTP method: ...")`。

### 1.3 `_introspect`（签名内省）

`yapi/router.py` (`_introspect`) 工作流：

1. 取 `inspect.signature(func)`。
2. **返回注解检查**：
   - 缺注解 → `YapiDeclarationError("must declare a return type annotation")`。
   - 不是 `BaseModel` 子类 → `YapiDeclarationError("must return a Pydantic BaseModel subclass")`。
3. **参数遍历**（按声明顺序）：
   - `param.default` 是 `fastapi.params.Depends` 实例 → 进 `dependency_params`，**continue**。Depends 短路优先于 BaseModel 判断，所以 `Depends(...)` 即使返回 BaseModel 也不会被误判为 request_model。
   - 否则 `annotation` 是 `BaseModel` 子类：
     - 已有 request_model → `YapiDeclarationError("may declare at most one Pydantic request model parameter")`。
     - 否则记下 `request_model = annotation`。
   - 都不是 → `YapiDeclarationError("has parameter '{name}' that is neither a Pydantic model nor a Depends() dependency")`。

### 1.4 构造 `PromptEndpoint`

```python
endpoint = PromptEndpoint(
    path=path,
    method=upper,
    request_model=request_model,
    response_model=return_annotation,
    function_doc=(func.__doc__ or "").strip(),
)
```

`PromptEndpoint` 是 `@dataclass(frozen=True)`（`yapi/endpoint.py`），承载路由"静态描述"。属性 `response_doc` 返回 `response_model.__doc__` 的 strip 结果。该对象一次性生成、随闭包持有，请求期不再变化。

### 1.5 二次签名遍历

`yapi/router.py:77-84` 再次遍历 `signature.parameters`，把所有 Parameter 收集到 `handler_params`，同时定位 `request_param_name`（第一个 BaseModel 参数的名字）。这一步看似冗余，实际是为了下一步给 handler 闭包"穿"原签名。

### 1.6 构造异步 handler 闭包

```python
async def handler(**kwargs):
    injected = {name: kwargs[name] for name, _ in dependency_params if name in kwargs}
    request_instance = kwargs.get(request_param_name) if request_param_name is not None else None

    dynamic_prompt = func(**kwargs)
    if dynamic_prompt is not None and not isinstance(dynamic_prompt, str):
        raise RuntimeExecutionError(...)

    return await run_in_threadpool(
        self._runtime.execute,
        endpoint=endpoint,
        request_model=request_instance,
        injected=injected,
        dynamic_prompt=dynamic_prompt,
    )
```

注意：
- handler 接受 `**kwargs`，**不**直接声明参数。
- `func(**kwargs)` **同步直接调用**用户函数，不 await。所以 `async def` 用户函数会得到 coroutine 对象、被守卫挡掉。
- `injected` 只挑出 dependency_params 名字，请求模型不会落入 `injected`。
- `request_instance` 与 `injected` 是 Runtime 层的两条独立数据通道，对应 `RuntimeContext.request` / `RuntimeContext.injected`。

### 1.7 `__signature__` 修补

```python
handler.__signature__ = inspect.Signature(parameters=handler_params, return_annotation=response_model)
handler.__annotations__ = {p.name: p.annotation for p in handler_params if p.annotation is not inspect.Parameter.empty}
handler.__annotations__["return"] = response_model
handler.__name__ = func.__name__
```

这是让 FastAPI 把 handler 当成"原签名"内省的关键。FastAPI 通过 `__signature__` 拿到 BaseModel 参数 → 解析请求体；拿到 Depends → 走依赖注入；拿到 `return` 注解 → 生成 OpenAPI responses。同时 `__name__ = func.__name__` 让 operation_id 看起来正常。

### 1.8 `add_api_route`

```python
self.add_api_route(path, handler, methods=[upper], response_model=response_model)
```

`response_model=` 显式传入，FastAPI 据此生成 OpenAPI schema 并做响应阶段的二次序列化。回归保险：`tests/test_router.py::test_router_post_emits_openapi_with_declared_models`。

### 1.9 装饰器返回 `func`

装饰器最后 `return func`——返回**用户原函数**而不是 handler。这意味着用户函数本身没有被替换，仍可在模块外直接调用。FastAPI 真正调用的是闭包内的 `handler`。

## 2. `app.include_router(router)`

FastAPI 把 `router.routes` 复制进 `app.routes`，路由真正生效。这一步是 FastAPI 原生行为，yapi 不介入。

## 3. 请求期

客户端 `POST /wish {"user_id": "u-1", "wish": "moon"}`：

### 3.1 FastAPI 解析

FastAPI 按 `handler.__signature__` 解析请求：
- 看到 `req: WishIn` 参数 → 用 `WishIn` 校验请求体，构造 `req=WishIn(...)`。
- 看到任意 `Depends(...)` 参数 → 解析对应依赖。

handler 是 `async def`，FastAPI 直接 `await handler(req=..., dep1=..., ...)`，**不**再做 sync→thread 卸载。

### 3.2 handler 内部

参见 1.6 节代码。重点：
- `dynamic_prompt = func(**kwargs)` 同步调用用户函数。
- 类型守卫：必须是 `None` 或 `str`，否则抛 `RuntimeExecutionError`。空串等同于无动态段（`compose_prompt` 内 `if dynamic_prompt` 为假会跳过）。
- 通过 `run_in_threadpool` 把同步的 `Runtime.execute` 卸到 starlette/anyio 的工作线程池——因为 `Runtime.execute` 内最终调用 `pydantic_ai.Agent.run_sync`（阻塞 API），不能在事件循环里直接跑。
- **隐含性能特性**：每个请求会占用一个工作线程直到 LLM 返回，线程池大小是 yapi 的可见并发上限。

### 3.3 `Runtime.execute`

`yapi/runtime.py` (`Runtime.execute`)：

```python
request_data = {} if request_model is None else request_model.model_dump()
context = self.build_context(request_data, injected)
prompt = compose_prompt(endpoint, dynamic_prompt)
try:
    payload = self._agent_runner(
        prompt=prompt,
        request=context.request,
        injected=context.injected,
        response_model=endpoint.response_model,
    )
except Exception as exc:
    raise RuntimeExecutionError("Agent execution failed") from exc
return endpoint.response_model.model_validate(payload)
```

关键点：
- request 没有 BaseModel 参数时（GET 等）`request_data = {}`，`injected` 同理可能为 `{}`。
- `build_context` 用 `dict(request_data)` / `dict(injected)` 做**浅拷贝**塞进 `RuntimeContext`（非 frozen，可变性边界没有明文规定）。
- **agent_runner 抛任何异常都被统一包装为 `RuntimeExecutionError("Agent execution failed") from exc`**——上层只能通过 `__cause__` 拿到原始错误，调试需要看 chained traceback。
- 末尾 `response_model.model_validate(payload)` 是**第二道**响应校验：若 payload 字段缺失 / 类型不符，pydantic 抛 `ValidationError`，**未被任何 try/except 接住**，会被 FastAPI 转 HTTP 500。

### 3.4 `compose_prompt` 的拼接顺序

`yapi/runtime.py` (`compose_prompt`)：

```
sections = [DEFAULT_SYSTEM_PREFIX]
if response_doc: sections.append(response_doc)
if endpoint.function_doc: sections.append(endpoint.function_doc)
if dynamic_prompt: sections.append(dynamic_prompt)
return "\n\n".join(sections)
```

顺序固定为 4 段，**空段直接跳过**（`if section` 为假即不追加）：

1. **`DEFAULT_SYSTEM_PREFIX`**（永远存在）：`"You are the execution engine behind a declarative HTTP endpoint. Return data that strictly matches the required response model."`（`yapi/runtime.py:11-14`）。
2. **`response_model.__doc__`**（strip 后非空时追加）：通过 `endpoint.response_doc` property 取。
3. **`endpoint.function_doc`**（用户路由函数 docstring，strip 后非空时追加）。
4. **`dynamic_prompt`**（handler 收到的本次请求的动态 prompt；空串与 None 都被跳过）。

段间用 `"\n\n"` 拼接。回归保险：`tests/test_runtime.py::test_runtime_sends_composed_prompt_to_agent_runner`。

**重复定义警告**：`yapi/agent.py` (`DEFAULT_SYSTEM_PREFIX`) 也定义了一份字符串，但目前**未被使用**——agent runner 内部用的是入参 prompt。这是死代码 / 冗余风险点，详见 [`../memory/doc-gaps.md`](../memory/doc-gaps.md)。

### 3.5 agent runner 调用

详细契约见 [`agent-runner-contract.md`](./agent-runner-contract.md)。简要：以 4 个 keyword（`prompt` / `request` / `injected` / `response_model`）调用，期望返回 dict。

### 3.6 响应序列化

`Runtime.execute` 返回 `BaseModel` 实例 → handler 返回该实例 → FastAPI 用 `add_api_route(..., response_model=response_model)` 形参再做一遍 pydantic 校验/字段过滤后转 JSON 写回客户端。

## 4. 不变量清单

下列条件在当前实现下恒成立，可作为未来重构的护栏：

1. **`PromptEndpoint` 装饰期冻结**（frozen dataclass）；请求期不变更。
2. **用户函数原物保留**：装饰器返回 `func` 本身；FastAPI 调用的是 handler 闭包。
3. **handler 永远是 async**；同步 `Runtime.execute` 必须通过 `run_in_threadpool` 卸载。
4. **`Runtime.execute` 接口稳定**：`(endpoint, request_model, injected, dynamic_prompt) -> BaseModel`。
5. **响应永远是 BaseModel 实例**：`model_validate` 保证类型；FastAPI 再做一遍序列化。
6. **agent_runner 入参形式固定**：keyword args `prompt / request / injected / response_model`，返回 dict。
7. **`request` 与 `injected` 是两条独立数据通道**；BaseModel 不会进 `injected`，Depends 不会进 `request`。
8. **声明错误同步抛**：所有签名违反在 import / `include_router` 阶段就暴露。

## 5. `_introspect` 的所有报错分支汇总

| 触发条件 | 错误消息片段 | 测试 |
|---|---|---|
| HTTP method 不在白名单 | `Unsupported HTTP method: ...` | 无覆盖 |
| 缺返回注解 | `must declare a return type annotation` | `test_router_post_requires_response_annotation` |
| 返回非 BaseModel | `must return a Pydantic BaseModel subclass` | `test_router_post_rejects_non_basemodel_response` |
| 第二个 BaseModel 参数 | `may declare at most one Pydantic request model parameter` | `test_router_post_rejects_multiple_basemodel_params` |
| 非 BaseModel 非 Depends 参数 | `has parameter '{name}' that is neither a Pydantic model nor a Depends() dependency` | 无覆盖 |

未覆盖分支详见 [`../memory/doc-gaps.md`](../memory/doc-gaps.md)。

## 6. 反例与边界用例速查

- 写 `-> dict` / `-> str` / 缺返回注解 → import 期 `YapiDeclarationError`。
- 写两个 BaseModel 参数 → import 期 `YapiDeclarationError`。
- 写 `q: str = Query(...)` 风格参数 → import 期 `YapiDeclarationError`（既非 BaseModel 也非 Depends）。
- 写 `Annotated[WishIn, Body(...)]` 风格 → annotation 不是 BaseModel 子类 → import 期 `YapiDeclarationError`（与 FastAPI 原生体验不同）。
- 用户函数 `async def make_a_wish(...) -> WishOut:` → coroutine 落入"非 str/非 None"守卫 → `RuntimeExecutionError` → HTTP 500。
- 用户函数返回 `""` / `None` → 合法，无动态段。
- 用户函数返回 `0` / `False` / `[]` → 非 str 非 None → `RuntimeExecutionError` → HTTP 500。
- 未设置 `YAPI_MODEL` 调用接口 → 默认 runner 抛 `NotImplementedError` → 包装为 `RuntimeExecutionError` → HTTP 500。
- `agent_runner` 返回的 dict 字段缺失 → `response_model.model_validate` 抛 `ValidationError`（**未被 yapi 捕获**） → HTTP 500。
- `router.post("/x", tags=["foo"])` → `tags=` 进入 `**_unused` 被静默丢弃；OpenAPI 不会出现 tag。
