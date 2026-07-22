# 容量保护门禁

`apps.operations.services.capacity` 是容量状态与同步写门禁的唯一 owner。当前阶段只提供纯 policy、可注入 sample source、同步 gate 和 health snapshot adapter；不读取真实磁盘，不保存样本，不调度检查，也不发送通知或邮件。周期采样、告警和恢复事件属于 `OBS-010`。

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
