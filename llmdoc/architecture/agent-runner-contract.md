---
id: architecture.agent-runner-contract
title: AgentRunner 契约
layer: architecture
tags: [architecture, agent, runner, protocol, runner-context, pydantic-ai]
status: stable
---

# AgentRunner 契约

固化 `yapi/runner.py` + `yapi/agent.py` + `yapi/runtime.py` 三处共同维护的 runner 扩展面。从 v2.1 起 runner 是显式的一等扩展点（不再是朴素 `Callable`）。

## 1. `AgentRunner` Protocol

`yapi/runner.py`：

```python
@runtime_checkable
class AgentRunner(Protocol):
    def run(self, ctx: RunnerContext) -> dict | BaseModel:
        ...
```

要点：

- **同步**接口；`Runtime.execute` 在 `run_in_threadpool` 内调用，runner 的 `.run` 可以放心做阻塞 I/O。
- 返回 `dict` 或 `BaseModel` 实例皆可；返回 BaseModel 实例时 `Runtime.execute` 走 `isinstance` 快路径跳过二次 `model_validate`。
- `@runtime_checkable` 让 `isinstance(obj, AgentRunner)` 可用，但**只是浅层结构检查**（见 §3）。

`Runtime` 在初始化时通过 `_coerce_runner` 把传入对象规范化成"有 `.run` 方法的对象"——任何已带 `.run(ctx)` 方法的实例（满足 Protocol 的鸭子类型）都直通；callable 包成 `_LegacyCallableRunner`。

## 2. `RunnerContext` 字段

`yapi/runner.py`：

```python
@dataclass(frozen=True)
class RunnerContext:
    prompt: str
    request: dict
    injected: dict
    response_model: type[BaseModel]
    path: str
    method: str
```

frozen 是有意为之：runner 不应突变 ctx，便于多模型 fan-out、跨 runner 链。各字段含义：

| 字段 | 来源 | 用途 |
|---|---|---|
| `prompt` | `Runtime._compose_prompt(endpoint, dynamic_prompt)` 的返回值 | 拼好的完整 system prompt |
| `request` | `request_model.model_dump()`（无 REQUEST_MODEL 时为 `{}`） | 请求体字典 |
| `injected` | DEPENDENCY + INJECTED_FIELD 合并后的 dict | 依赖注入 + Query/Header/... 字段 |
| `response_model` | `endpoint.response_model` | 期望响应类型，runner 一般传给 `pydantic_ai.Agent(output_type=...)` |
| `path` | `endpoint.path` | 路由路径，方便 tracing / 多路由分支 |
| `method` | `endpoint.method` | HTTP method，同上 |

`path / method` 是 v2.1 相对 v2 的关键新增：自定义 runner 可以基于这两个字段做 tracing tag、metrics label、按路径选模型等。

## 3. Protocol 静态提示局限（spec §5.3）

`@runtime_checkable` 的 `isinstance` 只检查"对象有 `run` 属性"，**不**校验签名：

```python
class BadRunner:
    def run(self, ctx, extra_required_arg):  # 签名错了
        return {}

isinstance(BadRunner(), AgentRunner)         # ❌ → True，Protocol 不挡
```

错误只能在请求期 `self._agent_runner.run(ctx)` 调用时被 Python 抛 `TypeError`，最终包装为 `RuntimeExecutionError("Agent execution failed: TypeError: ...")`。

设计立场：

- **Protocol 在 v2.1 中只承担"类型提示"职责**——给写 runner 的人 IDE / mypy / pyright 静态结构提示。
- **运行期保险靠错误消息**：`Runtime.execute` 把 `__cause__` 的类型名 + 消息塞进 `RuntimeExecutionError`，让请求期错误日志一眼能看出"签名错了"。
- **运行期保险靠测试矩阵**：`tests/test_runner.py::test_bad_runner_raises_at_request_time` 用一个签名错的 BadRunner 验证 HTTP 500 路径稳定。

写文案时**不要**说"Protocol 保证了运行期类型安全"，正确表述是"Protocol 提供静态结构提示，运行期由 `RuntimeExecutionError` 错误消息携带 cause 摘要做最后兜底"。

## 4. `_coerce_runner` + `_LegacyCallableRunner` 兼容适配

`yapi/runner.py` (`_coerce_runner`)：

```python
def _coerce_runner(runner: Any) -> AgentRunner:
    if runner is None:
        raise TypeError("agent_runner must not be None")
    if hasattr(runner, "run") and not isinstance(runner, type):
        return runner                            # 鸭子类型，含 Protocol-conforming 对象
    if callable(runner):
        return _LegacyCallableRunner(runner)
    raise TypeError("agent_runner must be an AgentRunner or a (*, prompt, request, injected, response_model) callable, got ...")
```

匹配顺序的硬约束：

1. `None` 显式拒绝（`Runtime.__init__` 永远收到非 None；构造期的 `or build_default_runner()` 兜底）。
2. **有 `.run` 属性 + 不是类对象**优先：覆盖类实例与 Protocol-conforming 鸭子。`not isinstance(runner, type)` 是为了拒绝"开发者错传了类而不是实例"。
3. callable（含 lambda / 普通函数 / 自定义 `__call__`）次之，包成 `_LegacyCallableRunner`。
4. 其他对象 `TypeError`。

`_LegacyCallableRunner`：

```python
class _LegacyCallableRunner:
    def __init__(self, fn): self._fn = fn
    def run(self, ctx: RunnerContext) -> dict | BaseModel:
        return self._fn(
            prompt=ctx.prompt, request=ctx.request,
            injected=ctx.injected, response_model=ctx.response_model,
        )
```

让 v2 风格 `lambda **_: {...}` / `def runner(*, prompt, request, injected, response_model): ...` **一字不改**继续工作——只接 4 个 keyword，不暴露 `path / method`。这是有意保留的"低成本兼容垫片"，不发 deprecation 警告。详见 `memory/decisions/2026-05-24-yapi-v2.1-surface-split.md`。

## 5. `PydanticAIRunner` 默认实现

`yapi/agent.py`：

```python
class PydanticAIRunner:
    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def run(self, ctx: RunnerContext) -> dict:
        if self._model is None:
            raise RuntimeError("YAPI_MODEL is not set. Set YAPI_MODEL=test for an offline smoke test, ...")
        agent = Agent(self._model, output_type=ctx.response_model, system_prompt=ctx.prompt)
        result = agent.run_sync(f"request={ctx.request}\ninjected={ctx.injected}")
        output = getattr(result, "output", result)
        return output.model_dump() if hasattr(output, "model_dump") else dict(output)


def build_default_runner(model: str | None = None) -> AgentRunner:
    resolved = model or os.getenv("YAPI_MODEL")
    if resolved is None:
        warnings.warn("YAPI_MODEL not set; the first request to a prompt route will raise. ...", YapiUsageWarning, stacklevel=2)
    return PydanticAIRunner(model=resolved)

build_agent_runner = build_default_runner       # v2 名字别名
```

关键事实：

- **构造期 warning**：`build_default_runner()` 调用时（典型场景：`PromptRouter()` 无参数构造），`model is None and os.environ["YAPI_MODEL"]` 未设置 → 发 `YapiUsageWarning("YAPI_MODEL not set; ...")`，`stacklevel=2` 让警告指向 `PromptRouter()` 调用现场。
- **延迟失败**：warning 之后仍然返回 `PydanticAIRunner(model=None)`。第一次 `.run(ctx)` 时才抛 `RuntimeError`，最终被 `Runtime.execute` 包装为 `RuntimeExecutionError`。
- **`YAPI_MODEL=test`**：`PydanticAI.Agent("test", ...)` 内部用 `TestModel` 按 response schema 占位，零网络、零 API key。CI 与离线 smoke 首选。
- **`output` fallback**：PydanticAI 不同版本对 `result.output` 的暴露形态不同，`getattr(result, "output", result)` 兼容两种；`model_dump` / `dict()` 也是同样的双 fallback。
- **`build_agent_runner` 别名**：v2 名字保留，避免下游已 `from yapi.agent import build_agent_runner` 的代码断裂。

## 6. `prompt_composer` 注入点

`Runtime.__init__` 接收 `prompt_composer: PromptComposer | None`；`PromptRouter(prompt_composer=...)` 透传：

```python
PromptComposer = Callable[[PromptEndpoint, str | None], str]
```

签名固定为 `(endpoint, dynamic_prompt) -> str`，必须返回拼好的完整 system prompt 字符串。默认实现 `compose_prompt` 用 4 段拼接（见 `request-lifecycle.md` §3.4）。

典型用途：

- 多语言 prompt（按 `endpoint.path` 或 `endpoint.function_doc` 切换语种）。
- 加入 few-shot 示例段。
- 自定义段落顺序（如把 dynamic_prompt 放到最前面）。

注入的 composer 返回值直接进 `RunnerContext.prompt`，对所有 runner 透明。

## 7. fake runner 测试范式

跨测试用 `PromptRouter(agent_runner=...)` 注入 fake 是标准做法。三种典型形态：

**A. lambda（v2 风格，最短）：**

```python
router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})
```

通过 `_LegacyCallableRunner` 翻译，接 4 个 keyword。

**B. 闭包 + 副作用捕获（验证传入参数）：**

```python
captured = {}
def runner(**kwargs):
    captured.update(kwargs)              # 拿到 prompt / request / injected / response_model
    return {"granted": True, "message": "ok"}

router = PromptRouter(agent_runner=runner)
# 请求后断言 captured["prompt"] / captured["injected"] / ...
```

`tests/test_router.py` 内 `test_prompt_supports_annotated_*` 系列大量使用这种形态。

**C. class runner（v2.1 风格，最完整）：**

```python
class CaptureRunner:
    def run(self, ctx: RunnerContext) -> dict:
        captured.append(ctx)             # 拿到完整 RunnerContext 含 path / method
        return {"granted": True, "message": "ok"}

router = PromptRouter(agent_runner=CaptureRunner())
```

是 `tests/test_runner.py` 的模板。注意 `isinstance(CaptureRunner(), AgentRunner)` 因 Protocol 只检查 `run` 属性而**总是 True**——这条断言适合放在 smoke 测试里证明 Protocol 链路通畅。

## 8. 错误反馈与 logging

runner 抛任何异常 → `Runtime.execute` 内 `logger.warning("runner failed: %r", exc)` + 抛 `RuntimeExecutionError(f"Agent execution failed: {type(exc).__name__}: {exc}") from exc`。完整错误目录见 [`../reference/error-catalog.md`](../reference/error-catalog.md)。

runner 调用前后还有两条 DEBUG log：

- `logger.debug("invoking runner=%s", type(self._agent_runner).__name__)`：runner 调用前。
- `logger.debug("execute path=... method=... has_request_model=... injected_keys=...")`：execute 进入。

pytest 抓 log 范式见 [`../reference/run-and-test.md`](../reference/run-and-test.md)。
