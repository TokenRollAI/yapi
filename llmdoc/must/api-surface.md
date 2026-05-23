---
id: must.api-surface
title: PromptRouter 对外契约
layer: must
tags: [must, api, contract, declarative]
status: stable
---

# PromptRouter 对外契约

唯一公开类。完整执行链路见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md)，这里只固化"开发者必须遵守的硬约束"。

## 继承与装饰器表面

- `PromptRouter` 继承 `fastapi.APIRouter`（`yapi/router.py` (`PromptRouter`)）。
- 覆盖了 5 个装饰器：`.get` / `.post` / `.put` / `.patch` / `.delete`。`OPTIONS` / `HEAD` / `TRACE` 不在白名单（`yapi/router.py` `_HTTP_METHODS`），传入会抛 `YapiDeclarationError`。
- 装饰器**只**接受一个 path 参数：`def post(self, path: str, **_unused)`。FastAPI 原生 kwargs（`tags=` / `summary=` / `status_code=` / `response_class=` / `response_model=` / ...）全部进 `**_unused` 被**静默丢弃**——这是一个已知开发者陷阱，详见 [`../memory/doc-gaps.md`](../memory/doc-gaps.md)。
- 同一个 `PromptRouter` 内**不能**混挂普通 FastAPI 接口：所有 `.get/.post/...` 都被覆盖到 `_register`。要挂普通路由，新建一个原生 `APIRouter`。

## 构造签名

```python
PromptRouter(agent_runner: Callable[..., dict] | None = None)
```

- 不传 / 传 `None`：使用默认 `yapi.agent.build_agent_runner()`（读 `YAPI_MODEL`）。
- 传 callable：必须接受 4 个 keyword 参数 `prompt, request, injected, response_model` 并返回 dict（必须能通过 `response_model.model_validate`）。详见 [`../architecture/agent-runner-contract.md`](../architecture/agent-runner-contract.md)。

## 函数签名推断契约

定义在 `yapi/router.py` (`_introspect`)。装饰器期同步抛 `YapiDeclarationError`，应用 import / startup 即失败。

### 返回注解硬约束

- **必须**有返回注解：`def f(...)` 不允许。
- 返回注解**必须**是 `BaseModel` 子类：`-> dict` / `-> str` / `-> Optional[WishOut]` 都不允许。
- 该类的 `__doc__` 会被纳入 system prompt（见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md)）。

### 参数硬约束

按声明顺序遍历，每个参数二选一：

1. **`default` 是 `fastapi.Depends(...)` 的参数**：进入依赖列表。注解可任意（甚至 `Any`），但**必须**用 default 形式，不支持 `Annotated[..., Depends(...)]`。
2. **`annotation` 是 `BaseModel` 子类的参数**：作为 request_model。**最多一个**；第二个 BaseModel 参数会抛错。

任何不属于上述两类的参数（包括 `q: str = Query(...)`、`q: int`、`x: Annotated[WishIn, Body(...)]`、`*args` / `**kwargs`）都会抛 `YapiDeclarationError`。

### GET 等无请求体场景

GET 路由允许没有 BaseModel 参数（`tests/test_router.py::test_router_supports_get_with_no_request_body`）。此时 request_model 为 None，`Runtime.execute` 内 `request_data = {}`。

## 动态 prompt 契约

用户函数在请求期被 handler 闭包**同步调用**（`func(**kwargs)`，**不 await**），返回值**只能**是：

- `None`（包括没有 `return` 语句的隐式 None / 显式 `return None`）：合法，"无动态提示"，最终 prompt 不会有动态段。
- `str`：作为动态 prompt 段追加到 system prompt 末尾（见 `compose_prompt` 章节）。**空字符串等同于无动态段**（`if dynamic_prompt` 为假）。
- 其他任意值（`int` / `dict` / `BaseModel` / `coroutine` / `0` / `False` / `[]`）：在 handler 内抛 `RuntimeExecutionError`，FastAPI 默认转 HTTP 500。

**`async def` 用户函数会失败**：handler 不 await，coroutine 对象落入"非 str 非 None"分支，必然 500。这是隐性限制，目前无测试覆盖，详见 [`../memory/doc-gaps.md`](../memory/doc-gaps.md)。

用户函数能从 kwargs 拿到完整的 request_model 实例与 Depends 解析对象——可以基于它们拼接 dynamic prompt：

```python
@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据愿望决定是否实现。"""
    return f"focus on user {req.user_id}'s mood: {req.wish}"
```

## 用户原函数不被绑定

装饰器**返回 `func` 原物**，FastAPI 真正调用的是闭包内的 `handler`。用户仍可在模块外直接调用原函数。`add_api_route` 通过给 `handler.__signature__` 还原原签名让 FastAPI 内省（请求体解析、OpenAPI 生成）保持正常。

## 错误反馈时机

- 装饰器期（`@router.post(...)` 求值时）抛 `YapiDeclarationError`：所有签名违反在 import / `include_router` 阶段就暴露。
- 请求期抛 `RuntimeExecutionError`：动态 prompt 非法、agent_runner 抛错、`YAPI_MODEL` 未设置等。

完整错误目录见 [`../reference/error-catalog.md`](../reference/error-catalog.md)。
