# ADR-004：Redis 可丢失，Outbox 保证副作用

状态：Accepted

## Context

验证码、限流、冷却和页面缓存适合 Redis；通知、定时发布、清理、审计不能因 Redis/Celery 重启丢失。数据库提交与直接发送任务之间存在崩溃窗口。

## Decision

Redis 只保存明确允许丢失的短期状态。业务到期时间、Job 和事实状态保存在 PostgreSQL。跨领域副作用与业务事务一起写 Outbox，再由至少一次投递的消费者处理；消费者按事件 ID 去重。

Celery Beat 扫描数据库的到期事实，不依赖长期 ETA 消息。全局并发正确性使用 PostgreSQL 约束/租约，不只依赖 Redis 锁。

## Consequences

- Redis 清空会使验证码/冷却提前失效，但不会发布错误内容或丢业务数据。
- 事件可能重复，所有消费者必须幂等。
- 多出 Outbox 发布器、消费记录和积压监控。
- 业务事务不等待邮件/文件系统，失败可追踪重试。

## Rejected alternatives

- 事务中直接 `delay()`：数据库回滚或进程崩溃会产生消息与事实不一致。
- Redis 持久锁作为唯一裁决：重启/过期可能允许重复全局任务。

## Revisit when

Outbox 吞吐成为实测瓶颈，或引入具有等价事务投递能力的基础设施时。
