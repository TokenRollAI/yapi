"""Depends 注入 + dynamic prompt 的最小示例。

运行：
    YAPI_MODEL=test uv run uvicorn examples.with_depends:app --reload

可观察：
    POST /wish 用 `Depends(fetch_profile)` 注入用户档案，
    并在路由函数内返回 dynamic prompt 段以追加到 system prompt。
"""

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from yapi import PromptRouter


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
    profile: dict = Depends(fetch_profile),
) -> WishOut:
    """根据用户档案决定是否实现愿望。"""
    if profile["vip"]:
        return f"user {req.user_id} is a VIP, grant the wish gracefully."
    return f"user {req.user_id} is regular, decide thoughtfully."


app = FastAPI(title="yapi with depends")
app.include_router(router)
