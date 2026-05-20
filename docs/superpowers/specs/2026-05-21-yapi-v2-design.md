# yapi v2 设计文档（API 收紧版）

日期：2026-05-21
状态：draft
取代：`docs/superpowers/specs/2026-05-20-yapi-design.md` 中第 4、6、9、10 节的 API 形态部分；其余整体定位仍延续 v1。

## 1. 本次重做的动机

v1 的 API 已经能跑通声明式 HTTP + 结构化输出 + state 持久化，但实际写起来不够优雅：

- 装饰器参数和 FastAPI 原生类型推断重复
- `llm_post` 暗示"POST 加个 LLM"，与产品定位（prompt-first 框架）不符
- `request_model=` / `response_model=` 在函数签名里其实已经表达过
- `state_dependencies=[Depends(...)]` 又包了一层 list，不像 FastAPI
- handler 函数体永远空，但其实可以承载有用的动态信息
- `state` 当前形态尚未让作者满意，需要从核心 API 中先剥离

v2 的目标是收紧 API，让它在外观上看上去更像 FastAPI 的自然扩展。

## 2. v2 核心设计原则

- **契约从函数签名推断**：`request_model` / `response_model` 不再出现在装饰器里。
- **装饰器尽量空**：路径以外的参数能不写就不写。
- **prompt 多源合成**：从响应模型 docstring、函数 docstring、函数返回值组合而成。
- **HTTP method 名直接借用 FastAPI**：`.post` / `.get` / `.put` 等，不再用 `llm_*`。
- **`PromptRouter` 上的方法覆盖原生 `APIRouter` 方法**：同一个 router 内的所有路由都是 prompt 路由；要写普通接口请另起一个 `APIRouter`。
- **state 暂时退出核心路径**：v2 的核心 API 不包含 `state_storage` / `state_dependencies` / `state_key`，等下一轮设计再回来。
- **依赖注入复用 FastAPI**：所有 deps 通过函数签名上的 `Depends(...)` 表达。

## 3. 标准声明姿势

### 3.1 最小例子

```python
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


app = FastAPI()
router = PromptRouter()


@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""


app.include_router(router)
```

### 3.2 使用 FastAPI 依赖注入

依赖注入完全沿用 FastAPI 原生姿势，不再有 `state_dependencies=[Depends(...)]` 这层包装。

```python
def fetch_profile(user_id: str) -> dict:
    return {"vip": user_id.startswith("vip-")}


@router.post("/wish")
def make_a_wish(
    req: WishIn,
    profile: dict = Depends(fetch_profile),
) -> WishOut:
    """根据用户的愿望和 VIP 状态决定是否实现。"""
```

注入到的依赖将出现在运行时上下文的 `injected` 区域，传给底层 agent。

### 3.3 动态 prompt

函数体可以返回一段字符串，框架会把它拼到 system prompt 末尾，作为本次请求的额外提示。

```python
@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""
    if req.wish.startswith("不"):
        return "用户在使用否定句，请先反问他真正想要什么。"
```

如果函数体不返回任何东西（或返回 `None`），框架忽略它。

### 3.4 仅声明、不写函数体

如果开发者只想完全声明式地表达一个接口，也可以保持函数体为空：

```python
@router.post("/wish")
def make_a_wish(req: WishIn) -> WishOut:
    """根据用户的愿望决定是否实现。"""
```

这是默认的、推荐的极简姿势。

## 4. 函数签名推断契约

`PromptRouter.post(path)` 解析被装饰函数时遵循以下规则：

- **request_model**：函数签名中类型为 Pydantic `BaseModel` 子类的位置参数 / 关键字参数（不包括 `Depends(...)`），按顺序为请求体；若没有，则视为无请求体接口。
- **response_model**：函数的返回注解必须是一个 Pydantic `BaseModel` 子类。缺失视为声明错误，直接在注册时抛出。
- **dependencies**：函数签名中带有 `Depends(...)` 默认值的参数，按 FastAPI 习惯处理。
- 框架在底层构造一个 FastAPI handler，把请求模型、依赖模型和返回模型都按 FastAPI 标准方式提交给 FastAPI，从而保证 OpenAPI 文档原样可用。

## 5. Prompt 合成顺序

每一次请求执行时，最终交给底层 agent 的 system prompt 大致由以下顺序拼接：

1. 框架基线 prompt（声明这是一个由 HTTP 请求驱动的结构化输出执行器）
2. 响应模型 docstring（描述"我是谁 / 我应当产出什么"）
3. 函数 docstring（描述"这一次具体任务"）
4. 函数返回的动态 prompt（描述"本次请求的特殊上下文"）

User prompt 仍由请求数据与注入依赖组成，与 v1 类似。

如果某一段为空（响应模型没有 docstring、函数没有 docstring、函数不返回字符串），框架直接跳过该段。

## 6. 与 FastAPI 的关系

- `PromptRouter` 仍继承自 `fastapi.APIRouter`，可以 `app.include_router(...)`。
- `PromptRouter.post` / `.get` / `.put` 等方法**显式覆盖**原生方法，所有声明都视为 prompt 路由。
- 想在同一应用里同时拥有普通 FastAPI 接口和 yapi 路由，请用两个 router：一个原生 `APIRouter`，一个 `PromptRouter`。
- OpenAPI 中请求模型、响应模型、依赖体验保持原生 FastAPI 行为，让 docs UI 和客户端工具继续可用。

## 7. 错误处理

继续沿用 v1 的边界，并补充几条 v2 特有规则：

- 函数缺少返回注解或返回注解不是 Pydantic 模型：注册时立刻抛出 `YapiDeclarationError`。
- 函数签名中同时出现多个 Pydantic 模型参数：注册时直接报错，要求开发者明确合并为一个请求模型。
- 函数体返回值不是 `None` / `str`：运行时抛 `RuntimeExecutionError`。
- 响应模型缺少 docstring 与函数缺少 docstring 时不报错，但日志层面提示开发者补 prompt。

## 8. 第二版明确不做的事

- 不重新引入 `state_*` 参数到装饰器；state 暂时下线。
- 不为每个 HTTP method 提供独立的"AI 行为差异"，所有 method 行为一致。
- 不增加 `router.declare(...)` 的纯声明式入口（已在脑暴中明确放弃）。
- 不在装饰器层增加可观测性 / 重试 / 工具策略等扩展点，这些留给未来再做。

## 9. 测试与验证策略

v2 的测试目标：

- 函数签名推断契约成立（请求模型、响应模型从签名取，OpenAPI 仍正常）
- 装饰器覆盖 `.post` 后，普通 FastAPI 写法在 `PromptRouter` 上不再生效
- prompt 合成顺序正确：响应模型 docstring + 函数 docstring + 函数返回值都进入 system prompt
- 函数返回值非 `None` / `str` 触发明确错误
- 缺少返回类型注解的声明在注册时立即报错
- 通过 `TestClient` 跑端到端：请求 → 推理（替身 agent）→ 响应符合契约
- 用 `uvicorn` + `curl` 跑一次真实运行面 smoke test

## 10. 迁移与兼容性

- 这是一次破坏式升级，旧的 `llm_post(...)` 装饰器与 `request_model=` / `response_model=` 形式直接移除。
- v1 中存在的 `state_storage` / `state_key` / `state_dependencies` 参数从 API 表面消失。
- `MemoryStorage` / `LocalStorage` / `yapi.state` 模块在仓库中保留，但不再被 v2 核心运行路径使用；等 state 设计第二轮再决定如何重新挂载。
- showcase 应用（`examples/wish_api.py`）会改写为 v2 形态，去掉 storage 与依赖参数。

## 11. 一句话总结

`yapi` v2 把 API 进一步收紧成：

**"FastAPI 的 .post 装饰器 + 一个有 docstring 的函数 = 一个 prompt-first HTTP endpoint。"**

state 暂时退场，先把声明体验做到尽可能贴近 FastAPI 原生习惯。
