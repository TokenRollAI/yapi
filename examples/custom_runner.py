"""自定义 AgentRunner Protocol 实现，演示离线 / mock / 多模型路由。

运行：
    uv run uvicorn examples.custom_runner:app --reload

可观察：
    无需配置 YAPI_MODEL；自定义 runner 直接返回模拟数据，
    并可基于 ctx.path / ctx.method 做分支。
"""

from fastapi import FastAPI
from pydantic import BaseModel

from yapi import AgentRunner, PromptRouter, RunnerContext


class WishIn(BaseModel):
    user_id: str
    wish: str


class WishOut(BaseModel):
    """你是一个愿望受理实体。请返回结构化结果。"""

    granted: bool
    message: str


class MockRunner:
    def run(self, ctx: RunnerContext) -> dict:
        wish = ctx.request.get("wish", "")
        return {
            "granted": "moon" not in wish.lower(),
            "message": f"path={ctx.path} method={ctx.method} prompt_chars={len(ctx.prompt)}",
        }


# Protocol 仅是结构提示——任何有 `.run(ctx)` 方法的对象都满足。
_: AgentRunner = MockRunner()  # type-check sanity


router = PromptRouter(agent_runner=MockRunner())


@router.prompt.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据愿望决定是否实现。"""


app = FastAPI(title="yapi custom runner")
app.include_router(router)
