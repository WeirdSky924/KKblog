# 应用服务契约

应用服务是所有状态变化的唯一公共入口。Django View、管理页面、HTMX、Celery 和管理命令都调用同一服务，不直接复制授权或事务。

## 统一命令形状

```python
@dataclass(frozen=True)
class CommandContext:
    actor_id: UUID | None
    request_id: str
    trace_code: str
    client_ip: str | None
    now: datetime

@dataclass(frozen=True)
class CommandResult[T]:
    value: T
    emitted_event_ids: tuple[str, ...]
```

命令 DTO 只包含已解析的标量、稳定 ID 和版本令牌；不得传 HttpRequest、表单、ORM QuerySet 或上传文件句柄进入领域服务。文件先由媒体入口转换为受控 staged asset ID。

每个命令固定执行：输入不变量 → IP/身份/角色策略 → 对象策略 → 容量/限流门禁 → 数据库事务/锁 → 审计与 outbox → 返回结果。提交后消费者再处理通知、缓存、邮件和文件。

## accounts 公开服务

| 服务 | 关键输入 | 结果 | 典型错误 |
| --- | --- | --- | --- |
| `request_verification_code` | purpose, email, invite?, IP | challenge metadata | 注册关闭、邀请码无效、发送过频、IP 受限 |
| `register_account` | email, code, password, invite? | account + session | 验证码错误、邮箱冲突、邀请码已用 |
| `authenticate_password` | email, password, remember | session | 凭证错误、临时限制、账号禁用 |
| `authenticate_code` | email, code, remember | session | 同上 |
| `reset_password` | email, code, new password | 完成 | 验证失败、限制中；成功撤销所有会话 |
| `change_password` | actor, current, new | rotated session | 当前密码错误 |
| `change_email` | actor, new email, code | account | 验证/唯一冲突 |
| `change_profile` | nickname/theme/avatar | account | 昵称规则/冷却/冲突、媒体归属 |
| `revoke_session(s)` | actor, target/all | count | 目标不属于本人 |
| `set_author_role` | admin, account, enabled | role state | 唯一管理员保护、账号不存在 |
| `set_account_enabled` | admin, account, enabled | account | 管理员保护 |
| `delete_account` | admin, account, author disposition | deletion record | 未处理作者文章、管理员自删 |
| `block_ip` / `unblock_ip` | admin, IP, note | block | 格式/重复状态 |

## content 公开服务

| 服务 | 关键输入 | 结果 | 典型错误 |
| --- | --- | --- | --- |
| `create_article` | author, format, initial state | article + revision | 非作者、磁盘门禁 |
| `save_revision` | article, base revision, row version, snapshot | new revision | 冲突、正文超限、媒体/标签非法 |
| `prepare_publication` | article, revision | sanitized review DTO | 非本人、遮罩/修订非法 |
| `publish_article` | article, revision, expected row version | published article | 未预览令牌、分区缺失、冲突 |
| `schedule_article` | article, revision, time | schedule | 时间无效、冲突 |
| `cancel_schedule` | article | draft | 非本人/已执行 |
| `change_visibility` | article, visibility | new published revision | 非已发布、管理员代改 |
| `prepare_restore_revision` | article, source revision | review DTO | 历史不属于文章 |
| `restore_revision` | article, source, expected version | new working revision | 冲突 |
| `soft_delete_article` | actor, article, reason? | purge deadline | 策略禁止 |
| `restore_article` | actor, article | restored state | 过期/遮罩冲突 |
| `hide_article` / `unhide_article` | admin, article, reason? | moderation case | 仅发布可隐藏 |
| `review_article_appeal` | admin, appeal, outcome | final case | 非法状态 |
| `manage_section` / `manage_tag` | admin command | object/result | 唯一/关联冲突 |

读取契约由 `content.queries` 暴露：`article_for_reader`、`article_for_author`、`article_for_admin`、`visible_article_page`、`author_article_page`。每个查询显式接收 actor，不提供“无权限过滤的通用 all_articles”。

## media 公开服务

| 服务 | 责任 |
| --- | --- |
| `stage_upload` | 流式限制、真实格式解码、元数据清理、生成受控 storage key |
| `bind_assets` | 校验 owner、purpose、target、数量并创建引用 |
| `replace_bindings` | 对比新旧集合，激活新增、把无引用旧资产标待删 |
| `authorize_asset_read` | 根据用途、目标可见性和 actor 产生内部发送授权 |
| `delete_unbound_assets` | 幂等删除数据库标记与磁盘文件 |

媒体服务不判断文章业务可见性细节，而调用目标领域提供的 `MediaAccessDecision` 端口；目标领域也不拼路径或删文件。

## comments 与 moderation 公开服务

| 服务 | 责任 |
| --- | --- |
| `create_top_level_comment` | 检查线程设置、冷却、100 字、最多三图，写缓冲评论 |
| `reply_to_comment` | 要求登录、禁止回复删除节点、计算深度/计数 |
| `publish_due_comments` | 条件批量公开到期缓冲评论 |
| `delete_own_comment` | 登录作者删除自己评论 |
| `delete_comment_as_owner` | 文章作者管理自己文章；留言板管理员 |
| `delete_comment_as_admin` | 任意评论、可选原因、终局审计 |
| `create_report` | 唯一举报、标签/描述/证据校验 |
| `review_report` | 管理员初审与评论占位/通知 |
| `appeal_report` | 结果对应一方的一次申诉 |
| `review_report_appeal` | 管理员终局复审 |
| `appeal_article_action` | 作者对隐藏/删除一次申诉 |
| `review_article_appeal` | 管理员终局并委托 content 恢复 |

## notifications 与 operations 公开服务

| 服务 | 责任 |
| --- | --- |
| `deliver_event_notification` | 按类型模板、接收者和 dedupe key 建通知/回执 |
| `broadcast_notification` | 唯一管理员向所有注册用户群发 |
| `mark_read` / `mark_all_read` | 只改本人回执，不删除通知 |
| `hide/restore/delete_broadcast` | 全局可见性变化和永久审计 |
| `record_audit_entry` | 只接受 schema 校验后的 safe before/after |
| `record_runtime_error` | 脱敏、生成/关联 trace code、聚合同指纹 |
| `evaluate_capacity` | 计算 NORMAL/WARN/NO_IMAGE/READ_ONLY 门禁 |
| `record_task_attempt` | 任务状态、尝试数、最终失败 |

审计写入失败时，管理员状态改变命令必须整体失败；运行错误记录失败不能向用户暴露原异常，但必须写容器 stderr 作为最后诊断通道。

## exchange 公开服务

| 服务 | 责任 |
| --- | --- |
| `create_import_preview` | 安全解包、解析、冲突分类，不写文章 |
| `update_import_decision` | 保存逐项选择和映射，递增 preview version |
| `confirm_import` | 冻结预览，逐项调用内容服务，保留部分成功 |
| `request_export` | 校验管理员、选择范围和全局并发，创建任务 |
| `cancel_export` | 条件取消、删除未完成包、永久审计 |
| `authorize_export_download` | 管理员、完成、未过期三重检查 |

## 返回与错误规则

- 表单可修复错误：稳定业务错误码 + 字段映射，例如 `account.email_taken`。
- 权限错误：对私人/草稿读取返回 `content.not_found`，避免对象存在性泄露；管理写入可返回 `access.denied`。
- 冲突：返回 409 语义的 `content.edit_conflict` 和安全版本列表。
- 限流：返回明确用户文案与可重试时间，但不暴露内部 Redis 键。
- 未预期错误：用户只见通用提示与 trace code；完整脱敏诊断进入 RuntimeError。

服务不能返回“已成功排队”并在 UI 显示业务完成。异步动作返回 `JobAccepted(job_id)`，界面显示进行中；只有 Job `COMPLETED` 才显示完成。
