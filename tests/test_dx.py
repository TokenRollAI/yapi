"""§8.4 DX 与可观测性测试。"""

import logging
import os
import warnings

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import (
    AgentRunner,
    PromptRouter,
    RunnerContext,
    RuntimeExecutionError,
    YapiDeclarationError,
    YapiError,
    YapiUsageWarning,
)
from yapi.agent import PydanticAIRunner, build_default_runner


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """grant wishes"""

    granted: bool
    message: str


def test_runtime_logs_debug_at_execute_entry(caplog: pytest.LogCaptureFixture) -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)

    with caplog.at_level(logging.DEBUG, logger="yapi.runtime"):
        resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    messages = [r.getMessage() for r in caplog.records if r.name == "yapi.runtime"]
    assert any("path=/wish" in m and "method=POST" in m for m in messages)


def test_runtime_error_message_includes_cause_repr() -> None:
    class BoomRunner:
        def run(self, ctx: RunnerContext) -> dict:
            raise ValueError("kaboom")

    app = FastAPI()
    router = PromptRouter(agent_runner=BoomRunner())

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    with pytest.raises(RuntimeExecutionError) as exc_info:
        client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    msg = str(exc_info.value)
    assert "ValueError" in msg
    assert "kaboom" in msg


def test_default_runner_construction_warns_when_yapi_model_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YAPI_MODEL", raising=False)
    with pytest.warns(YapiUsageWarning, match="YAPI_MODEL not set"):
        build_default_runner()


def test_default_runner_no_warning_when_yapi_model_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YAPI_MODEL", "openai:gpt-4o")
    with warnings.catch_warnings():
        warnings.simplefilter("error", YapiUsageWarning)
        runner = build_default_runner()
    assert isinstance(runner, PydanticAIRunner)


def test_default_runner_no_warning_when_model_arg_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YAPI_MODEL", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", YapiUsageWarning)
        runner = build_default_runner(model="openai:gpt-4o")
    assert isinstance(runner, PydanticAIRunner)


def test_prompt_router_with_custom_runner_skips_default_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YAPI_MODEL", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", YapiUsageWarning)
        PromptRouter(agent_runner=lambda **_: {})


def test_yapi_init_reexports_error_classes() -> None:
    # Smoke: every documented public symbol must be importable from yapi.
    from yapi import (  # noqa: F401
        AgentRunner,
        PromptRouter,
        RunnerContext,
        RuntimeExecutionError,
        YapiDeclarationError,
        YapiError,
        YapiUsageWarning,
    )

    assert issubclass(YapiDeclarationError, YapiError)
    assert issubclass(RuntimeExecutionError, YapiError)
    assert issubclass(YapiUsageWarning, UserWarning)
    assert isinstance(RunnerContext, type)
    assert isinstance(AgentRunner, type)  # Protocols are types


def test_state_store_error_removed() -> None:
    with pytest.raises(ImportError):
        from yapi.errors import StateStoreError  # noqa: F401


def test_default_runner_unset_yapi_model_raises_at_request_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YAPI_MODEL", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", YapiUsageWarning)
        router = PromptRouter()

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    with pytest.raises(RuntimeExecutionError) as exc_info:
        client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert "YAPI_MODEL" in str(exc_info.value)
