"""End-to-end tests against a real LLM provider.

These tests verify that the full pipeline — function signature → PromptContext
injection → `<context>` XML wrapping → PydanticAI Agent → structured response
validation — works against an actual model (configured via `YAPI_MODEL` + the
matching provider env vars).

Assertions are intentionally lenient where output is non-deterministic (free-form
strings) and strict where the prompt strongly constrains behavior (a clearly
specified decision rule should produce a clearly determined `bool`).

If a model flakes on a "strong rule" test, the fix is usually to make the rule
in the prompt more explicit — not to weaken the assertion. The whole point of
these tests is to catch real-world model misbehavior.
"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yapi import PromptContext, PromptRouter

pytestmark = pytest.mark.live


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """你是一个愿望受理实体。请基于提供的事实做出 grant 决策，并给出简短消息。"""

    granted: bool
    message: str


# 1. Minimal happy path: real model returns a payload that validates against the schema.


def test_live_minimal_route_returns_valid_response_model() -> None:
    app = FastAPI()
    router = PromptRouter()

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> WishOut:
        """根据用户的愿望决定是否实现。"""

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/wish", json={"user_id": "u-1", "wish": "have a sip of water"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["granted"], bool)
    assert isinstance(data["message"], str)
    assert data["message"], "model returned an empty message"


# 2. PromptContext.add_section drives a deterministic decision.


class StrictVipOut(BaseModel):
    """决策规则（必须严格遵守）：当且仅当 `<context>` 内 `# User Profile` 段中 `vip` 字段值为 true 时返回 granted=true；vip 为 false 时返回 granted=false。不允许其它解释，不允许同情或宽容。"""

    granted: bool
    message: str


def test_live_prompt_context_section_drives_decision() -> None:
    app = FastAPI()
    router = PromptRouter()

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn, ctx: PromptContext) -> StrictVipOut:
        """按照响应模型 docstring 的决策规则处理愿望。"""
        ctx.add_section("User Profile", {"vip": req.user_id.startswith("vip-")})

    app.include_router(router)
    client = TestClient(app)

    vip_resp = client.post("/wish", json={"user_id": "vip-7", "wish": "a small coffee"})
    assert vip_resp.status_code == 200, vip_resp.text
    assert vip_resp.json()["granted"] is True, (
        f"VIP user expected granted=true, got {vip_resp.json()}"
    )

    reg_resp = client.post("/wish", json={"user_id": "u-7", "wish": "a small coffee"})
    assert reg_resp.status_code == 200, reg_resp.text
    assert reg_resp.json()["granted"] is False, (
        f"non-VIP expected granted=false, got {reg_resp.json()}"
    )


# 3. Depends + PromptContext combination — mirrors examples/with_depends.py.


def _fetch_profile(req: WishIn) -> dict:
    return {"vip": req.user_id.startswith("vip-"), "credits": 100 if req.user_id.startswith("vip-") else 0}


def test_live_depends_data_reaches_model_via_prompt_context() -> None:
    app = FastAPI()
    router = PromptRouter()

    @router.prompt.post("/wish")
    def make_a_wish(
        req: WishIn,
        ctx: PromptContext,
        profile: dict = Depends(_fetch_profile),
    ) -> StrictVipOut:
        """按照响应模型 docstring 的决策规则处理愿望。"""
        ctx.add_section("User Profile", profile)
        ctx.add_kv("user_id", req.user_id)

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/wish", json={"user_id": "vip-42", "wish": "any wish"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] is True


# 4. v2.1 backward compat: `return "hint"` still wraps into <context> and reaches the model.


class HintOut(BaseModel):
    """请提取并回显 `<context>` 段中明确给出的代号（codename）。返回的 message 必须含该代号字面量。"""

    granted: bool
    message: str


def test_live_v21_return_str_still_reaches_model() -> None:
    app = FastAPI()
    router = PromptRouter()

    codename = "ZEBRA-9173"

    @router.prompt.post("/wish")
    def make_a_wish(req: WishIn) -> HintOut:
        """回显代号。"""
        return f"Codename is {codename}. Echo it verbatim in the message field."

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/wish", json={"user_id": "u-1", "wish": "anything"})
    assert resp.status_code == 200, resp.text
    assert codename in resp.json()["message"], (
        f"expected codename {codename!r} echoed in message, got {resp.json()}"
    )


# 5. async def route works with real model.


def test_live_async_def_route_works() -> None:
    app = FastAPI()
    router = PromptRouter()

    codename = "FALCON-2024"

    @router.prompt.post("/wish")
    async def make_a_wish(req: WishIn, ctx: PromptContext) -> HintOut:
        """回显代号。"""
        ctx.add_kv("codename", codename)
        ctx.add("Echo the codename verbatim in the message field.")

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/wish", json={"user_id": "u-1", "wish": "anything"})
    assert resp.status_code == 200, resp.text
    assert codename in resp.json()["message"]


# 6. Annotated injected field (Query) reaches the model alongside PromptContext.


def test_live_annotated_query_param_reaches_model() -> None:
    app = FastAPI()
    router = PromptRouter()

    @router.prompt.get("/echo")
    def echo(
        token: Annotated[str, Query()],
        ctx: PromptContext,
    ) -> HintOut:
        """回显 token。"""
        ctx.add_kv("token", token)
        ctx.add("Echo the token verbatim in the message field.")

    app.include_router(router)
    client = TestClient(app)

    token = "HUMMINGBIRD-77"
    resp = client.get("/echo", params={"token": token})
    assert resp.status_code == 200, resp.text
    assert token in resp.json()["message"]


# 7. Multiple PromptContext methods combine correctly — model sees all segments.


class MultiFactOut(BaseModel):
    """请在 message 中**同时**包含 `<context>` 内出现的：用户姓名、最爱颜色、订单号。三项缺一不可。"""

    granted: bool
    message: str


def test_live_multi_segment_prompt_context_all_reach_model() -> None:
    app = FastAPI()
    router = PromptRouter()

    @router.prompt.post("/profile")
    def show(req: WishIn, ctx: PromptContext) -> MultiFactOut:
        """汇总用户信息。"""
        ctx.add_section("User", {"name": "Alice Wonderland", "color": "magenta"})
        ctx.add_kv("order_id", "ORD-90210")
        ctx.add("All three facts above must appear verbatim in the message.")

    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/profile", json={"user_id": "u-1", "wish": "show me"})
    assert resp.status_code == 200, resp.text
    msg = resp.json()["message"]
    assert "Alice Wonderland" in msg, f"name missing in {msg!r}"
    assert "magenta" in msg, f"color missing in {msg!r}"
    assert "ORD-90210" in msg, f"order_id missing in {msg!r}"
