"""同一个 PromptRouter 内混挂普通 FastAPI 路由与 prompt 路由。

运行：
    YAPI_MODEL=test uv run uvicorn examples.mixed_router:app --reload

可观察：
    GET  /v1/health → {"status": "ok"}（原生 FastAPI 路由）
    POST /v1/wish   → 走 prompt 管线，使用 TestModel 占位响应
"""

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


router = PromptRouter(prefix="/v1", tags=["wishes"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""


app = FastAPI(title="yapi mixed router")
app.include_router(router)
