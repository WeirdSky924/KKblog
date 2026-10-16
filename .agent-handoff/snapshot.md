# Handoff Snapshot

## Current State

- Last updated: 2026-10-17
- Last agent: Codex
- Workspace root: `/home/code/.codex-worktrees/personal-blog/labs-test-environment`
- Current objective: 完成本轮 Labs 代码交付、正式增量更新、状态修正和 Labs 测试服务收尾。
- Current status: 源码提交 `2c78cddf92acf6adf7f33f3c57affa32cada522e` 已推送并 fast-forward 到 `origin/main`；生产已应用四项 migration、切换候选镜像并通过公网读回；终态招聘孤儿来源已由恢复 owner 收敛；Labs Web/Worker/Beat/Outbox 已停止。
- Immediate next actions:
  - 提交并推送本轮执行记录与 handoff 收口文档，随后删除已集成的远端任务分支；保留 Labs worktree 中未提交测试文件，按项目规则不进入交付提交。
  - 外部 P0 只读复测、知识审核 capability check、题库 `security_review` 可见性和 Labs Outbox 历史失败仍按独立 backlog 处理。
- Active files:
  - `docs/releases/2026-10-17-production-increment/announcement.md`
  - `docs/releases/2026-10-17-production-increment/deployment-record.md`
  - `.agent-handoff/snapshot.md`
  - `.agent-handoff/validation.md`
- Blockers: 本轮交付无发布阻塞；未完成项是外部 P0、认证态功能验收、知识审核 capability check、题库公开状态和 Labs Outbox 独立调查。
- Open questions:
  - UNKNOWN: 是否以及何时提供可授权管理员/普通用户 session，完成留言板、作者申请、通知中心和密码重置真实认证流。
  - UNKNOWN: 外部 P0 测试机是否可取得所需只读指标和快照。

## Recovery Summary

- Git：任务提交 `2c78cdd`、任务分支和 `origin/main` 已读回一致；发布记录后续文档提交尚待本次收口。
- Production：旧基线 `d06af75a9c31` 已切换为 `kaj-blog-web:2c78cddf92ac`；Web/Worker healthy、Beat running、restart count 0；公网 live/ready/home 为 `200`，公开岗位入口为 `302`。
- Production schema：`accounts.0010`、`accounts.0011`、`comments.0006`、`comments.0007` 已应用，候选无待执行 migration。
- State repair：此前 `PARTIAL` 父运行下的一条 `RUNNING` 来源明细已变为 `FAILED/opportunities.check_run_orphaned.v1`，父汇总失败数 `30→31`；当前活动运行、活动来源明细和机会相关 running TaskRun 均为 `0`。未调用 Provider/AGENT/招聘采集。
- Labs：`kaj-labs.service`、Worker、Beat 为 `inactive/dead`；Beat/Outbox service 保持 `failed` 但 `MainPID=0`；Outbox timer `inactive/dead`；无 Labs worktree 残留进程，公网 health 在关闭后为 `502`。生产机会浏览器服务未停止。
- Test-only files remain uncommitted in the Labs worktree: modified `apps/accounts/tests/test_acc004.py` and four new feature test files. They are preserved and excluded from Git delivery by project rule.
