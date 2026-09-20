# Handoff Snapshot

## Current State

- Last updated: 2026-09-20
- Last agent: Codex
- Workspace root: `/home/code/personal-blog`
- Current objective: 完成 Kajspace 公开岗位 P0 性能定位与最小优化，保留禁止生产副作用边界，并为外部 P0 复测准备可核验的 SQL/模板/传输证据。
- Current status: in progress
- Immediate next actions:
  - 在 Labs 服务获授权恢复为 `active/running` 后，对已同步的岗位性能改动做 health/page readback；当前不得自动启动或重启。
  - 在外部测试机按 P0 顺序重新执行正式环境低风险只读复测；并发 2/5 结果仍未由本任务产生。
  - 保持 `knowledge-review.v1` capability check 与当前 Endpoint row version 的独立待办，不与岗位性能任务混合。
- Active files:
  - `AGENT_HANDOFF.md`
  - `.agent-handoff/snapshot.md`
  - `apps/opportunities/views.py`
  - `apps/opportunities/queries/public.py`
  - `docs/operations/performance-testing/`
- Blockers: Labs 服务当前为 `inactive/dead`，`https://labs.kajspace.cn/health/live` 返回 `502`；不能在未获授权时自行启动/重启。外部正式 P0 复测尚未执行。
- Open questions:
  - UNKNOWN: 本次优化在正式环境并发 1/2/5 下的最新 p95 与数据库/运维快照，需外部测试机和运维只读证据。
  - UNKNOWN: 外部 P0 测试机能否取得正式环境 PostgreSQL/Redis/TaskRun 的只读指标快照。

## Recovery Summary

- 性能测试文档和 handoff 已由 Labs 任务分支提交并 fast-forward 推送到远端 `main`；具体集成提交以当前 `git fetch`/读回为准。
- 主工作区当前已与 `origin/main` 同步在 `a06a94f`；本任务产生的岗位性能代码和原有未跟踪 P0 文档均保留为未提交工作区改动，临时回归文件已清理，未执行 reset、stash 或 Git 交付。
- Labs 的 `kaj-labs.service`、worker、beat 均为 `inactive/dead`；正式 Docker Compose 仍运行 `kaj-blog-web:451bc9f`。
- 最近生产审核失败的直接事实是 `knowledge-review.v1` 没有匹配当前 Endpoint row version 的 `SCHEMA_SUPPORTED` 检查；先完成严格检查再重试。
- 本任务定位出岗位公开页的重复筛选选项 SQL、重复来源计数和 HTMX 未使用 summary 查询；最小优化已在本地隔离 PostgreSQL 回归通过，临时回归文件已按交付规则清理。
