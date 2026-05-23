---
id: memory.reflection.2026-05-24-pypi-release-bootstrap
title: 反思 - pyyapi 首次 PyPI 发布与 GitHub Trusted Publishing 流水线
layer: memory
tags: [reflection, release, packaging, pypi, naming]
status: stable
date: 2026-05-24
---

# 反思：pyyapi 首次 PyPI 发布

## 任务

把已基本完成的 yapi 包发布到 PyPI，并配齐 GitHub Actions 上的 tag-driven 自动发布。最终在 `pyyapi` 名下完成 v0.1.0，pipeline 走 Trusted Publishing。

## 评估：哪些是结构性结论，哪些是一次性教训

### 结构性、必须固化

**最值得固化的不是「这次怎么发的」，而是 distribution name ≠ import name 这件事**。`pip install pyyapi` 但 `from yapi import PromptRouter`——这个不对称从此长期存在于 README、错误信息、PyPI 项目页、Trusted Publisher 配置、未来任何"安装一下试试"的文档片段里。它不是 release 流水线的属性，而是包本身的属性，因此应进 must/ 而不是 guides/。当前 `must/project-shape.md` 完全没有 packaging 视角，新会话读完依然只知道"项目叫 yapi"——这是 must 层的真实缺口。

**Trusted Publishing 三件套（PyPI pending publisher + GitHub environment + workflow id-token 权限）值得一条独立 guide**。它的失败模式特殊：三处任一缺失，build 通过、publish 静默失败或 403，错误信息对新手不友好；而一次配好后几乎不会再动。这种"低频但高代价"的配置正是 guides/ 的甜点区。如果以后 fork/迁移仓库，没文档会重新踩。

**版本号闸门（tag vs `[project].version` 强校验）是真正的工程纪律**，而不是一次发布的细节。这条规则的价值在于它把"发版本"从"打 tag"两件可错位的事缩成一件——任何接手项目的人都该知道改 version 与打 tag 必须同步。它属于 guide 而非 must（因为不影响读代码），但应在 release guide 里以"为什么这样"的方式而不是"我们做了什么"的方式记录。

### 应停在 memory，不必升级

- **`yapi` 包名被占用、`yapi-py` 中间态、`uv.lock` 跟 name 同步**：这些是"取名那一夜"的特定经过，下次不会重演。属 memory 中决策上下文，最多在 decision log 里留一条"为何叫 pyyapi"。
- **WebFetch 拿不到 PyPI 项目页 / 应改走 JSON API**：是工具坑而非项目知识。如果要沉淀，归属是 `~/.claude/CLAUDE.md` 级的 agent 常识，不是本仓库 llmdoc。
- **sdist 带 tests/**：行业惯例，不算决策，不写。

### 灰色地带 — 需要用户拍板

- **`YAPI_MODEL=test` 与 release 流程的关系**：CI 里跑 pytest 必须有某种方式不真连 LLM，目前事实上靠 `TestModel`。这条信息一半属 must（运行时入口），一半属 release guide（CI 不需要任何 secrets 即可绿灯）。我倾向于在 must 的 `YAPI_MODEL` 段补一句"CI 与 release 流水线均依赖 `test` 字面量做离线冒烟"，避免在 guides 里独立解释一遍。
- **llmdoc/ 是否入库**：本次保持 untracked 是稳妥的（与历史一致），但这意味着任何来自社区的贡献者看不到 doc-gaps、看不到这份反思。这是策略问题不是疏忽，建议下一次有外部 contributor 出现时再决定，不要现在抢答。

## 暴露出的真实文档缺口

1. **`memory/doc-gaps.md` 在 `index.md` 第 40 行被引用但文件不存在**。这是一条具体的 bug——index 在撒谎。recorder 下次过 doc-gaps 时应优先把这个文件补上（哪怕只是骨架），或者从 index 拿掉条目。我倾向于补：本次任务本身就为 doc-gaps 贡献了至少两条素材（distribution name 不对称、release guide 缺失）。

2. **`guides/` 目录至今为空**，index 里写着"当前为空，第一份 guide 将在出现真实工作流时补写"——release 流水线就是那个"真实工作流"。继续放空是欠债。

3. **`must/project-shape.md` 第 60 行写了 `uv sync --extra dev`、`uv run pytest`，但完全没提 PyPI 安装路径**。对于一个已上 PyPI 的库，新会话读完 must 不知道"对外部用户而言怎么装"是个洞。

## 流程层面的判断

这一轮**没有"做错重做"的环节**——包名碰撞是外部事实而非误判，中间态 `yapi-py` 是和用户对齐过程的合理产物。流程上唯一可改进的是**信息验证顺序**：应该在 push 任何 tag 前先用 `curl https://pypi.org/pypi/<name>/json` 静态确认包名归属，而不是依赖 WebFetch；这一条小教训不值得进 guide，记在这里就够了。

另一个值得注意的元教训：**这次的 commit `307836a` 把"改名 + Trusted Publishing workflow + version bump + uv.lock 同步"打进了一个 chore**。从 git 史的可读性看是不太理想的，但因为是 release bootstrap 的不可分原子操作，事后回看也没法干净拆分。下次类似 bootstrap 任务如果时间够，应该先拆"改名"和"加 release.yml"两个 commit。这条不进任何稳定文档，只在这里留存。

## Promotion Candidates（给 recorder 的清单）

按优先级排序。每条都写明"为什么去那里"，避免 recorder 拍脑袋。

1. **must/project-shape.md（增补，不新开文件）**
   在"运行入口"段下方加一节 `安装方式`：明确 `pip install pyyapi` / `from yapi import PromptRouter`，一句话点出 distribution name 与 import name 的不对称。
   *理由*：这是新会话读完 must 之后必须知道的事实，且永远不会变。

2. **must/project-shape.md 的 `YAPI_MODEL` 段（追加一句）**
   "CI 与 release 流水线均依赖 `YAPI_MODEL=test` 做离线冒烟，因此发版无需任何 LLM provider secret。"
   *理由*：避免在 release guide 里重复解释 `TestModel` 角色。

3. **guides/release.md（新建）**
   覆盖：tag-driven 发布流程；版本号 bump 与 tag 必须同步（含 build job 的 tomllib 校验作为"为什么"）；Trusted Publishing 三件套一次性配置（pending publisher / environment `pypi` / `id-token: write`）；CI 不需要 PyPI token。
   *理由*：低频高代价配置，未来 fork/迁仓库的人会感谢这份 guide。

4. **memory/doc-gaps.md（补建）**
   至少包含：(a) `must/project-shape.md` 缺安装/打包视角；(b) `guides/` 长期为空与本次新增 release.md 的关系；(c) llmdoc/ 是否入库待用户决策；(d) `decisions/` 仍空、命名决策（yapi → pyyapi）值得写一条。
   *理由*：index 已经在引用这个文件，物理缺失是 bug。

5. **memory/decisions/2026-05-24-pypi-name-pyyapi.md（可选，新建）**
   一行决策 + 三行上下文：为什么不叫 yapi 也不叫 yapi-py，为什么保留 `yapi` 作为 import 名。
   *理由*：未来若有人提议"改回 yapi"或"重命名 import 路径"，需要这个上下文阻止白做工。

## Follow-up

建议主助手在结束当前任务时按惯例提示用户运行 `/llmdoc:update`，让 recorder 按上面 5 条 promotion candidates 落地。优先级 1、3、4 是必做，2 是顺手，5 是 nice-to-have。
