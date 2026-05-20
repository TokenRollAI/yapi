# yapi 设计文档

日期：2026-05-20
状态：draft

## 1. 项目定位

`yapi` 是一个 Prompt-first 的声明式 HTTP 框架层。

它基于 FastAPI、Pydantic 与 PydanticAI，把一次传统的 HTTP Controller 逻辑压缩成一组声明：

- 请求模型
- 响应模型
- prompt
- 可选的状态存储
- 可选的查询能力

开发者不需要编写常规业务 handler 逻辑，只需要声明输入输出契约与核心提示词，`yapi` 负责把 HTTP 请求自动转换为一次带结构化输出约束、可选状态上下文与可选工具调用能力的 Agent 运行。

`yapi` 的核心卖点不是“给 FastAPI 接一个 LLM”，而是：**把传统 Controller 逻辑坍缩成声明。**

---

## 2. 第一版目标

第一版优先证明以下三件事：

1. **真的没有业务代码**：开发者只写模型与 prompt，就能声明一个可用接口。
2. **真的有结构化输出**：HTTP 返回结果稳定满足 `response_model`。
3. **真的有持久化记忆**：同一路由的多次请求之间可以读取并更新 state。

第一版的目标不是功能全面，而是用最小闭环证明 `yapi` 的产品形态成立。

---

## 3. 目标用户与产品气质

第一版优先服务作者本人对框架气质的追求，而不是先追求大众接受度。

预期气质如下：

- **正经外壳**：看起来像一个自然的 FastAPI 扩展
- **极简黑魔法**：API 非常克制，但行为有明显的“在偷偷施法”的感觉
- **非聊天应用 SDK**：它首先是 HTTP 框架，而不是一个聊天或 agent playground 工具

理想的第一眼体验是：

> 开发者以为自己只是写了一个 route decorator，直到发现 handler 里面根本没有业务逻辑，接口却真的能运行。

---

## 4. 对外 API 设计原则

第一版对外只暴露少量核心概念：

- `PromptRouter`
- `request_model`
- `response_model`
- `state_storage`
- `enable_query`

目标是让开发者看到的不是一套复杂 runtime，而是一套非常直接的声明接口。

一个理想的使用方式如下：

```python
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from yapi import PromptRouter, LocalStorage

app = FastAPI()
router = PromptRouter()
storage = LocalStorage(path="./app_state.db")

class WishIn(BaseModel):
    user_id: str
    wish: str

class WishOut(BaseModel):
    granted: bool
    message: str
    remembered_mood: str | None = None


def fetch_profile(user_id: str) -> dict:
    return {"user_id": user_id, "vip": True}


@router.llm_post(
    "/wish",
    request_model=WishIn,
    response_model=WishOut,
    state_storage=storage,
    enable_query=False,
    state_dependencies=[Depends(fetch_profile)],
)
def make_a_wish():
    """
    你是一个愿望受理实体。
    你需要根据用户输入、上下文状态与规则，决定是否实现愿望，
    并返回结构化结果。
    如果状态需要更新，你可以使用内置的状态更新能力。
    """


app.include_router(router)
```

设计重点：

- handler 本身不承载业务逻辑
- docstring 或等效 prompt 字段是核心业务定义
- 输入输出契约继续由 Pydantic 保持秩序
- 状态与查询能力以声明方式挂载

---

## 5. 第一版运行模型

第一版的请求生命周期如下：

1. FastAPI 接收请求。
2. `yapi` 将请求解析并校验为 `request_model`。
3. `yapi` 从 `state_storage` 读取本次请求对应的 state。
4. `yapi` 执行 `state_dependencies`，将结果并入运行上下文。
5. `yapi` 组装 prompt、request data、state 与依赖数据。
6. `yapi` 调用底层 PydanticAI Agent。
7. Agent 输出被约束为 `response_model`。
8. 如果运行过程中 state 被修改，则自动持久化。
9. `yapi` 返回标准 JSON 响应。

这个模型强调一点：

**Controller 逻辑被 prompt 吞掉了，但 HTTP 世界的输入输出秩序仍然存在。**

---

## 6. 第一版必须实现的能力

第一版必须实现以下能力：

### 6.1 声明式路由装饰器

至少实现：

- `@router.llm_post(...)`

可选保留未来扩展：

- `llm_get(...)`

第一版不追求覆盖全部 HTTP 方法，只需要把一条最顺的路径打磨完整。

### 6.2 强类型输入输出契约

- 输入必须通过 Pydantic 校验
- 输出必须被约束为 `response_model`
- 结构化输出错误应由底层重试或错误包装机制处理

这是 `yapi` 与普通 LLM 调用脚本的核心分界线。

### 6.3 State 读取与自动持久化

- 请求开始前读取 state
- 请求结束前保存变更后的 state
- 多次请求之间可保持连续上下文

### 6.4 Prompt 作为唯一业务逻辑入口

第一版不提供常规 Python handler 作为补充业务层。

如果开发者仍然可以在 handler 里写大段逻辑，那么 `yapi` 的产品概念会失焦。

### 6.5 最小可用存储实现

第一版至少提供：

- `MemoryStorage`：用于测试与短生命周期演示
- `LocalStorage`：用于本地持久化演示

这样可以让框架开箱即跑，而不用先引入 Redis 或 PostgreSQL。

---

## 7. 第一版明确不做的能力

为保持边界清晰，第一版明确不做以下内容：

### 7.1 不做复杂 Tool 生态

`enable_query` 作为开关保留，但第一版只支持极少量、明确的工具注入方式。

第一版不尝试成为通用 agent platform。

### 7.2 不做复杂生命周期钩子

不优先设计：

- middleware hook
- before/after hook
- plugin hook
- policy hook

第一版需要的是少量但完整的魔法，而不是扩展机制堆砌。

### 7.3 不做多 provider 抽象

第一版绑定一条默认底层路径，例如：

- FastAPI
- Pydantic
- PydanticAI

未来可以扩展 provider，但 v0 不为了兼容性牺牲清晰度。

### 7.4 不做企业级状态系统

第一版不处理：

- 分布式锁
- 状态版本冲突
- 多租户隔离策略
- 高级事务语义

只要 state 可稳定读写、易理解、易演示即可。

### 7.5 不做复杂 Prompt 工程体系

第一版不引入：

- prompt registry
- prompt inheritance
- policy DSL
- prompt 管理后台

第一版的关键体验是：**开发者真的只写一段自然语言。**

---

## 8. 内部架构拆分

第一版内部只拆四个核心组件：

1. `PromptRouter`
2. `PromptEndpoint`
3. `StateStore`
4. `Runtime`

### 8.1 PromptRouter

职责：

- 提供 `llm_post(...)`
- 接收开发者的声明元数据
- 将声明注册成真实 FastAPI route
- 生成并绑定实际可执行的 handler

它不负责推理，不负责状态存储，不负责业务逻辑。

它的本质是：**把声明编译成路由。**

### 8.2 PromptEndpoint

职责：

- 保存单个 endpoint 的静态定义
- 持有路径、HTTP 方法、prompt、模型、state 配置与 query 配置
- 作为运行前的“配方卡”供 Runtime 使用

每一个 `@router.llm_post(...)` 最终都应该沉淀为一个 `PromptEndpoint` 实例。

这能避免 decorator 闭包承载过多责任，也为未来扩展调试、追踪与 OpenAPI 补充元数据提供稳定落点。

### 8.3 StateStore

职责：

- 读取 state
- 保存 state

建议第一版接口保持极小：

```python
class StateStore(Protocol):
    def load(self, key: str) -> dict | None: ...
    def save(self, key: str, state: dict) -> None: ...
```

可选扩展：

```python
    def delete(self, key: str) -> None: ...
```

第一版不引入事务、版本与并发控制语义。

### 8.4 Runtime

职责：

1. 接收当前 `PromptEndpoint`
2. 接收解析后的请求数据
3. 装载 state
4. 组装模型上下文
5. 创建并运行底层 Agent
6. 处理结构化输出
7. 捕捉 state 变更并持久化
8. 返回 `response_model` 实例

架构边界上：

- `PromptRouter` 属于声明期
- `Runtime` 属于执行期

这个分层可以为未来的 streaming、retry、trace 与 tool policy 保留清晰演进路径。

---

## 9. State 模型设计

State 是 `yapi` 第一版的第二核心卖点，因此必须设计得既自然又不脏。

### 9.1 State 的定位

State 不是普通缓存，也不是数据库 ORM 对象。

它是一次 endpoint 推理运行时可见的、可持久化的上下文对象，用于承载：

- 历史对话或历史交互摘要
- 用户偏好
- 路由级业务上下文
- 依赖查询得到的附加上下文

### 9.2 State 的来源

第一版 state 由三部分合成：

1. `state_storage` 里已存在的持久化 state
2. `state_dependencies` 返回的外部上下文数据
3. 当前请求中的 request data

其中：

- request data 不直接写回 state，除非运行时显式决定更新
- state_dependencies 的结果默认注入运行上下文，但是否持久化由运行时策略决定

### 9.3 State 的可见性

Agent 在推理时应该能感知到完整上下文，包括：

- 当前请求数据
- 当前已知 state
- 注入依赖结果

但这些内容应该在 prompt 组装层被明确分区，避免信息混杂。

建议上下文在内部组织成类似结构：

```python
{
    "request": {...},
    "state": {...},
    "injected": {...},
}
```

### 9.4 State 修改方式

第一版不建议让模型直接输出整个新 state。

更推荐的方式是内置一条隐藏的状态更新能力，例如：

- `update_state(patch: dict)`

运行时记录 patch，并在本次推理结束后合并到当前 state，再统一持久化。

这样有几个好处：

- 模型只修改需要变化的部分
- 运行时更容易审计 state 变更
- 不需要模型重建完整状态对象
- 更适合未来扩展状态变更日志

### 9.5 State Key 解析

第一版需要一个最小但明确的 state key 策略。

推荐：

- 默认由 `request_model` 中的显式字段生成，例如 `user_id` 或 `session_id`
- 装饰器允许开发者声明 `state_key` 或 `session_resolver`

避免第一版自动猜测过多字段，否则行为会变得不可解释。

---

## 10. Query / Tool 设计

第一版保留 `enable_query`，但严格控制范围。

### 10.1 默认关闭

默认 `enable_query=False`。

这样能确保：

- 响应时延更可控
- Token 消耗更可控
- demo 更容易稳定复现

### 10.2 开启后的行为

当 `enable_query=True` 时：

- Agent 可以调用显式注册的少量工具
- 工具主要用于补足 state 中没有的信息
- 工具结果回流后继续本次推理

### 10.3 第一版工具边界

第一版工具只服务于“缺失信息补全”，不承担复杂 workflow orchestration。

也就是说：

- 可以查询
- 不强调复杂行动链
- 不强调通用 agent 平台能力

---

## 11. 错误处理策略

第一版必须定义最基本的错误边界，避免 `yapi` 看起来像脆弱的 demo。

### 11.1 输入错误

- 由 FastAPI / Pydantic 负责返回标准请求校验错误
- `yapi` 不重复包装这类错误

### 11.2 输出结构化失败

- 由底层 PydanticAI 结果类型约束与重试机制优先处理
- 若多次失败，`yapi` 返回统一的服务端错误响应
- 错误信息应强调“模型未能生成符合契约的结果”

### 11.3 State 读取失败

- 对于不可恢复的存储错误，直接返回服务错误
- 第一版不引入复杂降级策略

### 11.4 State 保存失败

- 如果响应依赖状态变更成功，应将其视为请求失败
- 第一版不采用“响应成功但状态后台补写”的异步补偿策略

### 11.5 Tool 查询失败

- 若 route 开启了 query，工具调用失败应回传给运行时
- 第一版默认将其视为本次推理失败，而不是静默忽略

整体原则：

**第一版宁可失败得明确，也不要靠隐式降级掩盖问题。**

---

## 12. OpenAPI 与框架感

`yapi` 必须保留 FastAPI 的一项关键气质：

**它看起来像真正的 HTTP 框架，而不是一段 AI 脚本。**

因此第一版需要保证：

- 请求模型进入 OpenAPI
- 响应模型进入 OpenAPI
- 路由路径与方法正常出现在文档中
- 使用体验尽量贴近 FastAPI 原生习惯

第一版暂不要求在 OpenAPI 中完整表达 prompt 或状态运行时细节，但可以为未来补充扩展字段预留空间。

---

## 13. Demo 设计原则

第一版 demo 不是为了展示功能多，而是为了证明概念成立。

demo 必须同时证明：

1. 开发者真的没写业务代码
2. 返回结果真的稳定符合模型
3. 状态真的能在多次请求之间延续

推荐 demo 气质：

- 看起来像一个很正经的接口
- 行为却明显带有记忆和人格化痕迹
- 让人意识到“这不是 chat app，而是一个被 HTTP 调用的实体”

---

## 14. 测试策略

第一版测试重点不在性能或复杂集成，而在于验证框架承诺。

### 14.1 单元测试

覆盖以下对象：

- `PromptEndpoint` 的配置编译
- `StateStore` 的 load/save 行为
- `Runtime` 的上下文组装逻辑
- state patch 合并逻辑

### 14.2 集成测试

使用 FastAPI TestClient 或等效方式验证：

- 请求能正确进入 `request_model`
- 响应能正确满足 `response_model`
- 连续两次请求之间 state 能被读写
- 开启与关闭 `enable_query` 的行为边界正确

### 14.3 演示级验证

准备一个最小 showcase 用例，手动验证：

- OpenAPI 展示正常
- 请求体验足够直观
- 第二次调用确实体现记忆变化

---

## 15. 非目标

第一版明确不是以下产品：

- 通用 agent orchestration 平台
- 企业级工作流引擎
- 多模型统一抽象层
- 完整分布式状态管理系统
- Prompt 管理平台

这些方向未来可以演进，但不属于 v0 的验证目标。

---

## 16. 一句话总结

`yapi` v0 应该是一个：

**把 Pydantic 契约、Prompt 与可持久化状态编译成 HTTP endpoint 的极简框架。**

它的价值不在于功能繁多，而在于让开发者第一次直观感受到：

**HTTP 接口的业务逻辑，真的可以只剩声明。**
