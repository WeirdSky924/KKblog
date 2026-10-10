# Handoff Snapshot

## Current State

- Last updated: 2026-10-11
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 完成本轮 Labs 代码、文档的提交推送，增量更新正式环境、前向应用答题迁移、按真实检查结果修正 35 条岗位来源状态，并在结束时关闭 Labs 测试服务。
- Current status: 答题、导航、适配器和增量镜像代码已提交并 fast-forward 到远端；正在收口维护入口文档。正式 Nginx 维护标记已开启，公网返回 `503`；数据库/媒体/Compose 备份已校验。Caddy 已恢复 `2cbead0`，Web/Worker/Beat 仍为旧镜像；生产尚未执行 migration 或来源状态修复。Labs 已应用 `learning.0015` 并读回数据库级 `EXAM` 默认值。
- Immediate next actions:
  - 完成 Nginx 维护入口收口并推送 fast-forward；重新构建最终 revision 的 Web 候选，候选 checks 和 migration plan 与最终 revision 对齐。
  - 保持 `/run/kaj-production-maintenance.enabled`，停 Beat/Worker，前向执行 `learning.0014`/`0015`，切换 Web、`collectstatic`、Worker、Beat。
  - Worker socket 健康后逐条重查固定 35 条来源，读回终态；然后移除 Nginx 标记并验证公网和关键页面。
  - 最后关闭 Labs Web 与 P12 PostgreSQL/Redis/Mailpit 测试服务。
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
- Blockers: 没有授权阻塞。Nginx 维护标记已开启；需及时完成前向 migration、服务切换和定向来源检查后恢复公网访问。
- Open questions:
  - 无当前发布范围内的待确认项。

## Recovery Summary

- 最新核验远端默认分支为 `fde8a60`；当前活动 Labs 分支为 `codex/nginx-maintenance-gate`。正式 Web/Worker/Beat 容器仍为 `42adeb4`；生产 Caddy 已恢复 `2cbead0`。
- 旧 Labs 工作树完整保留在 `labs-test-environment-archive-20261009`（detached `a06a94f`），其脏改动未迁入新分支；旧 `codex/labs-next-iteration` 分支仍保留。
- 正式公告与本轮增量记录分别以 `docs/releases/2026-09-20-production-increment/` 和 `docs/releases/2026-10-09-next-iteration/announcement.md` 为准。
- 2026-10-09 生产只读指标快照截止 `03:20 UTC`：9 个 ACTIVE/有行为账户、159 篇文章、301 条修订、4 个 APPROVED 文档、4 套 PUBLISHED 题库（公开最新版 999 题）；TaskRun 1,737,523 条，成功率 `99.9930%`，重试率 `0.1112%`，P95 `254ms`。该数据不属于下一轮效果。
- 2026-10-10 生产招聘定时检查只读诊断：Celery 全局硬/软时限未配置；最新 18:00 批次完整处理 129 个来源，0 个未执行。35 个来源失败中 34 个为浏览器适配器不可用/响应校验失败，仅 1 个为单请求超时；近 30 天来源时限错误仅 1 条。另有 2026-09-20 单次 TaskRun 租约最终失败记录，作为独立异常保留，不解释当前重复失败模式。
- 进一步核验确认浏览器服务实际可运行，但 Worker 容器的 bind mount 与宿主当前 `/run/kaj-opportunity-browser` 是不同目录 inode；浏览器 systemd 服务于 2026-09-26 启动，Worker 容器于 2026-09-20 创建。持续的 `adapter_response_invalid` 分布于 Hotjob、Dahua、Getui、Meituan、Beisen，实时响应体未持久化。
- 2026-10-10 Labs 已通过有界 SafeHttpClient/robots 直连验证 Dahua、Beisen、Getui、Hotjob、Meituan 当前来源响应，并修复四种 adapter 的契约差异；聚焦回归 `35 passed`。没有运行生产采集或写入数据库。
- 2026-10-11 生产只读读回：35 条启用招聘来源为 `STALE`，26 条最后错误为浏览器 socket 不可用、8 条为响应契约错误、1 条为请求超时；没有活动来源检查运行。当前生产 Worker 环境变量指向的 socket 在容器内不存在，宿主浏览器服务为 active。
- 2026-10-11 生产执行中：备份已生成并校验；Nginx 维护标记的公网 `503` 和 Web loopback live/ready `200` 已读回。生产 migration 和来源重查尚未执行。
