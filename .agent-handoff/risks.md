# Risks, Blockers, And Unknowns

## Current Blockers

- 本轮正式更新已完成；没有待处理的生产发布阻塞。
- Labs Web/Worker/Beat 已停止；Outbox service 仍保留历史 `failed` 状态、timer 为 `inactive/dead`，未通过 reset 或 SQL 清除诊断事实。
- 认证态留言板、作者权限申请、通知中心和管理员密码重置真实浏览器流仍缺少获授权 session；不创建或借用账户，不发送真实邮件。

## Current Risks

- 正式生产已经向前应用四项 migration；应用回退只允许恢复旧镜像，不反向迁移。数据库和媒体备份保存在 `/home/code/personal-blog/var/production/backups/`，不得进入 Git 或宽泛清理。
- 候选 Web 首次 readiness 探针受主机换页超时，但随后 Web/Worker health、Beat、loopback/public live/ready 均恢复正常，restart count 为 0；该主机资源约束仍要求重型操作串行。
- 生产岗位来源的 `DEGRADED/STALE` 事实没有被改写；本轮只修正了已证实的终态父运行孤儿来源明细。Provider、AGENT 和招聘采集均未调用。
- 外部 P0 公网并发复测尚未执行；本轮生产 health、页面和数据库读回不能替代 P0 低风险性能证据。
- Labs 测试专用容器已停止并清理；数据卷、媒体、备份和凭据均保留。测试文件未进入交付提交。

## Unknowns / Confirmations Needed

- UNKNOWN: 是否授权解除指定题库卷的 `security_review` 管理隐藏；必须通过 `apps.learning` 管理 service 并留下审计。
- UNKNOWN: 是否提供可授权管理员/普通用户浏览器状态和隔离 Mailpit，以完成认证态功能验收。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun、Outbox 和 Nginx timing 的只读快照。
- UNKNOWN: Labs Outbox 两条历史 `task.final_failed.v1` transport failure 的独立根因；不得直接改写、删除或清零事件。

## Risk Guidelines

- 继续维护真实失败状态，不用“成功”覆盖未经证据确认的结果。
- 生产数据写入必须复用领域 service；不得直接 SQL 改写业务状态。
- 下一代理先读取本文件和 `snapshot.md`，再以 `docs/releases/2026-10-17-production-increment/deployment-record.md` 为本轮生产事实来源。
