# yapi

[![PyPI](https://img.shields.io/pypi/v/pyyapi.svg)](https://pypi.org/project/pyyapi/)
[![Python](https://img.shields.io/pypi/pyversions/pyyapi.svg)](https://pypi.org/project/pyyapi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Prompt-first declarative HTTP framework** — write a normal Python function with a docstring, get an LLM-powered HTTP endpoint with structured JSON responses.

`yapi` is a thin layer on top of [FastAPI](https://fastapi.tiangolo.com/) and [PydanticAI](https://ai.pydantic.dev/). You declare an HTTP route by decorating a regular function; the framework takes the function signature, the response model's docstring, the function's docstring and any dynamic prompt it returns, composes them into a system prompt, and hands the result to a PydanticAI `Agent` to produce a validated `BaseModel` response.

> Package name on PyPI is `pyyapi` (the unhyphenated `yapi` was taken by a 2018 project). Import path is still `yapi`.

## Install

```bash
pip install pyyapi
```

Python 3.12+ required.

## Quick start

```python
from fastapi import FastAPI
from pydantic import BaseModel

from yapi import PromptRouter


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """You are a wish-granting entity. Decide whether to grant the wish."""

    granted: bool
    message: str


app = FastAPI(title="yapi showcase")
router = PromptRouter()


@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """Decide whether to grant the user's wish."""


app.include_router(router)
```

Run it:

```bash
YAPI_MODEL=test uvicorn examples.wish_api:app --reload
```

`YAPI_MODEL=test` activates PydanticAI's built-in `TestModel` — no API key, no network, perfect for offline smoke tests. For real models, set e.g. `YAPI_MODEL=openai:gpt-4o` or `YAPI_MODEL=anthropic:claude-3-5-sonnet`.

Open `http://localhost:8000/docs` for the auto-generated OpenAPI UI.

## Configuration

`yapi` is configured entirely through environment variables — the package never reads `.env` files itself. Use a launcher that injects them (recommended: `uvicorn --env-file .env`; alternatives: `set -a; source .env; set +a` in your shell, Docker `--env-file`, Kubernetes secrets, etc.).

### `YAPI_MODEL` (required for the default runner)

PydanticAI model string in `provider:model` form. Read once when `PromptRouter()` is constructed without an explicit `agent_runner`.

```bash
YAPI_MODEL=openai:gpt-4o              # OpenAI
YAPI_MODEL=anthropic:claude-3-5-sonnet # Anthropic
YAPI_MODEL=openai:deepseek-chat        # DeepSeek (OpenAI-compatible)
YAPI_MODEL=test                        # PydanticAI TestModel, no key, no network
```

Unset → first request returns HTTP 500.

### Provider credentials (read directly by PydanticAI)

`yapi` does **not** validate or even look at these — they are consumed by the underlying PydanticAI provider via `os.environ`:

| Provider | Env vars |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| OpenAI-compatible endpoints (DeepSeek, Azure OpenAI, OneAPI, local servers, …) | `OPENAI_API_KEY` + `OPENAI_BASE_URL` (e.g. `https://api.deepseek.com/v1`) |
| Anthropic | `ANTHROPIC_API_KEY` |
| Others (Google, Groq, Mistral, …) | See [PydanticAI providers docs](https://ai.pydantic.dev/models/) |

### Example `.env` (DeepSeek)

```dotenv
YAPI_MODEL=openai:deepseek-chat
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

```bash
uv run uvicorn examples.wish_api:app --reload --env-file .env
```

> ⚠️ DeepSeek's "thinking" models (`deepseek-reasoner`, `deepseek-v4-flash`) currently reject OpenAI Function Calling's `tool_choice` parameter, which PydanticAI uses by default for structured output. Use `deepseek-chat` for now.

## How it works

For each request, `yapi`:

1. parses the request body into the `BaseModel` you declared as a parameter,
2. calls your function synchronously to optionally produce a **dynamic prompt** (the function's `return` value, must be `None` or `str`),
3. composes the final system prompt from: response-model docstring + function docstring + dynamic prompt,
4. invokes the configured `agent_runner` (defaulting to a PydanticAI `Agent`) with the prompt + request payload,
5. validates the agent's output against your return annotation and serializes via FastAPI.

## Contract (hard rules)

- `PromptRouter` subclasses `fastapi.APIRouter` and overrides `.get/.post/.put/.patch/.delete`. All routes on a `PromptRouter` are prompt routes — don't mix plain FastAPI routes onto it.
- The decorator only accepts the path argument. FastAPI kwargs like `tags=`, `summary=`, `status_code=`, `response_class=`, `response_model=` are silently ignored.
- Return annotation **must** be a `BaseModel` subclass.
- At most one parameter may be a `BaseModel` (the request body). Other parameters must have `default=fastapi.Depends(...)`.
- Function body must `return` either `None` or a `str` (the dynamic prompt). Anything else raises at request time. `async def` is not supported.

Violations are raised as `YapiDeclarationError` at decoration time — broken routes fail at import, not at request time.

## Dependency injection

```python
from fastapi import Depends

def get_db():
    ...

@router.post("/wish")
def make_a_wish(req: WishIn, db = Depends(get_db)) -> WishOut:
    """..."""
    return f"user has {db.balance(req.user_id)} wishes left"
```

## Custom agent runner

`PromptRouter(agent_runner=...)` accepts any callable with the signature `(*, prompt, request, injected, response_model) -> dict`. Useful for tests:

```python
router = PromptRouter(
    agent_runner=lambda **_: {"granted": True, "message": "ok"},
)
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv run uvicorn examples.wish_api:app --reload
```

## License

MIT
