# 架构决策记录索引

ADR 记录“为什么这样设计”，不是重复最终目录。状态只有 `Proposed`、`Accepted`、`Superseded`、`Rejected`。已接受 ADR 不原地改写结论；方向改变时新建 ADR，并在旧文档标记被谁取代。

| ADR | 决策 | 状态 |
| --- | --- | --- |
| ADR-001 | 采用领域模块化单体 | Accepted |
| ADR-002 | PostgreSQL 正文与不可变修订 | Accepted |
| ADR-003 | Django Templates + HTMX/Alpine | Accepted |
| ADR-004 | Redis 可丢失、Outbox 保证副作用 | Accepted |
| ADR-005 | 唯一管理员的内容查看例外 | Accepted |
| ADR-006 | 本地文件系统媒体与统一媒体服务 | Accepted |

阅读 ADR 时先看 Context 中的约束，再检查 Decision 是否真的解决约束，最后审视 Consequences 中主动接受的代价。成熟架构不是没有代价，而是代价被看见、被限定、可在条件变化时重新评估。
