---
id: overview.project-overview
title: yapi 项目定位
layer: overview
tags: [overview, product, scope, history]
status: stable
---

# yapi 项目定位

## 产品定位

yapi 是一个面向**应用后端**的 prompt-first 声明式 HTTP 框架：把"声明一个 HTTP 接口"和"声明一个 prompt+结构化输出契约"合并为一件事。开发者只需要：

1. 定义请求模型与响应模型（两个 `pydantic.BaseModel` 子类）。
2. 在 `PromptRouter` 上装饰一个有 docstring 的同步函数。
3. 设置一个环境变量 `YAPI_MODEL` 指向 PydanticAI 支持的模型字符串。

框架自动负责签名内省、prompt 组装、Agent 调用、响应校验、OpenAPI 生成。这相当于"把 FastAPI 路由当 prompt 模板写"。

## 产品气质

- **小而锋利**：源码集中在 9 个 `.py` 文件内（截至 v2.1），公开 API 仅 7 个 re-export（`PromptRouter` + runner Protocol 二人组 + 4 个错误/警告类）；目的不是堆功能，是把"prompt 即接口"这一个点钉死。
- **复用 FastAPI 的所有外围设施**：路由、`Depends`、OpenAPI、`TestClient`、ASGI 启动，都是 FastAPI 原生行为。yapi 不重造轮子。从 v2.1 起 `PromptRouter` 直接是 `APIRouter` 的真超集，普通 FastAPI 路由与 prompt 路由可在同一 router 内混挂。
- **声明优先**：所有契约违反在 import 期就抛 `YapiDeclarationError`，未识别 kwarg 发 `YapiUsageWarning`，运行期不靠"猜"。

## 目标用户

- 已经用 FastAPI 写过后端、习惯 BaseModel 风格的 Python 开发者。
- 需要把 LLM 调用包装成"看起来跟普通接口一样"的 HTTP endpoint，而不是直接写 chat agent loop。
- 对结构化输出（JSON schema 严格匹配）有强约束的业务场景。

## 产品边界（明确不做的事）

- **不是 chat application**：没有会话状态、没有 message history、没有 streaming 接口。每个请求都是一次性的 prompt → 结构化响应。
- **不是 agent platform**：不提供 tool 调度、planner、multi-step orchestration。tool 概念完全交给 PydanticAI Agent 内部消化（v2 也尚未暴露 tool 注入入口）。
- **不是 prompt 管理平台**：没有 prompt 版本管理、A/B 测试、experiment tracking。prompt 的"版本"就是函数与模型的 docstring，由 git 管理。
- **不重新封装 LLM SDK**：模型字符串原样交给 PydanticAI；API key、retry、timeout 都委托给 pydantic-ai 处理。

state / storage 暂时退出核心 API（v2 §2、§10、v2.1 §10），未来是否回归由后续 spec 决定；当前代码中**没有**对应模块，v1 残留 `StateStoreError` 也在 v2.1 物理删除。

## v1 → v2 简史

- **v1 spec**（`docs/superpowers/specs/2026-05-20-yapi-design.md`，556 行 draft）描绘了完整愿景：
  - 装饰器 `@router.llm_post(...)` 显式接收 `request_model=`、`response_model=`、`state_storage=`、`enable_query=`、`state_dependencies=[Depends(...)]`。
  - 内部 4 个组件：`PromptRouter` / `PromptEndpoint` / `StateStore` / `Runtime`。
  - 首版要落地 `MemoryStorage` + `LocalStorage`，含 `update_state(patch)` 隐藏 tool 与 `state_key` 解析。
- **v0 实现 plan**（`docs/superpowers/plans/2026-05-20-yapi-v0-implementation.md`，1605 行）基于 v1 设计，要求创建 `yapi/state.py` / `yapi/storage.py` / `tests/test_storage.py` 等。当前代码已偏离这份 plan，**勿按此 plan 工作**。
- **v2 spec**（`docs/superpowers/specs/2026-05-21-yapi-v2-design.md`，179 行 draft）显式取代 v1 第 4、6、9、10 节的 API 形态：
  - `llm_post` → 直接复用 FastAPI 的 `.post` / `.get` 等。
  - 装饰器收紧到只有 path 参数，契约全部从函数签名推断。
  - prompt 由四段拼接（DEFAULT_SYSTEM_PREFIX → response model docstring → function docstring → 动态 prompt）。
  - state 暂时下线。
  - showcase 复刻 v2 §3.1 的最小例子，即当前的 `examples/wish_api.py`。

**为什么从 v1 收紧到 v2**：v1 把太多决策塞进装饰器参数，与"开发者已经在签名里写过一次 BaseModel"产生重复；同时 state 抽象的成本与第一版要交付的价值不匹配。v2 通过"函数签名是唯一真相来源"把 API 表面降到最小，state 留作后续单独设计。

## v2 → v2.1 简史

- **v2.1 spec**（`docs/superpowers/specs/2026-05-24-yapi-v2.1-design.md`）在 v2 基础上做增量扩展，版本号 `0.1.0` → `0.2.0`：
  - `PromptRouter` 由"覆盖 `.get/.post/...` 的 APIRouter 子类"升级为**真超集**：原生方法走 FastAPI 通道，prompt 路由收敛到 `router.prompt.{get,post,put,patch,delete}` 子命名空间，混挂被官方鼓励。
  - 装饰器从 v2 "静默丢弃 FastAPI 原生 kwargs" 改为三档处理：透传白名单（OpenAPI / 路由元数据）/ 拒绝清单（与 yapi 契约冲突的 3 个 kwarg）装饰期报错 / 未知 `YapiUsageWarning`。
  - 函数签名内省扩展为 ParamRole 多分类，识别 `Annotated[BaseModel, Body()]` / `Annotated[T, Depends()]` / `Annotated[str, Query()/Header()/Cookie()/Path()/Form()/File()]` 等 FastAPI 原生写法；`async def` 路由函数受支持。
  - `agent_runner` 从朴素 callable 抬升为 `AgentRunner` Protocol + `RunnerContext` frozen dataclass（含 `path / method`），`PydanticAIRunner` 类化、构造期 `YAPI_MODEL` 缺失 warning、isinstance 快路径；v2 风格 `lambda **_: {...}` 仍由 `_LegacyCallableRunner` 透明兼容。
  - 公开符号从 1 个扩到 7 个 re-export：除 `PromptRouter` 外，新增 `AgentRunner / RunnerContext / YapiError / YapiDeclarationError / RuntimeExecutionError / YapiUsageWarning`；v1 残留 `StateStoreError` 物理删除；`yapi/py.typed` 落库。
  - `Runtime` 接入 `prompt_composer` 注入点 + module-level `yapi.runtime` / `yapi.router` logger。

**为什么从 v2 收紧到 v2.1**：v2 把所有 HTTP 方法都强行变成 prompt 路由，使得"健康检查 / metrics / 普通 CRUD + LLM 接口"必须新开 router，与"FastAPI 自然扩展"的口号矛盾；同时静默丢弃 FastAPI 原生 kwargs 是已登记的开发者陷阱。v2.1 通过显式 `.prompt.*` 入口 + kwarg 三档处理把这两条暗坑显性化。详细破坏点见 v2.1 spec §9.2。

## 关键事实速查

- 公开符号：7 个（`yapi/__init__.py` `__all__`）。
- Python：≥ 3.12。
- 关键依赖：`fastapi`、`pydantic`、`pydantic-ai`、`uvicorn`。
- 唯一外部配置：`YAPI_MODEL`（环境变量）。
- showcase：`examples/wish_api.py`（最小骨架）、`examples/mixed_router.py`（混挂）、`examples/with_depends.py`（`Depends`）、`examples/custom_runner.py`（自定义 runner Protocol）。
- 测试规模：8 个 test 文件覆盖 router / runtime / compat / runner / dx / integration / exports；规模较 v2 显著扩张（不写死数字，避免快速过时）。

详细执行模型见 [`../architecture/request-lifecycle.md`](../architecture/request-lifecycle.md)，agent 契约见 [`../architecture/agent-runner-contract.md`](../architecture/agent-runner-contract.md)。
