"""Depends 注入 + PromptContext 的最小示例（v2.2）。

运行：
    YAPI_MODEL=test uv run uvicorn examples.with_depends:app --reload

可观察：
    POST /wish 用 `Depends(fetch_profile)` 注入用户档案，
    通过 PromptContext 把结构化片段注入 system prompt（外裹 <context>...</context>）。
"""

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from yapi import PromptContext, PromptRouter


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """你是一个愿望受理实体。请返回结构化结果。"""

    granted: bool
    message: str


def fetch_profile(req: WishIn) -> dict:
    return {"vip": req.user_id.startswith("vip-")}


router = PromptRouter()


@router.prompt.post("/wish")
def make_a_wish(
    req: WishIn,
    ctx: PromptContext,
    profile: dict = Depends(fetch_profile),
) -> WishOut:
    """根据用户档案决定是否实现愿望。"""
    ctx.add_section("User Profile", profile)
    ctx.add_kv("user_id", req.user_id)


app = FastAPI(title="yapi with depends")
app.include_router(router)
