# Decision Log

| Date | Decision | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-09-16 | Use multi-document Agent handoff memory in the main worktree. | 当前项目跨会话、跨 Labs/正式快照、存在长期 backlog；索引与状态/风险/验证分离，恢复成本更低。 | `agent-handoff` bootstrap；`AGENT_HANDOFF.md` 与 `.agent-handoff/`。 |
| 2026-09-15 | 所有先行修改遵循 Labs-first；提交/推送从 Labs 任务分支开始，之后才同步主工作区。 | 主工作区存在历史脏改动，直接同步会覆盖未分类内容；Labs 应是测试和发布候选的事实起点。 | 用户当前工作流要求；`docs/operations/testing.md`；worktree 审计记录。 |
| 2026-09-15 | 性能测试文档由 Labs 提交并 fast-forward 到远端 `main`，提交为 `0b700d4`。 | 让外部测试机使用稳定、可追踪的 P0/P1/P2 任务与执行日志；不部署、不重启生产。 | Labs Git 读回、远端 `origin/main`、提交 `docs: 添加性能测试任务与执行记录`。 |
| 2026-09-15 | P0 先由服务器外部机器执行低风险只读基线。 | 避免本机 AI/浏览器/压测进程干扰正式服务器性能；P0 不调用 AGENT、不上传、不抓取招聘。 | `docs/operations/performance-testing/p0-production-canary.md`；用户确认。 |
| 2026-09-15 | AGENT capability check 按 Endpoint row version + schema 绑定；Endpoint 修改后必须重新严格检查。 | 文章解释、题库生成、知识审核使用不同 schema，不能用其他 schema 的成功检查授权。 | `apps/agents/services/invocations.py`、`apps/agents/services/checks.py`、生产只读状态。 |
| 2026-09-15 | 站内通知分为 Outbox 事件、Notification 本体和 NotificationReceipt 回执；Toast 不进入通知中心。 | 保证事务一致性、幂等投递、每用户已读隔离，并区分持久业务通知与临时操作反馈。 | `apps/core/events/`、`apps/notifications/`、通知模板/已读服务。 |

## Decision Guidelines

- Record durable decisions only.
- Include reason and evidence.
- Do not record guesses as decisions.
- If evidence is missing, mark it as `UNKNOWN`.
