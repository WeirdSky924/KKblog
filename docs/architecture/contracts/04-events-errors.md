# 领域事件、Outbox、错误与审计契约

## 事件信封

所有跨领域副作用使用同一事务 Outbox。业务事务写聚合与事件记录；独立发布器在提交后投递。消费者以 `event_id + consumer_name` 去重。

```json
{
  "event_id": "01J...",
  "event_type": "article.published.v1",
  "occurred_at": "UTC ISO-8601",
  "actor_id": "uuid-or-null",
  "aggregate_type": "article",
  "aggregate_id": "ulid",
  "trace_code": "KJ-...",
  "payload": {}
}
```

payload 由每个版本的 schema 校验，不放正文、密码、验证码、令牌、原始 IP、邮件内容或磁盘路径。事件只能描述已经发生的事实，不能命名为模糊的 `DoSomething`。

## 事件注册表

| 事件 | 生产者 | 消费者/副作用 |
| --- | --- | --- |
| `account.registered.v1` | accounts | 初始化通知偏好（首版无欢迎邮件） |
| `account.author_role_changed.v1` | accounts | 站内通知、管理员审计 |
| `account.disabled.v1` | accounts | content 隐藏投影、取消定时、审计 |
| `account.enabled.v1` | accounts | content 恢复禁用遮罩、审计 |
| `account.deleted.v1` | accounts | comments 匿名化、moderation 结案、media 清理 |
| `article.published.v1` | content | discovery 缓存/索引失效、审计 |
| `article.visibility_changed.v1` | content | 搜索/sitemap/缓存立即失效 |
| `article.author_mask_changed.v1` | content account-status consumer | discovery 按作者失效缓存/索引，media 与 reader query 直接读取遮罩投影 |
| `article.admin_viewed.v1` | content policy | notifications 按文章/日聚合 |
| `article.hidden/restored/deleted.v1` | content/moderation | 作者通知、缓存失效、审计 |
| `article.purge_requested.v1` | content | comments/media 清理，审计保留 |
| `tag.reviewed.v1` | content | 作者通知、关联移除/激活 |
| `comment.created.v1` | comments | 缓冲任务可观测记录 |
| `comment.deep_thread.v1` | comments | 作者/留言板管理员一次通知 |
| `comment.admin_deleted.v1` | comments | 相关注册用户通知、审计 |
| `report.reviewed/finalized.v1/v2` | moderation | 隐私安全的双方通知；v2 携带举报编号、目标评论编号、原因、脱敏补充说明与完整裁决结果 |
| `export.completed/failed.v1` | exchange | 管理员通知 |
| `export.includes_foreign_content.v1` | exchange | 受影响作者按日聚合通知 |
| `task.final_failed.v1` | operations | 管理员站内+邮件告警 |
| `capacity.threshold_changed.v1` | operations | 站内告警/解除运行门禁 |
| `service.health_changed.v1` | operations | 管理员站内健康告警/恢复状态；邮件仅故障 |

需要“立即一致”的动作不能等待事件：禁用账户撤销会话、发布指针更新、管理员隐藏查询遮罩、删除占位、唯一约束都在原事务完成。事件负责可重试的跨域投影与通知。

## Outbox 状态

`PENDING -> PUBLISHED`；发布失败保留 PENDING 并重试。消费者表记录 `event_id/consumer/status/processed_at`。处理逻辑必须满足至少一次投递：重复消息读回已有结果，不重复通知、不重复删除、不重复加浏览量。

Outbox 长期不是业务审计。成功消息可按运维保留策略归档/清理；审计和任务记录另有永久表。

## 错误分类

| 类别 | HTTP 语义 | 用户表现 | 示例 |
| --- | --- | --- | --- |
| Validation | 422 | 字段旁明确修正 | `account.password_weak` |
| Authentication | 401/登录页 | 登录或会话过期 | `access.session_expired` |
| Authorization | 403 或隐私 404 | 无权/404 | `access.denied` |
| NotFound | 404 | 统一 404 | `content.not_found` |
| Conflict | 409 | 冲突选择/刷新 | `content.edit_conflict` |
| RateLimit | 429 | 明确等待或日刷新 | `account.code_rate_limited` |
| Capacity | 503 | 暂停创建，既有内容可读 | `operations.creation_paused` |
| External | 502/任务失败 | 进行中失败或稍后再试 | `mail.delivery_failed` |
| Unexpected | 500 | 通用提示 + trace code | `internal.unexpected` |

业务错误是稳定类，不用异常消息作为 UI 文案。错误码和中文文案分离，为未来本地化预留。普通用户不看到 endpoint、SQL、堆栈、模型名或内部枚举。

## Trace code

每个入口建立 request ID；发生用户可见错误时生成短 trace code，例如 `KJ-20260719-7F3K9M`。同一调用链的 View、service、outbox、task 和 RuntimeError 都携带它。编码本身不可包含 user ID、IP 或时间以外的敏感信息。

管理员按 trace code 直接搜索错误日志。没有错误记录时也要诚实显示“未找到对应记录”，不能让错误码页面伪装诊断已完成。

## 脱敏注册表

统一 `RedactionPolicy` 按字段名和数据类型处理：

- 完全删除：password、code、token、cookie、authorization、`.env` 值、邮件正文。
- 摘要/哈希：正文、评论正文、上传文件、邀请码原码。
- 默认掩码：邮箱、IP、路径、User-Agent；管理员详情只有明确权限时读完整 IP。
- 永不记录：数据库连接串、私钥、第三方密钥、原始会话令牌。

脱敏在日志结构化写入前执行，不依赖前端隐藏。单元测试使用故意含秘密的异常验证所有 sink。

## 审计 schema

每个管理员写命令声明 `AuditSchema`：动作名、目标、允许记录的 before/after 字段、摘要生成器。未知字段默认拒绝写入，而不是默认全量序列化 ORM。

| 对象 | 记录 |
| --- | --- |
| 账户/角色 | 状态、角色集合、目标 user ID；邮箱仅掩码 |
| 文章 | 状态、修订 ID、可见性、管理案件 ID；不记正文 |
| 媒体 | asset ID、用途、状态、大小；不记磁盘绝对路径 |
| 评论/举报 | 状态、案件 ID、原因枚举；评论正文不进入事件，举报 v2 只携带脱敏补充说明 |
| 邀请码 | invite ID、状态、有效期、尾号；不记原码 |
| 设置/导航 | 允许的配置前后值；秘密设置根本不进网页模型 |
| 备份/导出 | Job ID、范围、状态、归档大小；不记公开下载 URL |

审计动作与业务写入同事务。审计失败意味着管理员命令失败；只读页面访问不审计，但管理员查看他人内容按通知事件单独追踪。

## 通知模板安全

通知类型映射到服务器模板和 payload schema。链接目标由类型与稳定 ID 构建，payload 不允许提交任意 HTML/URL。举报结果模板永不包含 reporter ID、证据路径或评论正文；v2 的补充说明在事件生成时将危险标记转为不可执行的全角文本，详情按纯文本分行展示；删除原因在渲染前按纯文本转义。
