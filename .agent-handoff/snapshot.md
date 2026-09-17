# Handoff Snapshot

## Current State

- Last updated: 2026-09-16
- Last agent: Codex
- Workspace root: `/home/code/personal-blog`
- Current objective: 保持 Labs-first 开发与交付流程，并在处理主工作区漂移后继续推进正式环境外部性能测试和下一轮迭代。
- Current status: in progress
- Immediate next actions:
  - 冻结主工作区现有改动，逐文件判定迁移到 Labs、已被替代或保留的内容；禁止直接 reset/pull 覆盖。
  - 在外部机器执行 P0 正式环境低风险只读测试，并把真实结果追加到正式环境性能测试执行日志。
  - 进入知识文档审核前，对 `knowledge-review.v1` 执行当前 Endpoint 的严格 schema capability 检查。
- Active files:
  - `AGENT_HANDOFF.md`
  - `.agent-handoff/snapshot.md`
  - `apps/agents/services/invocations.py`
  - `apps/learning/services/review_runtime.py`
  - `docs/operations/performance-testing/`
- Blockers: 主工作区存在未分类的 69 个已修改文件和 12 个未跟踪路径，不能安全同步到远端最新 `main`。
- Open questions:
  - UNKNOWN: handoff 文件是否在用户下一次明确 Git 交付时一并提交；当前未授权提交这些文件。
  - UNKNOWN: 主工作区独有改动中哪些仍是用户有效意图，哪些已经被 Labs/远端实现替代。
  - UNKNOWN: 外部 P0 测试机能否取得正式环境 PostgreSQL/Redis/TaskRun 的只读指标快照。

## Recovery Summary

- 远端 `origin/main` 与 Labs 快照均为 `0b700d4`；该提交只包含性能测试任务/执行日志文档，已从 Labs 提交并 fast-forward 推送。
- 主工作区 `main` 仍停留在 `e5adc20`，落后远端 21 个提交且工作区脏；不要用 reset、checkout 覆盖、stash 制造假干净状态。
- Labs 的 `kaj-labs.service`、worker、beat 均为 `inactive/dead`；正式 Docker Compose 仍运行 `kaj-blog-web:451bc9f`。
- 最近生产审核失败的直接事实是 `knowledge-review.v1` 没有匹配当前 Endpoint row version 的 `SCHEMA_SUPPORTED` 检查；先完成严格检查再重试。
