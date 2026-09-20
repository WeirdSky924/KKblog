# Task Backlog

- [x] `B-001` 历史主工作区漂移已不再存在于当前读回：`main` 与 `origin/main` 同步在 `a06a94f`；本任务及原有 P0 文档改动仍按未提交工作区改动保留。
- [ ] `B-002` 在外部机器按 P0 文档执行正式环境低风险只读测试，填写 `/home/code/.codex-worktrees/personal-blog/production-688c25b/docs/operations/performance-testing/p0-production-canary.execution.md` 对应结果。
- [ ] `B-003` 对生产 Endpoint 执行 `knowledge-review.v1` 严格 capability check，确认 `SUCCEEDED + SCHEMA_SUPPORTED + 当前 row_version` 后重试知识文档审核。
- [ ] `B-004` 清点 Labs 中未提交的文章解释测试文件和当前快照，决定纳入下一次 Labs 任务还是清理；不得混入性能文档提交。
- [x] `B-005` 用户明确 Git 交付后，从 Labs 任务分支提交 handoff 文件；已完成推送、fast-forward 集成和临时分支清理。
- [ ] `B-006` 更新或审查仍写着旧远端提交号的历史实施清单，避免把文档旧事实当作当前 Git 真值；先记录影响再决定是否修订。
- [ ] `B-007` Labs 服务恢复为 `active/running` 后，读回本任务同步的岗位性能代码和代表性岗位页面；不得自行重启服务。

## Backlog Guidelines

- Keep tasks actionable.
- Remove completed or obsolete items.
- Link items to risks, decisions, or files when useful.
