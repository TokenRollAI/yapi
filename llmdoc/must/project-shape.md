---
id: must.project-shape
title: 项目最小事实
layer: must
tags: [must, project-shape, runtime, packaging]
status: stable
---

# yapi 项目最小事实

## 这是什么项目

yapi 是一个 **prompt-first 的声明式 HTTP 框架**。开发者在 `PromptRouter` 上用 `@router.prompt.post("/path")` 装饰一个**有返回注解、有 docstring 的同步或异步函数**；框架在请求期把"函数签名 + 模型 docstring + 函数 docstring + `PromptContext` 收集的结构化片段 + 函数返回的动态 prompt（裹进 `<context>...</context>` XML 边界）"组装成 system prompt，交给 PydanticAI Agent 生成符合返回注解的结构化响应，最后用 FastAPI 序列化为 JSON。

公开 API 表面共 8 个 re-export（`yapi/__init__.py` `__all__`）：

- `PromptRouter` — 唯一开发者入口类。
- `PromptContext` — 自动注入的 prompt 增量收集器（v2.2 新增）。
- `AgentRunner`、`RunnerContext` — runner 扩展契约（Protocol + frozen dataclass）。
- `YapiError`、`YapiDeclarationError`、`RuntimeExecutionError`、`YapiUsageWarning` — 完整错误层级。

源码侧目前有 10 个 `.py` 文件 + `yapi/py.typed` 标记（v2.2 新增 `yapi/prompt_context.py`）。下游 mypy / pyright 可识别 yapi 的类型注解。

## 对齐的 spec

当前代码精确对齐 `docs/superpowers/specs/2026-05-24-yapi-v2.2-design.md`（v2.2）。v2.2 在 v2.1 基础上做增量扩展：

- **`PromptContext` 注入对象**：声明 `ctx: PromptContext` 参数，yapi 在请求期自动注入实例。三方法 `ctx.add(value)` / `ctx.add_kv(k, v)` / `ctx.add_section(name, body)` 收集结构化片段，按 `_format_value` 规则转字符串。
- **`<context>...</context>` XML 边界**：所有 ctx 片段 + `return str` 动态段统一外裹 XML 标签，作为 system prompt 最后一段；无任何段时整段省略。
- **`ParamRole.PROMPT_CONTEXT`** 新分类；`_introspect` 返回值由 4-tuple 变 5-tuple（新增 `ctx_param_name`）；handler `__signature__` 过滤 ctx 参数，FastAPI 看不到。
- **唯一 user-visible 破坏点**（v2.1 → v2.2）：v2.1 路由 `return "hint"` 现在被裹进 `<context>...</context>`（之前裸拼在 system prompt 末尾）。绝大多数 prompt 对 XML 边界鲁棒，无需迁移。

v2.1 已经做到的（仍生效）：

- `PromptRouter` 升级为 `APIRouter` 的真超集，prompt 路由收敛到 `router.prompt.{get,post,put,patch,delete}` 子命名空间。
- 函数签名识别原生 FastAPI 写法（`Annotated[BaseModel, Body()]` / `Annotated[T, Depends()]` / `Annotated[str, Query()/...]`），`async def` 路由函数受支持。
- 装饰器 kwarg 三档处理（透传白名单 / 拒绝清单装饰期报错 / 未知 `YapiUsageWarning`）。
- `agent_runner` 抬升为 `AgentRunner` Protocol + `RunnerContext`（含 `path / method`），v2 风格 callable 由 `_LegacyCallableRunner` 兼容。
- v1 残留 `StateStoreError` 已物理删除；state / storage **始终**不在仓库内（v2.2 spec §1 重申此立场——state 这件事 yapi 不集成，用 FastAPI 原生 `Depends` 即可）。

前置阅读 v2.1 spec（`docs/superpowers/specs/2026-05-24-yapi-v2.1-design.md`）以理解 v2.2 的增量动机；v2（`docs/superpowers/specs/2026-05-21-yapi-v2-design.md`）、v1（`docs/superpowers/specs/2026-05-20-yapi-design.md`）与 v0 plan（`docs/superpowers/plans/2026-05-20-yapi-v0-implementation.md`）**已过时**，不要按它们写代码。

## 最重要的对外 API 形态

详细契约见 [`api-surface.md`](./api-surface.md)。最小骨架：

```python
from fastapi import FastAPI
from pydantic import BaseModel
from yapi import PromptRouter

class WishIn(BaseModel):
    user_id: str
    wish: str

class WishOut(BaseModel):
    """你是一个愿望受理实体。请返回结构化结果。"""
    granted: bool
    message: str

router = PromptRouter()

@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""

app = FastAPI()
app.include_router(router)
```

实例：`examples/wish_api.py`（最小骨架）、`examples/mixed_router.py`（普通路由 + prompt 路由混挂）、`examples/with_depends.py`（`Depends` 注入 + dynamic prompt）、`examples/custom_runner.py`（自定义 `AgentRunner` Protocol）。

## 运行入口

- **Python**：≥ 3.12（`pyproject.toml`）。
- **依赖安装**：`uv sync --extra dev`（推荐，`uv.lock` 已落库，1842 行、105 个 lock 包）；或 `pip install -e ".[dev]"`。
- **跑测试**：`uv run pytest`（`pyproject.toml` 已配 `pythonpath=["."]` 与 `testpaths=["tests"]`，无需额外参数）。
- **启动 showcase**：`uv run uvicorn examples.wish_api:app --reload`，OpenAPI 在 `http://localhost:8000/docs`。

详细命令与离线 demo 见 [`../reference/run-and-test.md`](../reference/run-and-test.md)。

## 安装方式（PyPI distribution name）

distribution name 与 import name 不一致：在 PyPI 上是 **`pyyapi`**，但 import 路径仍然是 **`yapi`**。

```bash
pip install pyyapi
```

```python
from yapi import PromptRouter
```

之所以不对称：PyPI 上 `yapi` 这个名字被一个 2018 年的同名项目占用，无法收回，因此分发包改名为 `pyyapi`；import 路径保留 `yapi` 是为了不让仓库内所有 `from yapi import ...` 失效。这一不对称是**永久属性**，未来撰写 README、错误信息、教程或对外提示时都要避免说成 `pip install yapi`。

仓库内开发安装依旧走上一段的 `uv sync --extra dev`，无需 `pip install pyyapi`。

## `YAPI_MODEL` 的角色

`PromptRouter()` 不传 `agent_runner` 时回退到默认 `yapi.agent.build_default_runner()`（旧名 `build_agent_runner` 仍是同函数别名），在工厂调用时**一次性绑定** `os.getenv("YAPI_MODEL")` 到 `PydanticAIRunner` 实例。

- 未设置：构造**不报错但发 `YapiUsageWarning`**（spec §6.4 明文要求），**第一次请求**时 runner 抛 `RuntimeError("YAPI_MODEL is not set. Set YAPI_MODEL=test for an offline smoke test, or YAPI_MODEL=openai:gpt-4o etc. for real models.")`，被 `Runtime.execute` 包装为 `RuntimeExecutionError`，最终 FastAPI 转 HTTP 500。
- 设为模型字符串（如 `openai:gpt-4o`、`anthropic:claude-3-5-sonnet`、`openai:deepseek-chat`）：交给 `pydantic_ai.Agent(...)` 直接解析。**Provider 凭证由 pydantic-ai 在请求期直接读 `os.environ`**，yapi 全程不感知、不校验、不转发：`OPENAI_API_KEY` / `OPENAI_BASE_URL`（OpenAI 与所有 OpenAI 兼容端点，包括 DeepSeek、Azure OpenAI、OneAPI、自托管 vLLM 等）、`ANTHROPIC_API_KEY`、其他 provider 见 PydanticAI 文档。这意味着 yapi 永远不会因为"key 没设"在装饰器期或构造期失败——错误只能在请求期由 pydantic-ai 自己抛出，最终被包装成 `RuntimeExecutionError`。
- 设为字面量 `test`：PydanticAI 内置 `TestModel` 接管，零 API key、零网络，按响应模型 schema 生成占位结构。**离线冒烟首选**。
- 注意 yapi **不读 `.env` 文件**——任何 env 注入都由启动器负责（本地推荐 `uvicorn --env-file .env`，CI 用 secrets→env，生产用 systemd/k8s）。这是有意的 12-factor 设计：不依赖 `python-dotenv`，部署形态由部署侧决定。

### 关于"为什么 import example 就有 warning"

未设 `YAPI_MODEL` 时，`PromptRouter()` 构造期会发 `YapiUsageWarning("YAPI_MODEL not set; the first request to a prompt route will raise. ...")`。这就是 `examples/wish_api.py` / `examples/mixed_router.py` / `examples/with_depends.py` 在 `import` 时出现 warning 的根本原因（`examples/custom_runner.py` 传了自定义 runner 不触发）。这是 spec §6.4 明文要求的"真实启动期最早预警"——**不要静音它**。

测试场景如何避免：单元测试普遍传 `PromptRouter(agent_runner=lambda **_: {...})`，跳过 `build_default_runner`，warning 不会出现；端到端 smoke 设 `YAPI_MODEL=test` 也不会出现。

跨测试场景大多通过 `PromptRouter(agent_runner=lambda **_: {...})` 或自定义 class runner 注入 fake runner 绕开 `YAPI_MODEL`，详见 [`../architecture/agent-runner-contract.md`](../architecture/agent-runner-contract.md)。CI 与 release 流水线均依赖 `YAPI_MODEL=test` 做离线冒烟，因此发版无需配置任何 LLM provider secret。
