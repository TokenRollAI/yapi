# yapi v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal Prompt-first HTTP framework on top of FastAPI, Pydantic, and PydanticAI that supports declarative POST routes, structured responses, state persistence, and a working demo.

**Architecture:** `PromptRouter` compiles route declarations into FastAPI handlers, `PromptEndpoint` stores immutable endpoint definitions, `Runtime` executes requests against PydanticAI with state context and state patch tools, and `StateStore` persists state through memory and local-file implementations. The first version stays intentionally narrow: POST-only, a single PydanticAI-backed runtime, explicit state-key resolution, and minimal query/tool support.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, PydanticAI, pytest

---

## File map

### Package files
- Create: `pyproject.toml` — project metadata, runtime dependencies, pytest config
- Create: `yapi/__init__.py` — public exports
- Create: `yapi/router.py` — `PromptRouter` and `llm_post()` decorator
- Create: `yapi/endpoint.py` — `PromptEndpoint` definition
- Create: `yapi/runtime.py` — request execution, prompt assembly, state patch tracking
- Create: `yapi/state.py` — state-key resolver and patch merge helpers
- Create: `yapi/storage.py` — `StateStore`, `MemoryStorage`, `LocalStorage`
- Create: `yapi/errors.py` — framework-specific exception types
- Create: `yapi/models.py` — runtime context models used internally by the agent

### Demo files
- Create: `examples/wish_api.py` — showcase application that proves zero-business-code routing

### Test files
- Create: `tests/test_storage.py` — storage behavior tests
- Create: `tests/test_state.py` — key resolution and patch merge tests
- Create: `tests/test_router.py` — route registration and OpenAPI exposure tests
- Create: `tests/test_runtime.py` — runtime behavior with a fake agent runner
- Create: `tests/test_integration.py` — FastAPI end-to-end tests with state persistence
- Create: `tests/conftest.py` — shared fixtures for app creation and fake runtime

---

### Task 1: Bootstrap the package skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `yapi/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing package import test**

```python
from yapi import PromptRouter, MemoryStorage, LocalStorage


def test_public_exports_are_available() -> None:
    assert PromptRouter is not None
    assert MemoryStorage is not None
    assert LocalStorage is not None
```

Add this to `tests/test_storage.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py::test_public_exports_are_available -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yapi'`

- [ ] **Step 3: Write minimal package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "yapi"
version = "0.1.0"
description = "Prompt-first declarative HTTP framework"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1",
  "pydantic>=2.7,<3",
  "pydantic-ai>=0.0.18,<1",
  "uvicorn>=0.30,<1",
]

[project.optional-dependencies]
dev = [
  "httpx>=0.27,<1",
  "pytest>=8.2,<9",
  "pytest-asyncio>=0.23,<1",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create `yapi/__init__.py`:

```python
from yapi.router import PromptRouter
from yapi.storage import LocalStorage, MemoryStorage

__all__ = ["LocalStorage", "MemoryStorage", "PromptRouter"]
```

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture
def no_op() -> None:
    return None
```

- [ ] **Step 4: Add placeholder implementations required for import**

Create `yapi/router.py`:

```python
class PromptRouter:
    pass
```

Create `yapi/storage.py`:

```python
class MemoryStorage:
    pass


class LocalStorage:
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_storage.py::test_public_exports_are_available -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml yapi/__init__.py yapi/router.py yapi/storage.py tests/conftest.py tests/test_storage.py
git commit -m "chore: bootstrap yapi package skeleton"
```

---

### Task 2: Build storage implementations

**Files:**
- Modify: `yapi/storage.py`
- Create: `yapi/errors.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Replace `tests/test_storage.py` with:

```python
import json

from yapi.storage import LocalStorage, MemoryStorage


def test_public_exports_are_available() -> None:
    assert MemoryStorage is not None
    assert LocalStorage is not None


def test_memory_storage_round_trip() -> None:
    storage = MemoryStorage()
    storage.save("user:1", {"mood": "calm"})

    assert storage.load("user:1") == {"mood": "calm"}


def test_memory_storage_returns_none_for_missing_key() -> None:
    storage = MemoryStorage()

    assert storage.load("missing") is None


def test_local_storage_round_trip(tmp_path) -> None:
    storage = LocalStorage(path=tmp_path / "state.json")
    storage.save("user:1", {"mood": "curious"})

    assert storage.load("user:1") == {"mood": "curious"}


def test_local_storage_persists_json_object(tmp_path) -> None:
    path = tmp_path / "state.json"
    storage = LocalStorage(path=path)
    storage.save("user:1", {"mood": "curious"})

    payload = json.loads(path.read_text())
    assert payload == {"user:1": {"mood": "curious"}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `AttributeError` for missing `load` / `save`

- [ ] **Step 3: Implement storage errors and protocol**

Create `yapi/errors.py`:

```python
class YapiError(Exception):
    pass


class StateStoreError(YapiError):
    pass
```

Replace `yapi/storage.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from yapi.errors import StateStoreError


class StateStore(Protocol):
    def load(self, key: str) -> dict | None: ...
    def save(self, key: str, state: dict) -> None: ...


class MemoryStorage:
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    def load(self, key: str) -> dict | None:
        item = self._items.get(key)
        return None if item is None else dict(item)

    def save(self, key: str, state: dict) -> None:
        self._items[key] = dict(state)


class LocalStorage:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self, key: str) -> dict | None:
        payload = self._read_all()
        item = payload.get(key)
        return None if item is None else dict(item)

    def save(self, key: str, state: dict) -> None:
        payload = self._read_all()
        payload[key] = dict(state)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def _read_all(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}

        try:
            data = json.loads(self._path.read_text())
        except json.JSONDecodeError as exc:
            raise StateStoreError(f"Invalid state file: {self._path}") from exc

        if not isinstance(data, dict):
            raise StateStoreError(f"State file must contain an object: {self._path}")

        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/errors.py yapi/storage.py tests/test_storage.py
git commit -m "feat: add state storage implementations"
```

---

### Task 3: Add state-key resolution and patch merge helpers

**Files:**
- Create: `yapi/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing state helper tests**

Create `tests/test_state.py`:

```python
from pydantic import BaseModel

from yapi.state import merge_state_patch, resolve_state_key


class WishRequest(BaseModel):
    user_id: str
    wish: str


class SessionRequest(BaseModel):
    session_id: str
    prompt: str


def test_resolve_state_key_prefers_explicit_field() -> None:
    request = WishRequest(user_id="u-1", wish="rain")

    assert resolve_state_key(request, state_key="user_id") == "u-1"


def test_resolve_state_key_uses_default_user_id_field() -> None:
    request = WishRequest(user_id="u-1", wish="rain")

    assert resolve_state_key(request) == "u-1"


def test_resolve_state_key_uses_default_session_id_field() -> None:
    request = SessionRequest(session_id="s-1", prompt="hi")

    assert resolve_state_key(request) == "s-1"


def test_resolve_state_key_rejects_missing_identifier() -> None:
    class UnknownRequest(BaseModel):
        prompt: str

    request = UnknownRequest(prompt="hi")

    try:
        resolve_state_key(request)
    except ValueError as exc:
        assert "state key" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_merge_state_patch_overwrites_and_preserves_keys() -> None:
    current = {"mood": "calm", "count": 1}
    patch = {"mood": "stormy", "last_wish": "moon"}

    assert merge_state_patch(current, patch) == {
        "mood": "stormy",
        "count": 1,
        "last_wish": "moon",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yapi.state'`

- [ ] **Step 3: Implement state helpers**

Create `yapi/state.py`:

```python
from __future__ import annotations

from pydantic import BaseModel

DEFAULT_STATE_KEY_FIELDS = ("user_id", "session_id")


def resolve_state_key(request: BaseModel, state_key: str | None = None) -> str:
    payload = request.model_dump()

    if state_key is not None:
        value = payload.get(state_key)
        if value is None:
            raise ValueError(f"Configured state key '{state_key}' is missing")
        return str(value)

    for field_name in DEFAULT_STATE_KEY_FIELDS:
        value = payload.get(field_name)
        if value is not None:
            return str(value)

    raise ValueError("Unable to resolve state key from request")


def merge_state_patch(current: dict, patch: dict) -> dict:
    merged = dict(current)
    merged.update(patch)
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/state.py tests/test_state.py
git commit -m "feat: add state key and patch helpers"
```

---

### Task 4: Define endpoint and runtime context models

**Files:**
- Create: `yapi/endpoint.py`
- Create: `yapi/models.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing endpoint-definition tests**

Create `tests/test_runtime.py`:

```python
from pydantic import BaseModel

from yapi.endpoint import PromptEndpoint


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    granted: bool
    message: str


def test_prompt_endpoint_stores_definition() -> None:
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        prompt="grant wishes",
        request_model=WishRequest,
        response_model=WishResponse,
        state_key="user_id",
        enable_query=False,
        state_dependencies=(),
    )

    assert endpoint.path == "/wish"
    assert endpoint.method == "POST"
    assert endpoint.prompt == "grant wishes"
    assert endpoint.request_model is WishRequest
    assert endpoint.response_model is WishResponse
    assert endpoint.state_key == "user_id"
    assert endpoint.enable_query is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runtime.py::test_prompt_endpoint_stores_definition -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yapi.endpoint'`

- [ ] **Step 3: Implement endpoint and runtime context types**

Create `yapi/endpoint.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from yapi.storage import StateStore


@dataclass(frozen=True)
class PromptEndpoint:
    path: str
    method: str
    prompt: str
    request_model: type[BaseModel]
    response_model: type[BaseModel]
    state_storage: StateStore | None = None
    state_key: str | None = None
    enable_query: bool = False
    state_dependencies: tuple[Any, ...] = ()
```

Create `yapi/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeContext:
    request: dict
    state: dict
    injected: dict
    state_patch: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runtime.py::test_prompt_endpoint_stores_definition -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/endpoint.py yapi/models.py tests/test_runtime.py
git commit -m "feat: add endpoint definition types"
```

---

### Task 5: Implement runtime prompt assembly and state patch tracking

**Files:**
- Modify: `yapi/runtime.py`
- Modify: `yapi/models.py`
- Modify: `yapi/errors.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing runtime helper tests**

Append to `tests/test_runtime.py`:

```python
from yapi.models import RuntimeContext
from yapi.runtime import Runtime


def test_runtime_builds_context_sections() -> None:
    runtime = Runtime(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    context = runtime.build_context(
        request_data={"user_id": "u-1", "wish": "moon"},
        state={"mood": "calm"},
        injected={"profile": {"vip": True}},
    )

    assert context.request == {"user_id": "u-1", "wish": "moon"}
    assert context.state == {"mood": "calm"}
    assert context.injected == {"profile": {"vip": True}}


def test_runtime_updates_state_patch() -> None:
    runtime = Runtime(agent_runner=lambda **_: {"granted": True, "message": "ok"})
    context = RuntimeContext(request={}, state={}, injected={})

    runtime.update_state(context, {"mood": "joyful"})
    runtime.update_state(context, {"count": 2})

    assert context.state_patch == {"mood": "joyful", "count": 2}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runtime.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yapi.runtime'`

- [ ] **Step 3: Implement runtime helpers**

Append to `yapi/errors.py`:

```python
class RuntimeExecutionError(YapiError):
    pass
```

Create `yapi/runtime.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from yapi.models import RuntimeContext
from yapi.state import merge_state_patch


class Runtime:
    def __init__(self, agent_runner: Callable[..., dict]) -> None:
        self._agent_runner = agent_runner

    def build_context(self, request_data: dict, state: dict, injected: dict) -> RuntimeContext:
        return RuntimeContext(
            request=dict(request_data),
            state=dict(state),
            injected=dict(injected),
        )

    def update_state(self, context: RuntimeContext, patch: dict) -> None:
        context.state_patch = merge_state_patch(context.state_patch, patch)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/errors.py yapi/models.py yapi/runtime.py tests/test_runtime.py
git commit -m "feat: add runtime context helpers"
```

---

### Task 6: Execute requests through the runtime and persist state

**Files:**
- Modify: `yapi/runtime.py`
- Modify: `yapi/endpoint.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing runtime execution tests**

Append to `tests/test_runtime.py`:

```python
from yapi.storage import MemoryStorage


def test_runtime_executes_agent_and_returns_response_model() -> None:
    storage = MemoryStorage()
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        prompt="grant wishes",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=storage,
        state_key="user_id",
    )

    runtime = Runtime(
        agent_runner=lambda **_: {"granted": True, "message": "granted"},
    )

    response = runtime.execute(
        endpoint=endpoint,
        request_model=WishRequest(user_id="u-1", wish="moon"),
        injected={"profile": {"vip": True}},
    )

    assert response.model_dump() == {"granted": True, "message": "granted"}


def test_runtime_persists_merged_state_patch() -> None:
    storage = MemoryStorage()
    storage.save("u-1", {"mood": "calm"})
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        prompt="grant wishes",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=storage,
        state_key="user_id",
    )

    def fake_agent_runner(**kwargs):
        kwargs["update_state"]({"mood": "stormy", "last_wish": "moon"})
        return {"granted": True, "message": "granted"}

    runtime = Runtime(agent_runner=fake_agent_runner)

    runtime.execute(
        endpoint=endpoint,
        request_model=WishRequest(user_id="u-1", wish="moon"),
        injected={},
    )

    assert storage.load("u-1") == {"mood": "stormy", "last_wish": "moon"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runtime.py -v`
Expected: FAIL with `AttributeError: 'Runtime' object has no attribute 'execute'`

- [ ] **Step 3: Implement runtime execution**

Update `yapi/runtime.py` to:

```python
from __future__ import annotations

from collections.abc import Callable

from yapi.endpoint import PromptEndpoint
from yapi.errors import RuntimeExecutionError
from yapi.models import RuntimeContext
from yapi.state import merge_state_patch, resolve_state_key


class Runtime:
    def __init__(self, agent_runner: Callable[..., dict]) -> None:
        self._agent_runner = agent_runner

    def build_context(self, request_data: dict, state: dict, injected: dict) -> RuntimeContext:
        return RuntimeContext(
            request=dict(request_data),
            state=dict(state),
            injected=dict(injected),
        )

    def update_state(self, context: RuntimeContext, patch: dict) -> None:
        context.state_patch = merge_state_patch(context.state_patch, patch)

    def execute(self, endpoint: PromptEndpoint, request_model, injected: dict):
        request_data = request_model.model_dump()
        state_key = resolve_state_key(request_model, endpoint.state_key)
        storage = endpoint.state_storage
        state = {} if storage is None else (storage.load(state_key) or {})
        context = self.build_context(request_data=request_data, state=state, injected=injected)

        try:
            payload = self._agent_runner(
                prompt=endpoint.prompt,
                request=request_data,
                state=context.state,
                injected=context.injected,
                update_state=lambda patch: self.update_state(context, patch),
                response_model=endpoint.response_model,
                enable_query=endpoint.enable_query,
            )
        except Exception as exc:
            raise RuntimeExecutionError("Agent execution failed") from exc

        if context.state_patch and storage is not None:
            storage.save(state_key, merge_state_patch(context.state, context.state_patch))

        return endpoint.response_model.model_validate(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/runtime.py tests/test_runtime.py
git commit -m "feat: execute prompt endpoints through runtime"
```

---

### Task 7: Register declarative POST routes with FastAPI

**Files:**
- Modify: `yapi/router.py`
- Modify: `yapi/__init__.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write failing router tests**

Create `tests/test_router.py`:

```python
from fastapi import FastAPI
from pydantic import BaseModel

from yapi import MemoryStorage, PromptRouter


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    granted: bool
    message: str


def test_llm_post_registers_fastapi_route() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.llm_post(
        "/wish",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=MemoryStorage(),
    )
    def make_a_wish():
        """grant wishes"""

    app.include_router(router)

    paths = {(route.path, tuple(route.methods)) for route in app.routes}
    assert ("/wish", ("POST",)) in paths


def test_openapi_uses_declared_models() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.llm_post(
        "/wish",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=MemoryStorage(),
    )
    def make_a_wish():
        """grant wishes"""

    app.include_router(router)
    schema = app.openapi()

    assert "/wish" in schema["paths"]
    operation = schema["paths"]["/wish"]["post"]
    assert operation["requestBody"] is not None
    assert operation["responses"]["200"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_router.py -v`
Expected: FAIL because `PromptRouter` has no `llm_post`

- [ ] **Step 3: Implement route registration**

Replace `yapi/router.py` with:

```python
from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import APIRouter

from yapi.endpoint import PromptEndpoint
from yapi.runtime import Runtime


class PromptRouter(APIRouter):
    def __init__(self, agent_runner: Callable[..., dict]) -> None:
        super().__init__()
        self._runtime = Runtime(agent_runner=agent_runner)

    def llm_post(
        self,
        path: str,
        *,
        request_model,
        response_model,
        state_storage=None,
        state_key: str | None = None,
        enable_query: bool = False,
        state_dependencies: Sequence | None = None,
    ):
        def decorator(prompt_factory):
            prompt = (prompt_factory.__doc__ or "").strip()
            endpoint = PromptEndpoint(
                path=path,
                method="POST",
                prompt=prompt,
                request_model=request_model,
                response_model=response_model,
                state_storage=state_storage,
                state_key=state_key,
                enable_query=enable_query,
                state_dependencies=tuple(state_dependencies or ()),
            )

            async def handler(request: request_model):
                return self._runtime.execute(
                    endpoint=endpoint,
                    request_model=request,
                    injected={},
                )

            self.add_api_route(
                path,
                handler,
                methods=["POST"],
                response_model=response_model,
            )
            return prompt_factory

        return decorator
```

Update `yapi/__init__.py`:

```python
from yapi.router import PromptRouter
from yapi.storage import LocalStorage, MemoryStorage

__all__ = ["LocalStorage", "MemoryStorage", "PromptRouter"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/router.py yapi/__init__.py tests/test_router.py
git commit -m "feat: register declarative prompt routes"
```

---

### Task 8: Support state dependency injection for handlers

**Files:**
- Modify: `yapi/router.py`
- Modify: `yapi/runtime.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write failing dependency injection integration test**

Create `tests/test_integration.py`:

```python
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import MemoryStorage, PromptRouter


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    granted: bool
    message: str


def test_state_dependencies_are_injected_into_runtime() -> None:
    app = FastAPI()
    storage = MemoryStorage()

    def fake_agent_runner(**kwargs):
        injected = kwargs["injected"]
        return {
            "granted": injected["dependency_0"]["vip"],
            "message": "vip granted",
        }

    router = PromptRouter(agent_runner=fake_agent_runner)

    def fetch_profile(user_id: str) -> dict:
        return {"vip": user_id == "u-1"}

    @router.llm_post(
        "/wish",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=storage,
        state_dependencies=[Depends(fetch_profile)],
    )
    def make_a_wish():
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)

    response = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert response.status_code == 200
    assert response.json() == {"granted": True, "message": "vip granted"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_state_dependencies_are_injected_into_runtime -v`
Expected: FAIL because the handler always passes empty `injected`

- [ ] **Step 3: Implement dependency injection plumbing**

Update `yapi/router.py` to add a dependency runner closure for each dependency:

```python
from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence

from fastapi import APIRouter

from yapi.endpoint import PromptEndpoint
from yapi.runtime import Runtime


class PromptRouter(APIRouter):
    def __init__(self, agent_runner: Callable[..., dict]) -> None:
        super().__init__()
        self._runtime = Runtime(agent_runner=agent_runner)

    def llm_post(
        self,
        path: str,
        *,
        request_model,
        response_model,
        state_storage=None,
        state_key: str | None = None,
        enable_query: bool = False,
        state_dependencies: Sequence | None = None,
    ):
        def decorator(prompt_factory):
            prompt = (prompt_factory.__doc__ or "").strip()
            endpoint = PromptEndpoint(
                path=path,
                method="POST",
                prompt=prompt,
                request_model=request_model,
                response_model=response_model,
                state_storage=state_storage,
                state_key=state_key,
                enable_query=enable_query,
                state_dependencies=tuple(state_dependencies or ()),
            )

            async def handler(request: request_model):
                injected = {}
                for index, dependency in enumerate(endpoint.state_dependencies):
                    dependency_callable = getattr(dependency, "dependency", dependency)
                    signature = inspect.signature(dependency_callable)
                    kwargs = {
                        name: getattr(request, name)
                        for name in signature.parameters
                        if hasattr(request, name)
                    }
                    injected[f"dependency_{index}"] = dependency_callable(**kwargs)

                return self._runtime.execute(
                    endpoint=endpoint,
                    request_model=request,
                    injected=injected,
                )

            self.add_api_route(
                path,
                handler,
                methods=["POST"],
                response_model=response_model,
            )
            return prompt_factory

        return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_integration.py::test_state_dependencies_are_injected_into_runtime -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/router.py tests/test_integration.py
git commit -m "feat: inject state dependencies into runtime"
```

---

### Task 9: Add structured runtime prompt assembly for the agent runner

**Files:**
- Modify: `yapi/runtime.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Write failing prompt assembly test**

Append to `tests/test_runtime.py`:

```python

def test_runtime_sends_structured_context_to_agent_runner() -> None:
    captured = {}
    storage = MemoryStorage()
    storage.save("u-1", {"mood": "calm"})
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        prompt="grant wishes",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=storage,
        state_key="user_id",
    )

    def fake_agent_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    runtime = Runtime(agent_runner=fake_agent_runner)
    runtime.execute(
        endpoint=endpoint,
        request_model=WishRequest(user_id="u-1", wish="moon"),
        injected={"dependency_0": {"vip": True}},
    )

    assert captured["prompt"] == "grant wishes"
    assert captured["request"] == {"user_id": "u-1", "wish": "moon"}
    assert captured["state"] == {"mood": "calm"}
    assert captured["injected"] == {"dependency_0": {"vip": True}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime.py::test_runtime_sends_structured_context_to_agent_runner -v`
Expected: FAIL if runtime call signature differs from expected sections

- [ ] **Step 3: Normalize agent-runner payload shape**

Update the `self._agent_runner(...)` call inside `Runtime.execute()` so it always passes exactly these keyword arguments:

```python
payload = self._agent_runner(
    prompt=endpoint.prompt,
    request=context.request,
    state=context.state,
    injected=context.injected,
    update_state=lambda patch: self.update_state(context, patch),
    response_model=endpoint.response_model,
    enable_query=endpoint.enable_query,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/runtime.py tests/test_runtime.py
git commit -m "refactor: standardize runtime agent payload"
```

---

### Task 10: Add a real PydanticAI-backed default agent runner

**Files:**
- Create: `yapi/agent.py`
- Modify: `yapi/router.py`
- Modify: `yapi/runtime.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write failing integration test for default runner**

Append to `tests/test_integration.py`:

```python
from yapi.agent import build_agent_runner


def test_build_agent_runner_returns_callable() -> None:
    runner = build_agent_runner()

    assert callable(runner)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_build_agent_runner_returns_callable -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'yapi.agent'`

- [ ] **Step 3: Implement the default runner builder**

Create `yapi/agent.py`:

```python
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def build_agent_runner() -> Callable[..., dict]:
    def runner(
        *,
        prompt: str,
        request: dict,
        state: dict,
        injected: dict,
        update_state,
        response_model,
        enable_query: bool,
    ) -> dict:
        raise NotImplementedError(
            "Connect this runner to pydantic_ai.Agent in the next step"
        )

    return runner
```

Update `yapi/router.py` constructor to accept `agent_runner: Callable[..., dict] | None = None` and create the default runner when `None` is provided:

```python
from yapi.agent import build_agent_runner

class PromptRouter(APIRouter):
    def __init__(self, agent_runner: Callable[..., dict] | None = None) -> None:
        super().__init__()
        self._runtime = Runtime(agent_runner=agent_runner or build_agent_runner())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_integration.py::test_build_agent_runner_returns_callable -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/agent.py yapi/router.py tests/test_integration.py
git commit -m "feat: add default agent runner builder"
```

---

### Task 11: Wire the default runner to PydanticAI and state-update tooling

**Files:**
- Modify: `yapi/agent.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write failing fake-agent compatibility test**

Append to `tests/test_integration.py`:

```python

def test_default_runner_raises_clear_error_without_model_configuration() -> None:
    runner = build_agent_runner()

    try:
        runner(
            prompt="grant wishes",
            request={"user_id": "u-1", "wish": "moon"},
            state={},
            injected={},
            update_state=lambda patch: None,
            response_model=WishResponse,
            enable_query=False,
        )
    except NotImplementedError as exc:
        assert "pydantic_ai.Agent" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError")
```

- [ ] **Step 2: Run test to verify it passes before implementation**

Run: `pytest tests/test_integration.py::test_default_runner_raises_clear_error_without_model_configuration -v`
Expected: PASS

- [ ] **Step 3: Replace the stub with a real Agent integration**

Replace `yapi/agent.py` with:

```python
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext


@dataclass
class AgentDeps:
    request: dict
    state: dict
    injected: dict
    update_state: Callable[[dict], None]


DEFAULT_SYSTEM_PREFIX = (
    "You are the execution engine behind a declarative HTTP endpoint. "
    "Return data that matches the required response model exactly."
)


def build_agent_runner(model: str | None = None) -> Callable[..., dict]:
    configured_model = model or os.getenv("YAPI_MODEL")

    def runner(
        *,
        prompt: str,
        request: dict,
        state: dict,
        injected: dict,
        update_state,
        response_model: type[BaseModel],
        enable_query: bool,
    ) -> dict:
        if configured_model is None:
            raise NotImplementedError("Connect pydantic_ai.Agent by setting YAPI_MODEL")

        agent = Agent(
            configured_model,
            deps_type=AgentDeps,
            result_type=response_model,
            system_prompt=f"{DEFAULT_SYSTEM_PREFIX}\n\n{prompt}",
        )

        @agent.tool_plain
        def update_state_tool(patch: dict[str, Any]) -> str:
            update_state(dict(patch))
            return "ok"

        deps = AgentDeps(
            request=request,
            state=state,
            injected=injected,
            update_state=update_state,
        )

        user_prompt = (
            f"request={request}\n"
            f"state={state}\n"
            f"injected={injected}\n"
            f"enable_query={enable_query}"
        )
        result = agent.run_sync(user_prompt, deps=deps)
        return result.output.model_dump()

    return runner
```

- [ ] **Step 4: Run compatibility tests**

Run: `pytest tests/test_integration.py::test_build_agent_runner_returns_callable tests/test_integration.py::test_default_runner_raises_clear_error_without_model_configuration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yapi/agent.py tests/test_integration.py
git commit -m "feat: integrate default runner with pydanticai"
```

---

### Task 12: Prove end-to-end state persistence through FastAPI

**Files:**
- Modify: `tests/test_integration.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write failing state-persistence integration test**

Append to `tests/test_integration.py`:

```python

def test_repeated_requests_observe_persisted_state() -> None:
    app = FastAPI()
    storage = MemoryStorage()

    def fake_agent_runner(**kwargs):
        state = kwargs["state"]
        request = kwargs["request"]
        seen_count = state.get("seen_count", 0) + 1
        kwargs["update_state"]({"seen_count": seen_count, "last_wish": request["wish"]})
        return {
            "granted": True,
            "message": f"wish #{seen_count}: {request['wish']}",
        }

    router = PromptRouter(agent_runner=fake_agent_runner)

    @router.llm_post(
        "/wish",
        request_model=WishRequest,
        response_model=WishResponse,
        state_storage=storage,
    )
    def make_a_wish():
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)

    first = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    second = client.post("/wish", json={"user_id": "u-1", "wish": "stars"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"granted": True, "message": "wish #1: moon"}
    assert second.json() == {"granted": True, "message": "wish #2: stars"}
    assert storage.load("u-1") == {"seen_count": 2, "last_wish": "stars"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_repeated_requests_observe_persisted_state -v`
Expected: FAIL if route handling or state persistence is incomplete

- [ ] **Step 3: Fix any missing runtime/router wiring with the smallest code change**

Use the failing traceback to patch only the missing behavior. The intended steady-state is:

```python
response = runtime.execute(
    endpoint=endpoint,
    request_model=request,
    injected=injected,
)
```

and

```python
if context.state_patch and storage is not None:
    storage.save(state_key, merge_state_patch(context.state, context.state_patch))
```

- [ ] **Step 4: Run all integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py yapi/router.py yapi/runtime.py
git commit -m "test: prove end-to-end state persistence"
```

---

### Task 13: Add a showcase app that demonstrates the framework

**Files:**
- Create: `examples/wish_api.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write failing smoke test for example import**

Append to `tests/test_router.py`:

```python

def test_example_application_imports() -> None:
    from examples.wish_api import app

    assert app is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_router.py::test_example_application_imports -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'examples.wish_api'`

- [ ] **Step 3: Implement the showcase application**

Create `examples/wish_api.py`:

```python
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from yapi import LocalStorage, PromptRouter


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    granted: bool
    message: str
    remembered_mood: str | None = None


storage = LocalStorage(path="./app_state.json")
app = FastAPI(title="yapi showcase")
router = PromptRouter()


def fetch_profile(user_id: str) -> dict:
    return {"vip": user_id.startswith("vip-")}


@router.llm_post(
    "/wish",
    request_model=WishIn,
    response_model=WishOut,
    state_storage=storage,
    state_dependencies=[Depends(fetch_profile)],
)
def make_a_wish():
    """
    You are a wish-granting entity.
    Decide whether the wish is granted.
    Use the current request, persisted state, and injected profile.
    If the user reveals a mood, store it in state for future requests.
    """


app.include_router(router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_router.py::test_example_application_imports -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/wish_api.py tests/test_router.py
git commit -m "feat: add yapi showcase application"
```

---

### Task 14: Verify the full test suite and manual app startup

**Files:**
- Modify: `examples/wish_api.py` (only if startup issues appear)
- Test: `tests/test_storage.py`
- Test: `tests/test_state.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_router.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: PASS across storage, state, runtime, router, and integration tests

- [ ] **Step 2: Start the showcase app manually**

Run: `uvicorn examples.wish_api:app --reload`
Expected: Uvicorn starts successfully and exposes `/docs`

- [ ] **Step 3: Smoke-test the endpoint manually**

Run:

```bash
curl -X POST http://127.0.0.1:8000/wish \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u-1","wish":"moon"}'
```

Expected: HTTP 200 with JSON matching `WishOut`

- [ ] **Step 4: Commit final verification fixes if needed**

```bash
git add examples/wish_api.py yapi tests
git commit -m "chore: verify yapi v0 end-to-end"
```

---

## Self-review

### Spec coverage
- Declarative POST route support: Tasks 4, 7, 8
- Strong request/response typing: Tasks 6, 7, 12
- State persistence: Tasks 2, 3, 5, 6, 12
- PydanticAI-backed runtime: Tasks 9, 10, 11
- Minimal local and memory storage: Task 2
- Demo app and OpenAPI feel: Tasks 7, 13, 14
- Clear non-goals are respected: no multi-provider abstraction, no middleware/plugin system, no advanced query platform tasks included

### Placeholder scan
- No `TODO`, `TBD`, or “implement later” placeholders remain in task instructions.
- The only intentionally incomplete stage is Task 10’s temporary `NotImplementedError`, which is explicitly consumed and replaced in Task 11.

### Type consistency
- `PromptRouter`, `PromptEndpoint`, `Runtime`, `StateStore`, `MemoryStorage`, and `LocalStorage` use the same names across all tasks.
- `resolve_state_key`, `merge_state_patch`, and `build_agent_runner` are introduced before downstream usage.
- Request/response test models use the same `WishRequest` and `WishResponse` names across runtime, router, and integration tasks.
