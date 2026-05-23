---
id: reference.annotated-introspection
title: Annotated 内省协议
layer: reference
tags: [reference, annotated, introspection, fastapi, paramrole, constraint]
status: stable
---

# Annotated 内省协议

固化"yapi 如何从函数签名识别 FastAPI 写法"的稳定约束。任何后续扩展 `ParamRole`（新增参数语义、WebSocket、StreamingResponse、自定义 marker）的人都必须遵守这里的事实。

## 1. `Annotated[T, *metadata]` 的稳定返回形状

Python 标准库的 `typing.Annotated` 在被实例化后会在对象上挂两个 dunder 属性：

- `__origin__`：base type，即 `T`。
- `__metadata__`：metadata 元组，即 `tuple[Any, ...]`。

`typing.get_origin` 与 `typing.get_args` 也能拿到同样的信息，但 yapi 选择**直接读 dunder**而不是走 `get_origin / get_args`：

- `get_origin(Annotated[int, "x"])` 是 `int`？不是——它返回 `typing.Annotated` 本身（特例）；要拿 base type 得用 `get_args(...)[0]`。
- 直接读 `obj.__origin__` 与 `obj.__metadata__` 在所有支持的 Python 版本（≥ 3.12）上行为一致，无特例。

## 2. `_unwrap_annotated` helper 形态

`yapi/router.py` (`_unwrap_annotated`)：

```python
def _unwrap_annotated(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    if hasattr(annotation, "__metadata__") and hasattr(annotation, "__origin__"):
        return annotation.__origin__, tuple(annotation.__metadata__)
    return annotation, ()
```

- 同时检测**两个**属性，避免某些只挂其中一个的边界类型误判。
- 非 Annotated 类型直接返回 `(annotation, ())`，下游无需额外分支。
- 返回的 metadata 是 tuple 而不是 list，方便后续做"先匹配先生效"的顺序遍历。

任何在 `_classify_param` 之外读 Annotated 元信息的代码（未来的 `_compose_prompt` 扩展、自定义 marker 处理等）都应该复用这个 helper，而不是各自再写一遍 `hasattr / __metadata__`。

## 3. 标记类型匹配顺序：Body 必须先于 Param

`fastapi.params` 模块内的继承关系（v0.115）：

```
fastapi.params.Param      ← Query / Header / Cookie / Path / Form / File 的共同基类
fastapi.params.Body       ← Body 自己，与 Param 是兄弟，不是父子
fastapi.params.Depends    ← 独立类
```

因此判断顺序的硬约束是：

1. 先 `isinstance(default, params.Depends)`。
2. 再 `isinstance(default, _INJECTED_FIELD_TYPES)`，`_INJECTED_FIELD_TYPES = (Query, Header, Cookie, Path, Form, File)`。
3. 再 `isinstance(default, params.Body)`。
4. 最后才看 Annotated metadata，并按同样顺序找 marker。

**反模式**：写一个泛 `isinstance(default, params.Param)` 试图覆盖所有 6 个注入字段类型 + Body —— `Body` 会漏掉。即便未来 FastAPI 内部重构让 `Body` 变成 `Param` 子类，yapi 显式枚举 `_INJECTED_FIELD_TYPES` 也比依赖继承推断更稳。

完整匹配树见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md) §1.4。

## 4. handler `__signature__` 不可剥 Annotated

`yapi/router.py` 装饰器最后做的 `__signature__` 修补**必须**原样复用 `inspect.signature(func).parameters.values()`：

```python
original_signature = inspect.signature(func)
original_params = list(original_signature.parameters.values())   # 原样
handler.__signature__ = inspect.Signature(
    parameters=original_params,
    return_annotation=response_model,
)
```

如果改成"把 `Annotated[T, marker]` 规整成 `T`"或"丢掉 default"会发生什么：

- FastAPI 通过 `__signature__` 内省请求体解析、依赖、参数标记；丢掉 `Annotated` 等价于关掉 body / query / header 解析，请求会 422 或拿不到字段。
- 用户写 `req: Annotated[WishIn, Body(embed=True)]` 时 `embed=True` 完全靠 metadata 中的 `Body` 实例传给 FastAPI；剥掉 metadata 后 FastAPI 看不到 `embed=True`。
- 测试 `tests/test_router.py::test_prompt_handler_signature_preserves_annotated` 是这条约束的回归保险，会读 `route.endpoint` 的 signature 断言 `req` 与 `q` 的 annotation 都仍含 `__metadata__`。

**重要分离**：`param_roles: dict[str, ParamRole]` 是 yapi 的**内部状态**，handler 闭包按它做 kwargs 分流；handler `__signature__` 是给 FastAPI 看的**外部视图**，原样保留用户函数签名。两套视图各管各的，互不污染。

## 5. 扩展时的检查清单

未来若要给 `ParamRole` 添加新 marker（如自定义"动态 prompt 标签"），按顺序做：

1. 在 `_INJECTED_FIELD_TYPES` 或新增的常量元组里显式加入新类型（不要依赖继承）。
2. 在 `_classify_param` 的 default 分支与 Annotated metadata 分支**同时**加判断（用户两种写法都得支持）。
3. 如果 marker 改变 handler 闭包的分流逻辑（例如新角色既不是 REQUEST_MODEL 也不是 injected），在 handler 闭包内更新对应分支并写测试。
4. **不要**碰 `handler.__signature__ = inspect.Signature(parameters=original_params, ...)` 这一行——它是不变量，新 marker 的 metadata 应当随 `original_params` 一起原样进入 FastAPI 视野。

`fastapi.params.Param` 类层级在 FastAPI 升级后可能微调，扩展时记得跑 `tests/test_router.py` 的 Annotated 兼容矩阵（`test_prompt_supports_annotated_*` 系列）确认无回归。
