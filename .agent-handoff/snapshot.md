# Handoff Snapshot

## Current State

- Last updated: 2026-10-11
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 完成本轮 Labs 提交推送、正式增量更新、答题前向 migration、35 条招聘来源状态复核及 Labs 测试服务关闭。
- Current status: 已完成。本轮生产部署代码 revision 为 `d06af75`；Web/Worker/Beat 使用 `kaj-blog-web:d06af75a9c31`，Caddy 保持 `2cbead0`。生产已应用 `learning.0014/0015`；公网维护 marker 已移除，关键公网路径和 health 为 `200`。35 条来源最新终态为 30 HEALTHY、1 DEGRADED/TRUNCATED、4 STALE（Qcraft 超时、2 Hotjob 和1 Meituan响应错误）。Labs Web、Worker、Beat、Outbox service/timer 与 P12 PostgreSQL/Redis/Mailpit 已停止。
- Immediate next actions:
  - 单独调查定向来源复查期间两次 PostgreSQL backend exit-code 2 自动恢复的根因；容器无 restart/OOM，当前 healthy。
  - 在 Labs 收集安全响应契约并修复 3 个仍 stale 的 HTTP 来源；定位 Qcraft 单来源超时，后续只按受限检查恢复其状态。
  - 外部 P0 性能复测与生产知识审核 capability check 保持独立运维待办。
- Active files:
  - `apps/learning/migrations/0014_quizattempt_mode_and_more.py`
  - `apps/learning/migrations/0015_quiz_attempt_mode_db_default.py`
  - `apps/opportunities/checks/`
  - `docker/web/Dockerfile.incremental`
  - `docs/releases/2026-10-11-production-increment/`
  - `docs/releases/2026-10-09-next-iteration/announcement.md`
  - `.agent-handoff/snapshot.md`
  - `.agent-handoff/validation.md`
- Blockers: 本轮部署和 Labs 关停均已完成。剩余 4 个来源保持真实失败状态；PostgreSQL backend 自动恢复根因待调查。
- Open questions:
  - 无当前发布范围内的待确认项。

## Recovery Summary

- 本轮生产部署代码提交为 `d06af75`；Labs worktree 内的相关测试服务已关闭。正式 Web/Worker/Beat 为 `d06af75a9c31` 候选；Caddy 为 `2cbead0`。
- 旧 Labs 工作树完整保留在 `labs-test-environment-archive-20261009`（detached `a06a94f`），其脏改动未迁入新分支；旧 `codex/labs-next-iteration` 分支仍保留。
- 正式公告与本轮增量记录分别以 `docs/releases/2026-09-20-production-increment/` 和 `docs/releases/2026-10-09-next-iteration/announcement.md` 为准。
- 2026-10-09 生产只读指标快照截止 `03:20 UTC`：9 个 ACTIVE/有行为账户、159 篇文章、301 条修订、4 个 APPROVED 文档、4 套 PUBLISHED 题库（公开最新版 999 题）；TaskRun 1,737,523 条，成功率 `99.9930%`，重试率 `0.1112%`，P95 `254ms`。该数据不属于下一轮效果。
- 2026-10-10 生产招聘定时检查只读诊断：Celery 全局硬/软时限未配置；最新 18:00 批次完整处理 129 个来源，0 个未执行。35 个来源失败中 34 个为浏览器适配器不可用/响应校验失败，仅 1 个为单请求超时；近 30 天来源时限错误仅 1 条。另有 2026-09-20 单次 TaskRun 租约最终失败记录，作为独立异常保留，不解释当前重复失败模式。
- 进一步核验确认浏览器服务实际可运行，但 Worker 容器的 bind mount 与宿主当前 `/run/kaj-opportunity-browser` 是不同目录 inode；浏览器 systemd 服务于 2026-09-26 启动，Worker 容器于 2026-09-20 创建。持续的 `adapter_response_invalid` 分布于 Hotjob、Dahua、Getui、Meituan、Beisen，实时响应体未持久化。
- 2026-10-10 Labs 已通过有界 SafeHttpClient/robots 直连验证 Dahua、Beisen、Getui、Hotjob、Meituan 当前来源响应，并修复四种 adapter 的契约差异；聚焦回归 `35 passed`。没有运行生产采集或写入数据库。
- 2026-10-11 发布前生产快照：35 条启用招聘来源为 `STALE`，26 条最后错误为浏览器 socket 不可用、8 条为响应契约错误、1 条为请求超时；没有活动来源检查运行。该状态已由本轮定向复查更新，最终结果见 deployment record。
- 2026-10-11 生产执行完成：生产 dump、媒体、Compose 备份已校验；`0014/0015` 已应用；browser runtime 已更新到 `d06af75` 并与 Worker socket inode 对齐；Nginx marker 已关闭、公网关键路径 `200`。来源复查结果和数据库 backend 自动恢复见正式 deployment record。
