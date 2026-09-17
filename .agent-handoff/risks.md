# Risks, Blockers, And Unknowns

## Current Blockers

- 主工作区 `/home/code/personal-blog` 的 `main` 落后 `origin/main` 23 个提交，同时有 70 个 tracked 修改和 22 个 untracked 路径（含本 handoff）；未完成分类前不能安全同步。

## Current Risks

- Labs 和正式快照均为 detached HEAD；Labs 服务已停，Labs 还有未提交的文章解释测试；后续 Git 交付必须从已核验远端 `main` 建任务分支。
- 正式项目快照 `/home/code/.codex-worktrees/personal-blog/production-688c25b` 仍有性能文档未提交改动；运行目录 `/home/code/personal-blog/var/production` 含生产凭据、数据库、媒体和备份，禁止当作源码同步目标。
- P0 性能测试尚未执行；当前只有任务定义和执行模板，不能把健康检查、容器状态或旧发布记录当作 P0 通过证据。
- 生产知识审核 profile 当前没有匹配 Endpoint row version 的 `knowledge-review.v1` 严格能力检查；重复启动审核会继续确定性失败，必须先检查。
- `docs/planning/implementation-todolist.md` 等历史文档含旧远端提交号/部署口径；Git、服务和数据库读回优先级高于历史文案。

## Unknowns / Confirmations Needed

- UNKNOWN: 主工作区原有 69 个 tracked 改动中哪些属于当前有效开发意图；需要逐文件比较 Labs/远端并结合用户确认。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun 和 Outbox 的只读快照。
- UNKNOWN: 是否需要同时维护 Claude Code 的 `.claude/CLAUDE.md`；当前只生成 Codex `AGENTS.md` handoff protocol。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
