"""§8.3 Runner Protocol & RunnerContext tests."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import AgentRunner, PromptRouter, RunnerContext
from yapi.endpoint import PromptEndpoint
from yapi.runtime import Runtime


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """grant wishes"""

    granted: bool
    message: str


def test_protocol_runner_run_method_invoked() -> None:
    received: list[RunnerContext] = []

    class MyRunner:
        def run(self, ctx: RunnerContext) -> dict:
            received.append(ctx)
            return {"granted": True, "message": "from-class-runner"}

    assert isinstance(MyRunner(), AgentRunner)

    app = FastAPI()
    router = PromptRouter(agent_runner=MyRunner())

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "from-class-runner"
    assert len(received) == 1
    assert isinstance(received[0], RunnerContext)


def test_runner_context_carries_path_method() -> None:
    captured: list[RunnerContext] = []

    class CaptureRunner:
        def run(self, ctx: RunnerContext) -> dict:
            captured.append(ctx)
            return {"granted": True, "message": "ok"}

    app = FastAPI()
    router = PromptRouter(agent_runner=CaptureRunner())

    @router.prompt.put("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.put("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert captured[0].path == "/wish"
    assert captured[0].method == "PUT"
    assert captured[0].response_model is WishOut


def test_legacy_callable_runner_still_works() -> None:
    app = FastAPI()
    router = PromptRouter(
        agent_runner=lambda **_: {"granted": True, "message": "legacy"}
    )

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert resp.json() == {"granted": True, "message": "legacy"}


def test_prompt_composer_override() -> None:
    composer_calls: list[tuple] = []

    def my_composer(endpoint: PromptEndpoint, dynamic_prompt: str | None) -> str:
        composer_calls.append((endpoint.path, endpoint.method, dynamic_prompt))
        return f"CUSTOM::{endpoint.path}::{dynamic_prompt or ''}"

    captured: list[RunnerContext] = []

    class CaptureRunner:
        def run(self, ctx: RunnerContext) -> dict:
            captured.append(ctx)
            return {"granted": True, "message": "ok"}

    app = FastAPI()
    router = PromptRouter(
        agent_runner=CaptureRunner(),
        prompt_composer=my_composer,
    )

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""
        return "tail"

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert captured[0].prompt == "CUSTOM::/wish::tail"
    assert composer_calls == [("/wish", "POST", "tail")]


def test_bad_runner_raises_at_request_time() -> None:
    class BadRunner:
        def run(self, ctx, extra_required_arg):  # signature mismatch
            return {}

    app = FastAPI()
    router = PromptRouter(agent_runner=BadRunner())

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 500


def test_coerce_runner_rejects_non_callable() -> None:
    with pytest.raises(TypeError):
        Runtime(agent_runner=123)
