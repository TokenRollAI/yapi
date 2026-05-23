from typing import Annotated

import pytest
from fastapi import Body, Cookie, Depends, FastAPI, Header, Path, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import PromptRouter, YapiUsageWarning
from yapi.errors import YapiDeclarationError


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    """你是一个愿望受理实体。"""

    granted: bool
    message: str


def _ok_runner(**_):
    return {"granted": True, "message": "ok"}


def test_router_post_registers_route_with_inferred_models() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=_ok_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)

    paths = {(route.path, tuple(route.methods)) for route in app.routes}
    assert ("/wish", ("POST",)) in paths


def test_router_post_emits_openapi_with_declared_models() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=_ok_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    schema = app.openapi()

    operation = schema["paths"]["/wish"]["post"]
    assert operation["requestBody"] is not None
    assert operation["responses"]["200"] is not None


def test_router_post_requires_response_annotation() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):

        @router.prompt.post("/wish")
        def make_a_wish(req: WishRequest):
            """grant wishes"""


def test_router_post_rejects_non_basemodel_response() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):

        @router.prompt.post("/wish")
        def make_a_wish(req: WishRequest) -> dict:
            """grant wishes"""


def test_router_post_rejects_multiple_basemodel_params() -> None:
    class Extra(BaseModel):
        flag: bool

    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):

        @router.prompt.post("/wish")
        def make_a_wish(req: WishRequest, extra: Extra) -> WishResponse:
            """grant wishes"""


def test_router_supports_get_with_no_request_body() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=_ok_runner)

    class StatusOut(BaseModel):
        """describe the system."""

        message: str

    @router.prompt.get("/status")
    def status() -> StatusOut:
        """return current status."""

    app.include_router(router)

    paths = {(route.path, tuple(route.methods)) for route in app.routes}
    assert ("/status", ("GET",)) in paths


def test_example_application_imports(monkeypatch) -> None:
    monkeypatch.setenv("YAPI_MODEL", "test")
    # Force re-import so the YAPI_MODEL env applies to the module-level PromptRouter().
    import importlib
    import examples.wish_api as wish_api

    wish_api = importlib.reload(wish_api)
    assert wish_api.app is not None


# ---- §8.2 FastAPI 兼容性 ----


def test_prompt_passthrough_tags_summary_status_code() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=_ok_runner)

    @router.prompt.post(
        "/wish",
        tags=["wishes"],
        summary="grant a wish",
        status_code=201,
    )
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    schema = app.openapi()
    operation = schema["paths"]["/wish"]["post"]
    assert operation["tags"] == ["wishes"]
    assert operation["summary"] == "grant a wish"
    assert "201" in operation["responses"]

    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 201


def test_prompt_rejects_response_model_kwarg() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):
        router.prompt.post("/wish", response_model=WishResponse)


def test_prompt_rejects_response_class_kwarg() -> None:
    from fastapi.responses import JSONResponse

    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):
        router.prompt.post("/wish", response_class=JSONResponse)


def test_prompt_rejects_dependencies_kwarg() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError):
        router.prompt.post("/wish", dependencies=[Depends(lambda: None)])


def test_prompt_warns_on_unknown_kwarg() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.warns(YapiUsageWarning, match="not recognized"):
        router.prompt.post("/wish", does_not_exist=True)


def test_prompt_supports_async_def_handler() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.prompt.post("/wish")
    async def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""
        return f"async-wish-{req.user_id}"

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert "async-wish-u-1" in captured["prompt"]


def test_prompt_rejects_sync_generator_function() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="generator"):

        @router.prompt.post("/wish")
        def make_a_wish(req: WishRequest) -> WishResponse:
            """grant wishes"""
            yield "nope"


def test_prompt_rejects_async_generator_function() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="generator"):

        @router.prompt.post("/wish")
        async def make_a_wish(req: WishRequest) -> WishResponse:
            """grant wishes"""
            yield "nope"


def test_prompt_supports_annotated_body_param() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=_ok_runner)

    @router.prompt.post("/wish")
    def make_a_wish(req: Annotated[WishRequest, Body()]) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200


def test_prompt_supports_annotated_query_param() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.prompt.get("/wish")
    def make_a_wish(q: Annotated[str, Query()] = "default") -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/wish", params={"q": "moon"})
    assert resp.status_code == 200
    assert captured["injected"] == {"q": "moon"}


def test_prompt_supports_annotated_header_param() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.prompt.post("/wish")
    def make_a_wish(
        req: WishRequest,
        x_token: Annotated[str, Header()] = "anonymous",
    ) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post(
        "/wish",
        json={"user_id": "u-1", "wish": "moon"},
        headers={"x-token": "abc"},
    )
    assert resp.status_code == 200
    assert captured["injected"]["x_token"] == "abc"


def test_prompt_supports_annotated_depends() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    def get_token() -> str:
        return "deps-token"

    @router.prompt.post("/wish")
    def make_a_wish(
        req: WishRequest,
        token: Annotated[str, Depends(get_token)],
    ) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish", json={"user_id": "u-1", "wish": "moon"})
    assert resp.status_code == 200
    assert captured["injected"]["token"] == "deps-token"


def test_prompt_supports_annotated_cookie_param() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.prompt.get("/wish")
    def make_a_wish(c: Annotated[str, Cookie()] = "anon") -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    client.cookies.set("c", "abc")
    resp = client.get("/wish")
    assert resp.status_code == 200
    assert captured["injected"]["c"] == "abc"


def test_prompt_supports_path_param() -> None:
    app = FastAPI()
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"granted": True, "message": "ok"}

    router = PromptRouter(agent_runner=runner)

    @router.prompt.post("/wish/{user_id}")
    def make_a_wish(
        user_id: Annotated[str, Path()],
        req: WishRequest,
    ) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    client = TestClient(app)
    resp = client.post("/wish/u-7", json={"user_id": "u-7", "wish": "moon"})
    assert resp.status_code == 200
    assert captured["injected"]["user_id"] == "u-7"


def test_prompt_rejects_bare_string_param() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="parameter 'q'"):

        @router.prompt.get("/wish")
        def bad(q: str) -> WishResponse:
            """grant wishes"""


def test_prompt_rejects_scalar_body_default() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="Body"):

        @router.prompt.post("/wish")
        def bad(q: str = Body(...)) -> WishResponse:
            """grant wishes"""


def test_prompt_rejects_scalar_annotated_body() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="Body"):

        @router.prompt.post("/wish")
        def bad(q: Annotated[str, Body()]) -> WishResponse:
            """grant wishes"""


def test_prompt_rejects_two_body_params() -> None:
    class Extra(BaseModel):
        flag: bool

    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match="at most one"):

        @router.prompt.post("/wish")
        def bad(
            req: WishRequest,
            extra: Annotated[Extra, Body()],
        ) -> WishResponse:
            """grant wishes"""


def test_prompt_rejects_var_positional() -> None:
    router = PromptRouter(agent_runner=_ok_runner)

    with pytest.raises(YapiDeclarationError, match=r"\*args"):

        @router.prompt.post("/wish")
        def bad(*args) -> WishResponse:
            """grant wishes"""


def test_prompt_handler_signature_preserves_annotated() -> None:
    import inspect

    router = PromptRouter(agent_runner=_ok_runner)

    @router.prompt.post("/wish")
    def make_a_wish(
        req: Annotated[WishRequest, Body()],
        q: Annotated[str, Query()] = "default",
    ) -> WishResponse:
        """grant wishes"""

    route = next(r for r in router.routes if getattr(r, "path", None) == "/wish")
    sig = inspect.signature(route.endpoint)
    req_param = sig.parameters["req"]
    q_param = sig.parameters["q"]
    assert hasattr(req_param.annotation, "__metadata__")
    assert hasattr(q_param.annotation, "__metadata__")
