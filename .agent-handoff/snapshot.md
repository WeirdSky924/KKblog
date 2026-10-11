# Handoff Snapshot

## Current State

- Last updated: 2026-10-12
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 整理根 README 与相关状态摘要，使其符合 2026-10-11 正式增量发布及截至 2026-10-12 可核验的项目情况。
- Current status: 已完成。生产应用 revision 为 `d06af75`。根 README、架构入口、运维入口和实施清单状态段已更新；运行数据均注明快照日期与来源，Git 交付以远端读回为准。
- Immediate next actions:
  - README 文档任务无后续动作；保留以下独立运维待办：PostgreSQL backend 自动恢复根因调查、4 条仍 `STALE` 的来源复核、外部 P0 正式性能金丝雀和生产知识审核 capability check。
- Active files:
  - `README.md`
  - `docs/architecture/README.md`
  - `docs/operations/README.md`
  - `docs/planning/implementation-todolist.md`
  - `.agent-handoff/snapshot.md`
  - `.agent-handoff/validation.md`
- Blockers: 无 README 文档阻塞；Labs 服务仍按上一轮要求保持关闭。4 条来源状态与 PostgreSQL backend 根因调查仍是独立运维事项。
- Open questions:
  - 无当前发布范围内的待确认项。

## Recovery Summary

- 2026-10-12 README 快照已注明：生产代码 revision `d06af75`；业务规模数据来自 2026-10-09 生产只读快照，招聘来源聚合来自 2026-10-11 检查记录，P0 金丝雀仍未执行。
- 本轮生产部署代码提交为 `d06af75`；Labs worktree 内的相关测试服务已关闭。正式 Web/Worker/Beat 为 `d06af75a9c31` 候选；Caddy 为 `2cbead0`。
- 旧 Labs 工作树完整保留在 `labs-test-environment-archive-20261009`（detached `a06a94f`），其脏改动未迁入新分支；旧 `codex/labs-next-iteration` 分支仍保留。
- 正式公告与本轮增量记录分别以 `docs/releases/2026-09-20-production-increment/` 和 `docs/releases/2026-10-09-next-iteration/announcement.md` 为准。
- 2026-10-09 生产只读指标快照截止 `03:20 UTC`：9 个 ACTIVE/有行为账户、159 篇文章、301 条修订、4 个 APPROVED 文档、4 套 PUBLISHED 题库（公开最新版 999 题）；TaskRun 1,737,523 条，成功率 `99.9930%`，重试率 `0.1112%`，P95 `254ms`。该数据不属于下一轮效果。
- 2026-10-10 生产招聘定时检查只读诊断：Celery 全局硬/软时限未配置；最新 18:00 批次完整处理 129 个来源，0 个未执行。35 个来源失败中 34 个为浏览器适配器不可用/响应校验失败，仅 1 个为单请求超时；近 30 天来源时限错误仅 1 条。另有 2026-09-20 单次 TaskRun 租约最终失败记录，作为独立异常保留，不解释当前重复失败模式。
- 进一步核验确认浏览器服务实际可运行，但 Worker 容器的 bind mount 与宿主当前 `/run/kaj-opportunity-browser` 是不同目录 inode；浏览器 systemd 服务于 2026-09-26 启动，Worker 容器于 2026-09-20 创建。持续的 `adapter_response_invalid` 分布于 Hotjob、Dahua、Getui、Meituan、Beisen，实时响应体未持久化。
- 2026-10-10 Labs 已通过有界 SafeHttpClient/robots 直连验证 Dahua、Beisen、Getui、Hotjob、Meituan 当前来源响应，并修复四种 adapter 的契约差异；聚焦回归 `35 passed`。没有运行生产采集或写入数据库。
- 2026-10-11 发布前生产快照：35 条启用招聘来源为 `STALE`，26 条最后错误为浏览器 socket 不可用、8 条为响应契约错误、1 条为请求超时；没有活动来源检查运行。该状态已由本轮定向复查更新，最终结果见 deployment record。
- 2026-10-11 生产执行完成：生产 dump、媒体、Compose 备份已校验；`0014/0015` 已应用；browser runtime 已更新到 `d06af75` 并与 Worker socket inode 对齐；Nginx marker 已关闭、公网关键路径 `200`。来源复查结果和数据库 backend 自动恢复见正式 deployment record。
