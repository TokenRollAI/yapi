---
id: reference.prompt-context
title: PromptContext 注入对象
layer: reference
tags: [reference, prompt-context, v2.2, xml-boundary]
status: stable
---

# PromptContext 注入对象

v2.2 引入的"prompt 增量"通道。把"往 system prompt 塞结构化片段"从用户函数 `return str` 的副作用升级为显式注入对象 + append-only 副作用接口。源文件：`yapi/prompt_context.py`（35 行）。

## 1. 触发与注入

只要 prompt 路由函数声明了一个 **annotation 是 `PromptContext`（或其子类）的裸参数**，yapi 就在请求期为该路由新建一个 `PromptContext` 实例并按参数名注入到用户函数。

```python
from yapi import PromptContext, PromptRouter

router = PromptRouter()

@router.prompt.post("/wish")
def make_a_wish(req: WishIn, ctx: PromptContext) -> WishOut:
    """根据用户档案决定是否实现愿望。"""
    ctx.add_section("User", req.user_id)
```

注入识别规则在 `yapi/router.py` `_classify_param` 内，在 `_unwrap_annotated` 之前完成；详见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md) §1.4。

## 2. 三方法表面

`PromptContext` 公开方法只有三个，全部**仅追加，无返回值**：

| 方法 | 形态 | 输出片段 |
|---|---|---|
| `ctx.add(value)` | 任意值 | `<_format_value(value)>` |
| `ctx.add_kv(key, value)` | 键值对 | `{key}: <_format_value(value)>` |
| `ctx.add_section(name, body)` | 命名段 | `# {name}\n<_format_value(body)>` |

还有一个**内部**方法 `segments() -> tuple[str, ...]`，由 `compose_prompt` 调用拿到拼接后片段元组；**不**对外承诺稳定。

刻意**不提供**的方法：`clear / pop / extend / remove / replace`、条件添加 helper、自定义 separator、自定义外裹 tag。append-only 是有意为之，条件添加用 Python 原生 `if`。想换 XML 标签的开发者注入 `prompt_composer=` 自己拼。

## 3. `_format_value` 序列化规则

`yapi/prompt_context.py::_format_value(value)` 按顺序匹配：

| 类型 | 转换 |
|---|---|
| `None` | `RuntimeExecutionError("PromptContext does not accept None; use an empty string if you want an empty segment.")` |
| `str` | 原样返回 |
| `BaseModel` 实例 | `value.model_dump_json()` |
| `dict / list / tuple` | `json.dumps(value, ensure_ascii=False)` |
| 其它 | `str(value)` |

`None` 之所以拒绝：在 prompt 里没有合理语义，拒绝比静默跳过更显性。想要"空段"请显式 `ctx.add("")` 或省略调用。

`ensure_ascii=False` 之所以默认：让中文 / unicode 字面写进 prompt，避免 `"中"` 这种对 LLM 不友好的转义。

## 4. XML 边界与拼接顺序

`compose_prompt` 在 `Runtime.execute` 内调用，按下列顺序拼装最终 system prompt：

```
DEFAULT_SYSTEM_PREFIX                              # 永远存在
↓
response_model.__doc__                             # 如非空
↓
function.__doc__                                   # 如非空
↓
<context>                                          # 仅当至少有一个 segment
  ctx.segments() 按调用顺序拼接（segment 间 \n\n）
  
  dynamic_prompt（如果 return 了非空 str）
</context>
```

段间用 `"\n\n"` 串联。空段省略：当 PromptContext 没有任何 `add*` 调用，且函数 `return` 不是非空 str 时，`<context>` 整段**不输出**——避免空 token 浪费，让 v2.2 路由在"无动态段"场景下 prompt 形态与 v2.1 完全一致。

实例（接 §1 路由，假设 `req.user_id = "u-1"`）：

```
You are the execution engine behind a declarative HTTP endpoint. Return data that strictly matches the required response model.

根据用户档案决定是否实现愿望。

<context>
# User
u-1
</context>
```

## 5. 不变量

1. **请求局部**：每次请求新建实例，不跨请求、不共享。
2. **append-only**：无 mutation / 删除 API，段序与调用序一致。
3. **被 `__signature__` 过滤**：装饰期 `_introspect` 识别 ctx 参数后，handler `__signature__` 把它剔除，FastAPI 看不到，自然不当 query / body 解析，OpenAPI 也不出现 `PromptContext` 字段。
4. **runner 看不到 segment 级粒度**：`RunnerContext.prompt` 是已经裹好的字符串，runner 想看 segment 自己 parse `<context>`（按 YAGNI 推迟到未来版本）。
5. **最多一个 `PromptContext` 参数**：第二个装饰期 `YapiDeclarationError`。
6. **不能带 FastAPI marker**：`Annotated[PromptContext, Body()/Query()/Depends()/...]` 装饰期 `YapiDeclarationError`。
7. **`<context>` tag 固定字面量**：不支持用户自定义 tag、不支持多个 `<context>` 块（一个路由一个 `<context>`，里面用 `add_section(name, ...)` 区分子段）。

## 6. 与 state 的关系

v2.2 spec 明确：**yapi 不集成 state 存储**。Redis / Mongo / Dynamo / SQL session 这些客户端用 FastAPI 原生 `Depends(...)` 拿就好，yapi 不再造一层 `StateStore` Protocol。

典型组合（见 `examples/state_via_depends.py`）：

```python
def get_store() -> dict:
    return _STORE                                  # 真实场景换成 Redis client / DB session 等

@router.prompt.post("/wish")
def make_a_wish(
    req: WishIn,
    ctx: PromptContext,
    store: dict = Depends(get_store),
) -> WishOut:
    """..."""
    profile = store.get(req.user_id, {})
    ctx.add_section("User Profile", profile)
    ctx.add_kv("item_id", req.item_id)
```

存储侧由开发者用 `Depends` 拿；过滤 / 转换由开发者写；哪些事实进 prompt 由开发者用 `ctx.*` 决定。yapi 只负责把这些片段拼接 + 外裹 + 注入 system prompt。

## 7. 错误一览

| 触发条件 | 时机 | 错误 |
|---|---|---|
| 同一路由两个 `PromptContext` 参数 | 装饰期 | `YapiDeclarationError("may declare at most one PromptContext parameter")` |
| `Annotated[PromptContext, Marker]` | 装饰期 | `YapiDeclarationError("must not carry FastAPI markers")` |
| `ctx.add(None) / add_kv(_, None) / add_section(_, None)` | 请求期（沿用户调用栈） | `RuntimeExecutionError("PromptContext does not accept None; ...")` |

完整错误层级见 [`./error-catalog.md`](./error-catalog.md)。

## 8. 测试范式

单元测试在 `tests/test_prompt_context.py`（11 条覆盖三方法 + `_format_value` 所有分支 + None 拒绝 + 段序）。

router-level 注入识别测试在 `tests/test_router.py`：
- `test_router_injects_prompt_context_by_type` / `_async` / `_param_name_is_arbitrary` — sync / async / 任意参数名都识别。
- `test_router_rejects_two_prompt_context_params` — 两个 ctx 装饰期报错。
- `test_router_rejects_prompt_context_with_fastapi_marker` — 带 Marker 装饰期报错。
- `test_router_prompt_context_not_in_openapi` — OpenAPI 不暴露 `PromptContext`。

端到端集成测试在 `tests/test_integration.py`：
- `test_e2e_ctx_segments_reach_runner` — ctx 片段经 prompt 抵达 fake runner。
- `test_e2e_v21_route_with_return_str_wraps_in_context` — v2.1 老路由 `return str` 现在裹 `<context>`。
- `test_e2e_route_with_no_ctx_and_no_return_skips_context_tag` — 空段省略。
