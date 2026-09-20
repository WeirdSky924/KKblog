# Risks, Blockers, And Unknowns

## Current Blockers

- Labs 服务 `/home/code/.codex-worktrees/personal-blog/labs-test-environment` 当前为 `inactive/dead`，`https://labs.kajspace.cn/health/live` 返回 `502`；已完成文件虽已定向同步，但无法做服务页面读回，不能自行启动或重启。
- 外部正式 P0 复测尚未执行；本地隔离回归不能替代公网并发 1/2/5、Nginx timing 和生产数据库/队列快照。

## Current Risks

- Labs 和正式快照均为 detached HEAD；Labs 服务已停，且 Labs 还有 handoff/文章解释测试等未提交改动；后续 Git 交付必须从已核验远端 `main` 建任务分支。
- 主工作区当前与 `origin/main` 同步在 `42adeb4`；本轮正式发布记录和原有 P0 文档仍未提交，后续 Git 交付不得混入无关改动。
- 正式项目快照 `/home/code/.codex-worktrees/personal-blog/production-688c25b` 仍有性能文档未提交改动；运行目录 `/home/code/personal-blog/var/production` 含生产凭据、数据库、媒体和备份，禁止当作源码同步目标。
- P0 性能测试尚未重新执行；正式环境已完成运行时增量切换，但当前只有代码级证据、发布 smoke 和历史部分失败结果，不能把它们当作优化后的 P0 通过证据。
- 生产知识审核 profile 当前没有匹配 Endpoint row version 的 `knowledge-review.v1` 严格能力检查；重复启动审核会继续确定性失败，必须先检查。
- `docs/planning/implementation-todolist.md` 等历史文档含旧远端提交号/部署口径；Git、服务和数据库读回优先级高于历史文案。

## Unknowns / Confirmations Needed

- UNKNOWN: 当前工作区未跟踪 P0 文档是否应在后续独立交付；需按用户授权与性能测试流程决定，不能与岗位优化代码自动混交。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun 和 Outbox 的只读快照。
- UNKNOWN: 是否需要同时维护 Claude Code 的 `.claude/CLAUDE.md`；当前只生成 Codex `AGENTS.md` handoff protocol。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
