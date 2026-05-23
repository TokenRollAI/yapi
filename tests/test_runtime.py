from pydantic import BaseModel

from yapi.endpoint import PromptEndpoint
from yapi.models import RuntimeContext
from yapi.runtime import Runtime


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    """你是一个愿望受理实体。"""

    granted: bool
    message: str


def test_prompt_endpoint_stores_definition() -> None:
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=WishRequest,
        response_model=WishResponse,
        function_doc="grant wishes",
    )

    assert endpoint.path == "/wish"
    assert endpoint.method == "POST"
    assert endpoint.request_model is WishRequest
    assert endpoint.response_model is WishResponse
    assert endpoint.function_doc == "grant wishes"


def test_runtime_builds_context_sections() -> None:
    runtime = Runtime(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    context = runtime.build_context(
        request_data={"user_id": "u-1", "wish": "moon"},
        injected={"profile": {"vip": True}},
    )

    assert context.request == {"user_id": "u-1", "wish": "moon"}
    assert context.injected == {"profile": {"vip": True}}


def test_runtime_executes_agent_and_returns_response_model() -> None:
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=WishRequest,
        response_model=WishResponse,
        function_doc="grant wishes",
    )

    runtime = Runtime(
        agent_runner=lambda **_: {"granted": True, "message": "granted"},
    )

    response = runtime.execute(
        endpoint=endpoint,
        request_model=WishRequest(user_id="u-1", wish="moon"),
        injected={"profile": {"vip": True}},
        dynamic_prompt=None,
    )

    assert response.model_dump() == {"granted": True, "message": "granted"}


def test_runtime_sends_composed_prompt_to_agent_runner() -> None:
    captured = {}
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=WishRequest,
        response_model=WishResponse,
        function_doc="grant wishes based on context",
    )

    def fake_agent_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    runtime = Runtime(agent_runner=fake_agent_runner)
    runtime.execute(
        endpoint=endpoint,
        request_model=WishRequest(user_id="u-1", wish="moon"),
        injected={"profile": {"vip": True}},
        dynamic_prompt="user is shouting",
    )

    assert "你是一个愿望受理实体。" in captured["prompt"]
    assert "grant wishes based on context" in captured["prompt"]
    assert "user is shouting" in captured["prompt"]
    assert captured["request"] == {"user_id": "u-1", "wish": "moon"}
    assert captured["injected"] == {"profile": {"vip": True}}


from yapi.prompt_context import PromptContext
from yapi.runtime import compose_prompt


def test_compose_skips_context_when_empty():
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=None,
        response_model=WishResponse,
        function_doc="grant wishes",
    )
    prompt = compose_prompt(endpoint, None, None)
    assert "<context>" not in prompt


def test_compose_wraps_single_ctx_segment():
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=None,
        response_model=WishResponse,
        function_doc="grant wishes",
    )
    ctx = PromptContext()
    ctx.add("hint segment")
    prompt = compose_prompt(endpoint, ctx, None)
    assert "<context>\nhint segment\n</context>" in prompt


def test_compose_wraps_dynamic_only():
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=None,
        response_model=WishResponse,
        function_doc="grant wishes",
    )
    prompt = compose_prompt(endpoint, None, "dynamic text")
    assert "<context>\ndynamic text\n</context>" in prompt


def test_compose_concatenates_ctx_then_dynamic():
    endpoint = PromptEndpoint(
        path="/wish",
        method="POST",
        request_model=None,
        response_model=WishResponse,
        function_doc="grant wishes",
    )
    ctx = PromptContext()
    ctx.add("s1")
    ctx.add("s2")
    prompt = compose_prompt(endpoint, ctx, "dynamic")
    assert "<context>\ns1\n\ns2\n\ndynamic\n</context>" in prompt
