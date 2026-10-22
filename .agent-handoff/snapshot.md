# Handoff Snapshot

## Current State

- Last updated: 2026-10-22
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 完成交付分支中全部 Labs 改动的提交推送、生产增量更新和测试服务关闭，并建立本轮独立正式公告。
- Current status: 任务分支 `codex/production-increment-20261022` 已从远端 `main=d0407d6` 建立。生产仍运行 `kaj-blog-web:2c78cddf92ac`，live/ready `200`，维护标记关闭。只读状态审计显示终态岗位运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、运行中岗位 TaskRun `0`，当前没有需修复的错误状态。前端完整构建、前端测试 `5 passed`、聚焦 Python 回归 `29 passed`、Ruff、JS 语法和差异检查已通过。候选构建前发现并修复 `.dockerignore` 排除 `static/dist/` 的冲突。尚未提交、构建候选、备份、应用生产 migration、切换生产服务或关闭 Labs 测试服务。
- Immediate next actions:
  - 检查并选择性暂存所有本轮 Labs 代码、测试和文档，提交并推送任务分支，按 fast-forward 集成 `main`。
  - 从本轮完整源码提交构建候选镜像，执行候选 `check --deploy`、migration drift/plan、Compose 和 `collectstatic` 验证。
  - 维护窗口前创建并校验新鲜生产 DB/媒体/Compose 备份；只应用 `navigation.0009_focus_mode_settings`，完成候选切换和健康读回。
  - 正式读回通过后停止本项目 Labs Web/Worker/Beat/Outbox 和 P12 PostgreSQL/Redis/Mailpit；补全公告与 handoff 并完成文档提交推送。
- Active files:
  - `.dockerignore`
  - `apps/navigation/migrations/0009_focus_mode_settings.py`
  - `apps/discovery/templates/discovery/article_detail.html`
  - `static/src/article-focus.js`
  - `static/src/article-reader-mode.js`
  - `static/src/discovery.css`
  - `docs/releases/2026-10-22-production-increment/announcement.md`
  - `docs/releases/2026-10-22-production-increment/deployment-plan.md`
  - `docs/releases/2026-10-22-production-increment/deployment-record.md`
  - `docs/releases/2026-10-22-production-increment/pre-deployment-checklist.md`
  - `docs/releases/2026-10-20-next-iteration/announcement.md`
  - `.agent-handoff/` 当前状态、验证和收口记录
- Blockers: 候选镜像、生产备份、migration 和切换尚未执行。手机版分页浮层和全屏专注的真实视觉/手势验收仍由用户完成；当前任务遵循其此前要求不启动浏览器。
- Open questions:
  - UNKNOWN: 候选镜像的生产网络 migration plan 和 loopback health 是否与预期一致，需在维护前验证。
  - UNKNOWN: 正式手机用户是否确认设置浮层遮挡范围、阅读翻页及全屏专注视觉体验。

## Recovery Summary

- Git：Labs worktree 位于任务分支 `codex/production-increment-20261022`，从新鲜 `origin/main=d0407d6` 建立；所有 Labs 当前修改仍在工作区，尚未暂存或提交。主工作区与其他 worktree 未修改。
- Runtime：`kaj-labs.service` 的工作目录仍是本 worktree，服务 `active/running`，公网 `/health/live=200`。Worker/Beat 和 P12 资源在本轮前置恢复记录中为运行状态；Outbox service/timer 的历史失败/停止状态未改写。
- Production：旧镜像与 10 月 17 日既有状态修正见 `docs/releases/2026-10-17-production-increment/deployment-record.md`；当前旧镜像/health 已读回，迁移与候选切换待本轮授权操作。
- Release record：本轮独立公告与计划在 `docs/releases/2026-10-22-production-increment/`；不复用 Labs 多切片公告作为正式公告。
- Testing: 本轮前端 5 项、Python 聚焦 29 项通过；前端最新手机视觉行为由用户验收，未启动浏览器。
