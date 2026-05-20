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

    @router.post("/wish")
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

    @router.post("/wish")
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

    @router.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""
        return 42

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})

    assert response.status_code == 500
