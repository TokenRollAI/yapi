---
id: must.project-shape
title: 项目最小事实
layer: must
tags: [must, project-shape, runtime, packaging]
status: stable
---

# yapi 项目最小事实

## 这是什么项目

yapi 是一个 **prompt-first 的声明式 HTTP 框架**。开发者在 `PromptRouter` 上写 `@router.post("/path")` 装饰一个**有返回注解、有 docstring 的同步函数**；框架在请求期把"函数签名 + 模型 docstring + 函数 docstring + 函数返回的动态 prompt"组装成 system prompt，交给 PydanticAI Agent 生成符合返回注解的结构化响应，最后用 FastAPI 序列化为 JSON。

公开 API 表面**只有一个**符号：`PromptRouter`（`yapi/__init__.py`）。源码总规模 ~280 行（7 个 .py 文件），测试 ~300 行。

## 对齐的 spec

当前代码精确对齐 `docs/superpowers/specs/2026-05-21-yapi-v2-design.md`（v2）。v2 在头部明确取代 v1（`docs/superpowers/specs/2026-05-20-yapi-design.md`）的第 4、6、9、10 节：

- 装饰器命名从 `llm_post` 收回为复用 FastAPI 的 `.post/.get/...`。
- 装饰器不再接受 `request_model=` / `response_model=` / `state_*` 等显式参数；契约全部从函数签名推断。
- state / storage 暂时下线：仓库内**没有** `yapi/state.py`、`yapi/storage.py`，`PromptRouter.__init__` 没有 storage 参数，`Runtime` 没有 load/save 逻辑。

`docs/superpowers/plans/2026-05-20-yapi-v0-implementation.md` 是基于 v1 的实现 plan，**已过时**，不要按它创建 `yapi/state.py` / `yapi/storage.py` / `tests/test_storage.py`。

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

@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""

app = FastAPI()
app.include_router(router)
```

实例：`examples/wish_api.py`。

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

`PromptRouter()` 不传 `agent_runner` 时回退到默认 `yapi.agent.build_agent_runner()`，在工厂调用时**一次性绑定** `os.getenv("YAPI_MODEL")` 到闭包。

- 未设置：构造不报错；**第一次请求**时 runner 抛 `NotImplementedError("Connect pydantic_ai.Agent by setting YAPI_MODEL")`，被 `Runtime.execute` 包装为 `RuntimeExecutionError`，最终 FastAPI 转 HTTP 500。
- 设为模型字符串（如 `openai:gpt-4o`、`anthropic:claude-3-5-sonnet`、`openai:deepseek-chat`）：交给 `pydantic_ai.Agent(...)` 直接解析。**Provider 凭证由 pydantic-ai 在请求期直接读 `os.environ`**，yapi 全程不感知、不校验、不转发：`OPENAI_API_KEY` / `OPENAI_BASE_URL`（OpenAI 与所有 OpenAI 兼容端点，包括 DeepSeek、Azure OpenAI、OneAPI、自托管 vLLM 等）、`ANTHROPIC_API_KEY`、其他 provider 见 PydanticAI 文档。这意味着 yapi 永远不会因为"key 没设"在装饰器期或构造期失败——错误只能在请求期由 pydantic-ai 自己抛出，最终被包装成 `RuntimeExecutionError`。
- 设为字面量 `test`：PydanticAI 内置 `TestModel` 接管，零 API key、零网络，按响应模型 schema 生成占位结构。**离线冒烟首选**。
- 注意 yapi **不读 `.env` 文件**——任何 env 注入都由启动器负责（本地推荐 `uvicorn --env-file .env`，CI 用 secrets→env，生产用 systemd/k8s）。这是有意的 12-factor 设计：不依赖 `python-dotenv`，部署形态由部署侧决定。

跨测试场景大多通过 `PromptRouter(agent_runner=lambda **_: {...})` 注入 fake runner 绕开 `YAPI_MODEL`，详见 [`../architecture/agent-runner-contract.md`](../architecture/agent-runner-contract.md)。CI 与 release 流水线均依赖 `YAPI_MODEL=test` 做离线冒烟，因此发版无需配置任何 LLM provider secret。
