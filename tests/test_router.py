import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from yapi import PromptRouter
from yapi.errors import YapiDeclarationError


class WishRequest(BaseModel):
    user_id: str
    wish: str


class WishResponse(BaseModel):
    """你是一个愿望受理实体。"""

    granted: bool
    message: str


def test_router_post_registers_route_with_inferred_models() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)

    paths = {(route.path, tuple(route.methods)) for route in app.routes}
    assert ("/wish", ("POST",)) in paths


def test_router_post_emits_openapi_with_declared_models() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    @router.post("/wish")
    def make_a_wish(req: WishRequest) -> WishResponse:
        """grant wishes"""

    app.include_router(router)
    schema = app.openapi()

    operation = schema["paths"]["/wish"]["post"]
    assert operation["requestBody"] is not None
    assert operation["responses"]["200"] is not None


def test_router_post_requires_response_annotation() -> None:
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    with pytest.raises(YapiDeclarationError):

        @router.post("/wish")
        def make_a_wish(req: WishRequest):
            """grant wishes"""


def test_router_post_rejects_non_basemodel_response() -> None:
    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    with pytest.raises(YapiDeclarationError):

        @router.post("/wish")
        def make_a_wish(req: WishRequest) -> dict:
            """grant wishes"""


def test_router_post_rejects_multiple_basemodel_params() -> None:
    class Extra(BaseModel):
        flag: bool

    router = PromptRouter(agent_runner=lambda **_: {"granted": True, "message": "ok"})

    with pytest.raises(YapiDeclarationError):

        @router.post("/wish")
        def make_a_wish(req: WishRequest, extra: Extra) -> WishResponse:
            """grant wishes"""


def test_router_supports_get_with_no_request_body() -> None:
    app = FastAPI()
    router = PromptRouter(agent_runner=lambda **_: {"message": "ok"})

    class StatusOut(BaseModel):
        """describe the system."""

        message: str

    @router.get("/status")
    def status() -> StatusOut:
        """return current status."""

    app.include_router(router)

    paths = {(route.path, tuple(route.methods)) for route in app.routes}
    assert ("/status", ("GET",)) in paths


def test_example_application_imports() -> None:
    from examples.wish_api import app

    assert app is not None
