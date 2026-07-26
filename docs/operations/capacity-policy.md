# 容量保护门禁

`apps.operations.services.capacity` 是容量判定与同步写门禁的唯一 owner。`OBS-007` 建立纯 policy、可注入 sample source 和同步 gate；`OBS-010` 复用同一 policy，每五分钟采样媒体文件系统并把最新事实保存为 `CapacitySnapshot`，通过版本化状态事件驱动站内告警，并复用统一运维邮件窗口。

## 状态边界

门禁按 `free_bytes / total_bytes` 的精确整数比例计算，不使用浮点数：

| 可用比例 | 状态 | 文字创建 | 图片创建 | 既有读取 | 诊断写入 |
| --- | --- | --- | --- | --- | --- |
| `>= 10%` | `NORMAL` | 允许 | 允许 | 允许 | 允许 |
| `>= 5%` 且 `< 10%` | `WARN` | 允许 | 允许 | 允许 | 允许 |
| `>= 2%` 且 `< 5%` | `NO_IMAGE` | 允许 | 拒绝 | 允许 | 允许 |
| `< 2%` | `READ_ONLY` | 拒绝 | 拒绝 | 允许 | 允许 |

因此精确 `10%`、`5%` 和 `2%` 不进入更严格的“低于”状态。sample 必须包含正数总容量、范围内可用字节和 timezone-aware 观测时间。

## 消费者契约

写服务必须接收服务器端构造的 `CapacityGate`，并在每次持久化前调用：文字创建使用 `TEXT_CREATE`，任何新图片使用 `IMAGE_CREATE`。不得从请求字段、前端按钮状态、Redis 锁或客户端缓存构造容量事实。

`CapacityGate.require` 每次重新调用注入的 sample source，所以容量恢复后无需管理员确认即可解除限制。`DIAGNOSTIC_WRITE` 保留审计和运行错误所需最低写通道；既有内容读取不调用写门禁。

图片门禁返回稳定错误码 `operations.image_creation_blocked.v1` 和“暂时不支持上传图片。”；只读门禁返回 `operations.content_creation_blocked.v1`。两者均由统一错误处理中间件生成无缓存的 503 响应，不暴露磁盘路径、挂载点或字节数。

## 周期采样与告警

- 同一 UTC 五分钟窗口只建立一个 `apps.operations.check_capacity` TaskRun；重复 Worker 调度读取同一幂等终态。
- `CapacitySnapshot` 每个受控 source 只保存最新总量、可用量、状态、状态变化时间和累计样本数；相同时间/相同事实重放幂等，时间倒退或同时间冲突关闭失败。
- `NORMAL -> WARN/NO_IMAGE/READ_ONLY` 建立或更新一条活跃容量告警；持续低容量每小时最多一个邮件窗口。阈值内部升级仍写站内状态事件。
- 回到 `NORMAL` 时事务内关闭活跃告警并写恢复状态事件，写服务下一次同步采样自动恢复；不创建恢复邮件窗口，也不要求管理员确认。
- 周期事实只用于可观测读回。每次文字或图片创建仍从受信文件系统重新采样并经过同一 `CapacityPolicy`，因此 Beat 延迟、Redis 丢失或旧快照不会放宽服务端门禁。
