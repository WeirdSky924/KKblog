# Handoff Snapshot

## Current State

- Last updated: 2026-10-11
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 完成本轮 Labs 代码、文档的提交推送，增量更新正式环境、前向应用答题迁移、按真实检查结果修正 35 条岗位来源状态，并在结束时关闭 Labs 测试服务。
- Current status: 五个本轮代码提交已在 `codex/labs-production-increment` 本地形成；答题、适配器、维护路由和增量镜像契约回归通过。Labs 已应用 `learning.0015` 并读回数据库级 `EXAM` 默认值。生产仍为旧镜像、migration `learning.0013`，尚未备份、迁移、切换或修改来源状态。
- Immediate next actions:
  - 完成新发布公告/计划、迁移与 handoff 文件审查，随后推送任务分支并 fast-forward 到远端默认分支。
  - 从正式 Web/Caddy 镜像构建候选，跑生产只读门禁并创建数据库、媒体、Compose 新备份。
  - 启用 Caddy 维护标记，执行 `learning.0014`/`0015`，按 Web → Worker → Beat 顺序切换并验证静态资源。
  - Worker socket 健康后，使用现有来源检查 service 逐条重查固定 35 条来源；读回结果后关闭 Labs Web 与 P12 PostgreSQL/Redis/Mailpit 测试服务。
  - 外部 P0 性能复测与生产知识审核 capability check 保持独立运维待办。
- Active files:
  - `apps/learning/migrations/0014_quizattempt_mode_and_more.py`
  - `apps/learning/migrations/0015_quiz_attempt_mode_db_default.py`
  - `apps/opportunities/checks/`
  - `docker/caddy/Caddyfile.production`
  - `docker/web/Dockerfile.incremental`
  - `docs/releases/2026-10-11-production-increment/`
  - `docs/releases/2026-10-09-next-iteration/announcement.md`
  - `.agent-handoff/snapshot.md`
  - `.agent-handoff/validation.md`
- Blockers: 没有授权阻塞。Docker Hub 基础镜像请求超时，已通过从当前正式镜像构建的增量路径规避；正式候选镜像仍待构建。
- Open questions:
  - 无当前发布范围内的待确认项。

## Recovery Summary

- 最新核验远端默认分支为 `origin/main=631253f`；当前活动 Labs 分支 `codex/labs-production-increment` 从该基线创建，正式 Web/Worker/Beat 镜像 revision 为 `42adeb4`，应用运行时代码与远端默认分支一致。
- 旧 Labs 工作树完整保留在 `labs-test-environment-archive-20261009`（detached `a06a94f`），其脏改动未迁入新分支；旧 `codex/labs-next-iteration` 分支仍保留。
- 正式公告与本轮增量记录分别以 `docs/releases/2026-09-20-production-increment/` 和 `docs/releases/2026-10-09-next-iteration/announcement.md` 为准。
- 2026-10-09 生产只读指标快照截止 `03:20 UTC`：9 个 ACTIVE/有行为账户、159 篇文章、301 条修订、4 个 APPROVED 文档、4 套 PUBLISHED 题库（公开最新版 999 题）；TaskRun 1,737,523 条，成功率 `99.9930%`，重试率 `0.1112%`，P95 `254ms`。该数据不属于下一轮效果。
- 2026-10-10 生产招聘定时检查只读诊断：Celery 全局硬/软时限未配置；最新 18:00 批次完整处理 129 个来源，0 个未执行。35 个来源失败中 34 个为浏览器适配器不可用/响应校验失败，仅 1 个为单请求超时；近 30 天来源时限错误仅 1 条。另有 2026-09-20 单次 TaskRun 租约最终失败记录，作为独立异常保留，不解释当前重复失败模式。
- 进一步核验确认浏览器服务实际可运行，但 Worker 容器的 bind mount 与宿主当前 `/run/kaj-opportunity-browser` 是不同目录 inode；浏览器 systemd 服务于 2026-09-26 启动，Worker 容器于 2026-09-20 创建。持续的 `adapter_response_invalid` 分布于 Hotjob、Dahua、Getui、Meituan、Beisen，实时响应体未持久化。
- 2026-10-10 Labs 已通过有界 SafeHttpClient/robots 直连验证 Dahua、Beisen、Getui、Hotjob、Meituan 当前来源响应，并修复四种 adapter 的契约差异；聚焦回归 `35 passed`。没有运行生产采集或写入数据库。
- 2026-10-11 生产只读读回：35 条启用招聘来源为 `STALE`，26 条最后错误为浏览器 socket 不可用、8 条为响应契约错误、1 条为请求超时；没有活动来源检查运行。当前生产 Worker 环境变量指向的 socket 在容器内不存在，宿主浏览器服务为 active。
- 2026-10-11 候选验证：答题回归 `15 passed`、适配器/Worker/Caddy 回归 `36 passed`、维护/增量镜像契约 `2 passed`；Labs 已应用 `learning.0015`，数据库 `mode` 默认值读回 `'EXAM'`。生产变更仍未开始。
