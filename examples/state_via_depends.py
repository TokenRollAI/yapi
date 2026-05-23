"""演示用 FastAPI 原生 Depends 拿 dict store，通过 PromptContext 把 state 塞进 prompt。

yapi 不集成 state 存储：Redis / Mongo / SQL 等客户端用 Depends 拿，
用 ctx.add_section / add_kv / add 决定哪些事实进 prompt。

运行：
    YAPI_MODEL=test uv run uvicorn examples.state_via_depends:app --reload
"""

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from yapi import PromptContext, PromptRouter

# 模拟内存 KV store（实际场景替换为 Redis / Mongo / SQL 客户端）
_STORE: dict[str, dict] = {
    "u-1": {"name": "Alice", "vip": True, "last_orders": ["o-100", "o-101"]},
    "u-2": {"name": "Bob", "vip": False, "last_orders": []},
}


class WishIn(BaseModel):
    user_id: str
    wish: str
    item_id: str


class WishOut(BaseModel):
    """你是一个愿望受理实体。请根据用户档案和商品信息决定是否实现愿望。"""

    granted: bool
    message: str


def get_store() -> dict[str, dict]:
    return _STORE


router = PromptRouter()


@router.prompt.post("/wish")
def make_a_wish(
    req: WishIn,
    ctx: PromptContext,
    store: dict = Depends(get_store),
) -> WishOut:
    """根据用户档案决定是否实现愿望。"""
    profile = store.get(req.user_id, {})
    ctx.add_section("User Profile", profile)
    ctx.add_kv("item_id", req.item_id)
    if profile.get("last_orders"):
        ctx.add(profile["last_orders"])


app = FastAPI(title="yapi state via depends")
app.include_router(router)
