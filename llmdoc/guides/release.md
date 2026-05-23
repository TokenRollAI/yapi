---
id: guides.release
title: 发布到 PyPI
layer: guide
tags: [guide, release, packaging, pypi, ci]
status: stable
---

# 发布到 PyPI

这份 guide 写给接手 yapi release 流水线的人，重点解释**为什么这样设计**，而不是逐步流水账（流水账 README 已经够了）。

## 触发模型：只有 tag 才发版

`.github/workflows/release.yml` 第 4-6 行：

```yaml
on:
  push:
    tags:
      - "v*"
```

含义：任何合入 `main` 的 commit 都不会触发发版；只有显式 `git tag v*` 并 push 上去时 Actions 才动手。把"代码就绪"和"决定发版"两件事解耦——可以在 main 上累积若干 commit，只在准备好的那一刻打 tag。

## 版本号闸门：tag 必须等于 pyproject 的 version

`build` job 在打包前先做一次校验（`.github/workflows/release.yml` 第 24-32 行）：把 `${GITHUB_REF_NAME#v}` 与 `pyproject.toml` 的 `[project].version` 用 `tomllib` 取出后做 `[ "$tag" != "$pkg" ]` 比对，对不上整个 release fail。

这条规则的价值不是"我们多写了一步"，而是它把"改 version 文件"和"打 tag"两件容易错位的事强制对齐：任何接手发版的人，只要 tag 错了或者忘记 bump `pyproject.toml`，CI 会在 build 阶段直接 red，发不出去。**不要绕过它**，比如不要在 Actions 上手动重新触发或临时 patch tag。

## Trusted Publishing 三件套（一次性配置，缺一不可）

yapi 没有 PyPI API token，发布走 OIDC Trusted Publishing。三件套必须**全部就位**，否则 `publish` job 会拿不到 token，并以一个对新手不友好的 403 失败：

1. **PyPI 后台 pending publisher**：在 https://pypi.org/manage/account/publishing/ 添加，字段：
   - owner = `TokenRollAI`
   - repository = `yapi`
   - workflow = `release.yml`
   - environment = `pypi`
2. **GitHub 仓库 environment**：在仓库 Settings → Environments 创建名为 `pypi` 的 environment，名字必须与 workflow 中 `environment.name: pypi`（第 51-52 行）字面对应。如果该 environment 配了 required reviewers，`publish` job 会在执行前阻塞等人点 Approve——这是一个可选的人工闸门。
3. **workflow id-token 权限**：`publish` job 必须声明 `permissions: id-token: write`（第 54-55 行），否则 GitHub 不会签发 OIDC token，pypa 的 publish action 就拿不到凭据。

低风险点：没有长期 API token，泄露面更小。代价：首次配置一旦三处错位，错误日志不会告诉你是哪一处错了，必须**逐处对齐复核**。

## 发版动作

1. 在 `pyproject.toml` bump `[project].version` 为新版本号 `X.Y.Z`。
2. commit + push 到 main。
3. `git tag vX.Y.Z` && `git push origin vX.Y.Z`。
4. 等 Actions：`build` 校验版本号、构建 sdist+wheel、`twine check`、上传 artifact；`publish` 通过 OIDC 推上 PyPI。

整套动作里**唯一不可逆**的是 step 3。如果 step 1 bump 错了版本号，step 2 的 push 还可以补 commit；一旦 tag 推上去且 build 通过，publish 成功后该版本号在 PyPI 上就永久占用了——PyPI 不允许覆盖已发布版本。

## CI 与 secrets

`.github/workflows/ci.yml` 在 push 与 PR 上跑 pytest 矩阵（Python 3.12 / 3.13）。**它不需要任何 secrets**——测试不连真 LLM provider，全部用 `agent_runner` fake 或 `YAPI_MODEL=test` 走 PydanticAI 的 `TestModel`。详情见 [`../must/project-shape.md`](../must/project-shape.md) 的 `YAPI_MODEL` 段。

这意味着 fork / 迁仓库时，CI 不需要任何配置就能绿；release 流程也不需要长期 secret，只要配好 Trusted Publishing 三件套即可。

## 首次发布的真实历史

`pyyapi` v0.1.0 由 commit `307836a` + tag `v0.1.0` 发布到 PyPI。

`pyyapi` v0.2.0 随 v2.1 落地一起发布；`pyproject.toml` `[project].version` 已 bump 至 `0.2.0`。这是一次破坏性 minor 发版（项目仍在 `0.x` 期，按 SemVer 约定 minor 允许带破坏点）；破坏点见 v2.1 spec §9.2，迁移指引随附 README。CI 与 release 流水线行为不变，仍按上述 tag-driven + Trusted Publishing 三件套发布。
