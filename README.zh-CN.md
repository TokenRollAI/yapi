# yapi

[![PyPI](https://img.shields.io/pypi/v/pyyapi.svg)](https://pypi.org/project/pyyapi/)
[![Python](https://img.shields.io/pypi/pyversions/pyyapi.svg)](https://pypi.org/project/pyyapi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> English version: [README.md](./README.md)

**Prompt-first 声明式 HTTP 框架** —— 写一个带 docstring 的普通 Python 函数，就能得到一个由 LLM 驱动、返回结构化 JSON 的 HTTP 接口。

`yapi` 是 [FastAPI](https://fastapi.tiangolo.com/) 与 [PydanticAI](https://ai.pydantic.dev/) 之上的薄层封装。`PromptRouter` 是 `fastapi.APIRouter` 的真正 *superset*：原生 FastAPI 路由原样可用，prompt 路由进入 `router.prompt.*` 子命名空间。

> PyPI 包名是 `pyyapi`（未加前缀的 `yapi` 已被 2018 年同名项目占用），import 路径仍为 `yapi`。

## 安装

```bash
pip install pyyapi
```

需要 Python 3.12+。

## 快速开始

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


app = FastAPI(title="yapi showcase")
router = PromptRouter()


@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""


app.include_router(router)
```

启动：

```bash
YAPI_MODEL=test uvicorn examples.wish_api:app --reload
```

`YAPI_MODEL=test` 启用 PydanticAI 内置 `TestModel` —— 无需 API key、无需联网，适合离线 smoke。真实模型用 `YAPI_MODEL=openai:gpt-4o` / `YAPI_MODEL=anthropic:claude-3-5-sonnet` 之类。

打开 `http://localhost:8000/docs` 可看到自动生成的 OpenAPI UI。

## 同一个 router 混挂普通路由与 prompt 路由

`PromptRouter` 现在是 `APIRouter` 的真正 superset：`.get/.post/...` 保持 FastAPI 原生行为；只有 `router.prompt.*` 才进入 LLM 流水线。

```python
router = PromptRouter(prefix="/v1", tags=["wishes"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""
```

## 配置

`yapi` 完全通过环境变量配置 —— 包内不读 `.env` 文件。请用支持注入的启动器（推荐 `uvicorn --env-file .env`；亦可用 shell 的 `set -a; source .env; set +a`、Docker `--env-file`、Kubernetes secrets 等）。

### `YAPI_MODEL`（使用默认 runner 时必填）

PydanticAI 的 `provider:model` 字符串。`PromptRouter()` 不传 `agent_runner` 时构造期一次性读取。

```bash
YAPI_MODEL=openai:gpt-4o              # OpenAI
YAPI_MODEL=anthropic:claude-3-5-sonnet # Anthropic
YAPI_MODEL=openai:deepseek-chat        # DeepSeek（OpenAI 兼容）
YAPI_MODEL=test                        # PydanticAI TestModel，无 key 无网络
```

未设置 → 构造期发出 `YapiUsageWarning`，第一次请求 HTTP 500。

> ⚠️ **模型必须支持 OpenAI Function Calling 的 `tool_choice` 参数。** `yapi` 走 PydanticAI 的结构化输出路径，会强制模型按你声明的响应 `BaseModel` 返回一次 tool call。不支持 `tool_choice` 的模型——典型如"推理 / 思考"系列（`deepseek-reasoner`、`deepseek-v4-flash`、`o1-preview` / `o1-mini` 等），或者只支持 chat / completion 的检查点——首次请求会以 `ModelHTTPError` 报 HTTP 500。请选明确声明支持 function calling 的模型（`gpt-4o`、`gpt-4o-mini`、`claude-3-5-sonnet`、`deepseek-chat` 等）。

### Provider 凭证（由 PydanticAI 直接读取）

`yapi` 不做任何校验，下列变量由底层 PydanticAI 通过 `os.environ` 读取：

| Provider | 环境变量 |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| OpenAI 兼容端点（DeepSeek、Azure OpenAI、OneAPI、本地服务等） | `OPENAI_API_KEY` + `OPENAI_BASE_URL`（如 `https://api.deepseek.com/v1`） |
| Anthropic | `ANTHROPIC_API_KEY` |
| 其它（Google、Groq、Mistral 等） | 见 [PydanticAI providers 文档](https://ai.pydantic.dev/models/) |

### `.env` 示例（DeepSeek）

```dotenv
YAPI_MODEL=openai:deepseek-chat
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

```bash
uv run uvicorn examples.wish_api:app --reload --env-file .env
```

> 与上方警告同源：DeepSeek 的"思考"系列（`deepseek-reasoner`、`deepseek-v4-flash`）不接受 `tool_choice`，在这里无法工作，请用 `deepseek-chat`。

## 请求生命周期

对每一次落到 `router.prompt.*` 路由的请求，`yapi` 会：

1. 按函数签名解析 path / query / header / cookie / body 参数（FastAPI 语义，再加最多一个 `BaseModel` 请求体）；
2. 同步或 `async def` 调用用户函数，可选地拿到一段**动态 prompt**（`return` 值，必须为 `None` 或 `str`）；
3. 拼装 system prompt：响应模型 docstring + 函数 docstring + 动态 prompt；
4. 用 `RunnerContext`（prompt、request、injected、response_model、path、method）调用 `agent_runner`（默认是 PydanticAI `Agent`）；
5. 用返回注解校验 agent 输出，再由 FastAPI 序列化为 JSON。

## 契约（硬约束）

下面规则只作用于 `router.prompt.*`：

- 返回注解 **必须** 是 `BaseModel` 子类。
- 至多一个参数是 `BaseModel`（请求体）。支持 `req: WishIn` 与 `req: Annotated[WishIn, Body()]` 两种风格。
- 其它参数必须二选一：
  - `Depends(...)` default 或 `Annotated[T, Depends(...)]`；
  - `Annotated[T, Query()/Header()/Cookie()/Path()/Form()/File()]` 或对应的 `= Query(...)` default。
- `*args` / `**kwargs` 装饰期被拒绝。
- 函数体必须 `return` `None` 或 `str`（动态 prompt），其它值请求期报错。
- `async def` 被支持。

装饰器 kwarg：

- 透传 FastAPI 白名单：`tags`、`summary`、`description`、`status_code`、`deprecated`、`operation_id`、`name`、`include_in_schema`、`responses`、`openapi_extra`。
- 装饰期 `YapiDeclarationError` 拒绝：`response_model`、`response_class`、`dependencies`。
- 其它未识别 kwarg 发 `YapiUsageWarning`。

所有违规都在装饰期同步抛 `YapiDeclarationError`，import / `include_router` 阶段就暴露。

## 依赖注入

```python
from fastapi import Depends
from typing import Annotated

def get_db():
    ...

@router.prompt.post("/wish")
def make_a_wish(
    req: WishIn,
    db: Annotated[Database, Depends(get_db)],
) -> WishOut:
    """..."""
    return f"user has {db.balance(req.user_id)} wishes left"
```

## 自定义 agent runner

实现 `AgentRunner` Protocol —— 任何具有 `.run(ctx: RunnerContext) -> dict | BaseModel` 方法的对象都满足：

```python
from yapi import AgentRunner, PromptRouter, RunnerContext

class MockRunner:
    def run(self, ctx: RunnerContext) -> dict:
        return {
            "granted": "moon" not in ctx.request["wish"].lower(),
            "message": f"path={ctx.path}",
        }

router = PromptRouter(agent_runner=MockRunner())
```

v2 的 `(*, prompt, request, injected, response_model) -> dict` 写法继续可用（内部走适配层）。

也可以注入 `prompt_composer=` 覆盖 system prompt 拼接策略。

## 开发

```bash
uv sync --extra dev
uv run pytest
uv run uvicorn examples.wish_api:app --reload
```

## License

MIT
