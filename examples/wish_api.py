from fastapi import FastAPI
from pydantic import BaseModel

from yapi import PromptRouter


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """你是一个愿望受理实体。请返回结构化结果。"""

    granted: bool
    message: str


app = FastAPI(title="yapi showcase")
router = PromptRouter()


@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""


app.include_router(router)
