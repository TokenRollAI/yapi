from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import PromptRouter


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    """你是一个愿望受理实体。"""

    granted: bool
    message: str


def test_dependency_injection_flows_into_runtime() -> None:
    app = FastAPI()

    def fake_agent_runner(**kwargs):
        injected = kwargs["injected"]
        return {
            "granted": injected["profile"]["vip"],
            "message": "vip granted",
        }

    router = PromptRouter(agent_runner=fake_agent_runner)

    def fetch_profile(req: WishRequest) -> dict:
        return {"vip": req.user_id == "u-1"}

    @router.prompt.post("/wish")
    def make_a_wish(
        req: WishRequest,
        profile: dict = Depends(fetch_profile),
    ) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)

    response = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert response.status_code == 200
    assert response.json() == {"granted": True, "message": "vip granted"}


def test_dynamic_prompt_returned_by_handler_reaches_agent_runner() -> None:
    captured = {}
    app = FastAPI()

    def fake_agent_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=fake_agent_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""
        return f"focus on user {req.user_id}'s mood: {req.wish}"

    app.include_router(router)
    client = TestClient(app)

    response = client.post("/wish", json={"user_id": "u-1", "wish": "stars"})

    assert response.status_code == 200
    assert "focus on user u-1's mood: stars" in captured["prompt"]


def test_handler_returning_non_string_raises_runtime_error() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""
        return 42

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert response.status_code == 500


# ---- v2.2 PromptContext e2e ----


from yapi import PromptContext


def test_e2e_ctx_segments_reach_runner() -> None:
    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    app = FastAPI()
    router = PromptRouter(agent_runner=fake_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest, ctx: PromptContext) -> WishResponse:
        """grant wishes"""
        ctx.add_section("User", req.user_id)
        ctx.add_kv("wish", req.wish)
        ctx.add("extra hint")

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert resp.status_code == 200
    prompt = captured["prompt"]
    assert "<context>" in prompt
    assert "# User" in prompt
    assert "u-1" in prompt
    assert "wish: moon" in prompt
    assert "extra hint" in prompt


def test_e2e_v21_route_with_return_str_wraps_in_context() -> None:
    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    app = FastAPI()
    router = PromptRouter(agent_runner=fake_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""
        return "legacy hint string"

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert resp.status_code == 200
    prompt = captured["prompt"]
    assert "<context>\nlegacy hint string\n</context>" in prompt


def test_e2e_route_with_no_ctx_and_no_return_skips_context_tag() -> None:
    captured = {}

    def fake_runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    app = FastAPI()
    router = PromptRouter(agent_runner=fake_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert resp.status_code == 200
    assert "<context>" not in captured["prompt"]
