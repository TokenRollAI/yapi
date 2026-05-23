"""§8.1 PromptRouter ↔ APIRouter 兼容测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import PromptRouter
from yapi.router import _PromptDecorators


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """grant wishes"""

    granted: bool
    message: str


def _ok_runner(**_):
    return {"granted": True, "message": "ok"}


def test_prompt_router_native_get_works_like_apirouter() -> None:
    app = FastAPI()
    runner_calls: list = []

    def runner(**kwargs):
        runner_calls.append(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.get("/h")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/h")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert runner_calls == []


def test_prompt_router_mixed_routes_share_prefix_and_tags() -> None:
    app = FastAPI()
    router = PromptRouter(prefix="/v1", tags=["wishes"], agent_runner=_ok_runner)

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)

    health_resp = client.get("/v1/health")
    assert health_resp.status_code == 200

    wish_resp = client.post("/v1/wish", json={"user_id": "u-1", "wish": "moon"})
    assert wish_resp.status_code == 200

    schema = app.openapi()
    assert "wishes" in schema["paths"]["/v1/health"]["get"]["tags"]
    assert "wishes" in schema["paths"]["/v1/wish"]["post"]["tags"]


def test_prompt_router_native_post_does_not_invoke_agent_runner() -> None:
    app = FastAPI()
    runner_calls: list = []

    def runner(**kwargs):
        runner_calls.append(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.post("/echo")
    def echo(payload: dict) -> dict:
        return payload

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/echo", json={"hello": "world"})
    assert resp.status_code == 200
    assert resp.json() == {"hello": "world"}
    assert runner_calls == []


def test_prompt_router_namespace_returns_helper_object() -> None:
    router = PromptRouter(agent_runner=_ok_runner)
    assert isinstance(router.prompt, _PromptDecorators)
    for method in ("get", "post", "put", "patch", "delete"):
        assert callable(getattr(router.prompt, method))


def test_prompt_router_apirouter_kwargs_forwarded() -> None:
    router = PromptRouter(
        prefix="/api",
        tags=["t"],
        agent_runner=_ok_runner,
    )
    assert router.prefix == "/api"
    assert "t" in router.tags
