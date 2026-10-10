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
| `request_verification_code` | purpose, email, invite?, IP | challenge metadata + multipart 邮件 | 注册关闭、邀请码无效、发送过频、IP 受限、邮件发送失败 |
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

验证码邮件由 accounts 在发码事务外沿既有 mail adapter 发送：主题和发件人显示名读取当前站名，正文同时提供纯文本与经过白名单校验的 HTML。navigation 只提供站名与可空模板配置，不接触收件人、验证码或 SMTP 凭据；发送失败必须回滚本次 challenge 与限流预留，不能显示假成功。

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

## discovery 公开服务

| 服务 | 责任 |
| --- | --- |
| `set_article_like` | 登录账户对可读文章幂等点赞/取消，维持 `(account, article)` 唯一 |
| `article_like_counts` | 按文章 ID 批量聚合点赞数，未迁移窗口安全降级为零 |

## comments 与 moderation 公开服务

| 服务 | 责任 |
| --- | --- |
| `create_top_level_comment` | 检查线程设置、冷却、100 字、最多三图，写缓冲评论 |
| `reply_to_comment` | 要求登录、禁止回复删除节点、计算深度/计数 |
| `publish_due_comments` | 条件批量公开到期缓冲评论 |
| `delete_own_comment` | 登录作者删除自己评论 |
| `delete_comment_as_owner` | 文章作者管理自己文章；留言板管理员 |
| `delete_comment_as_admin` | 任意评论、可选原因、终局审计 |
| `set_article_comment_pin` | 文章作者/管理员置顶或取消公开顶层评论；每文章至多一条 |
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

## opportunities 公开服务与查询

| 服务/查询 | 责任 |
| --- | --- |
| `create_source` / `activate_source_and_request_check` | 唯一管理员创建停用来源草稿；启用与首次检查运行原子创建，来源首次完整检查成功前不公开 |
| `request_source_check` / `request_full_check` | 唯一管理员请求单来源或全量检查；复用当前兼容运行，拒绝插队或并发第二个重型运行 |
| `request_check_cancellation` | 唯一管理员请求安全取消全量运行；当前来源原子步骤结束后停止，保留已提交结果 |
| `dispatch_pending_check_runs` | 有界补偿事务提交后首次 broker 派发失败的 `PENDING` 运行；实际执行继续由 TaskRun 幂等键裁决 |
| `replace_source_filter_options` | 以全站规范身份和来源观测更新城市、类别、届别集合；失效值保留历史 |
| `create_opportunity` | 唯一管理员新建待确认公开岗位，校验来源、HTTPS、allowlist 和三类多值筛选，并原子创建审核项/审计 |
| `update_source` / `activate_source` / `disable_source` | 唯一管理员维护来源和 allowlist；启停保持岗位之前的发布事实，所有变化写审计 |
| `update_opportunity` / `withdraw_opportunity` | 唯一管理员维护人工覆盖、核实和发布状态；下架不删除岗位历史或用户收藏 |
| `resolve_review_item` | 唯一管理员接受客观事实、保留人工值或关闭审核项；同一开放项不可重复处理 |
| `resolve_review_items` | 唯一管理员原子接受当前页指定审核项或全部开放审核项；并发下只处理仍开放的项目，并以单次批量审计记录范围和数量 |
| `update_opportunity_settings` | 唯一管理员原子替换仍在公开范围内的城市、核实状态、企业、招聘类型、岗位类别和届别六组多选默认值；默认值只是公开页首次进入的普通筛选 |
| `set_opportunity_bookmark` | 活跃登录账户幂等收藏/取消，维持 `(account, opportunity)` 唯一 |
| `public_opportunities` | 只读启用且公开来源下在架、已确认/待确认岗位，不泄露内部检查和审核字段 |
| `public_opportunity_sources` / `public_opportunity_filters` / `public_opportunity_summary` | 公开来源分页、全站筛选集合和摘要计数；只投影可公开事实 |
| `bookmarked_opportunities` | 只读调用账户自己的收藏，保留已下架/已过期岗位的安全状态标记 |
| `admin_sources` / `admin_opportunities` / `admin_review_queue` | 唯一管理员的来源、岗位与审核分页投影；普通账户不可调用，收藏不进入管理投影 |
| `admin_check_run_sources` / `admin_check_run_source_detail` | 按来源分页的任务历史与单条快照差异详情；详情至多返回 200 条新增/更新岗位，不在历史列表全量物化 |

来源抓取、TaskRun、每日调度和 90 天清理由同一 owner 提供；T22 管理页面和 T23 公开页面均已落地。展示层不得同步执行外部读取，只提交运行请求并读回持久状态；公开筛选和分页始终以服务端查询为真值。

## agents 公开服务

| 服务 | 关键输入 | 结果 | 典型错误 |
| --- | --- | --- | --- |
| `manage_agent_endpoint` | admin, endpoint fields, expected version | endpoint safe snapshot | 参数范围/交叉冲突、秘密别名非法、并发 409 |
| `manage_agent_profile` | admin, stable key, endpoint, schema key, expected version | profile | endpoint/Prompt 不可用、用途冲突 |
| `save_agent_prompt_revision` | admin, profile, Markdown, expected version | immutable revision + current pointer | 未知变量、内容超限、并发 409 |
| `check_agent_endpoint` | admin, endpoint, idempotency key | async check reference | 频控、禁用、网络策略拒绝 |
| `resolve_agent_snapshot` | stable profile key | immutable runtime snapshot | profile/endpoint/Prompt 未启用 |
| `invoke_structured` | snapshot, caller ref, idempotency key, bounded blocks, schema key | validated JSON + invocation ref | token/并发不足、SSRF、超时、响应过大、schema 非法 |
| `restore_default_token_limits` | admin, expected versions | site/endpoint limits | 范围、endpoint > site、并发 409 |
| `reset_token_usage` | admin, scope, reason, idempotency key | adjustment + remaining summary | 活跃预留保护、并发 409 |

只有 `resolve_agent_snapshot` 与 `invoke_structured` 面向业务 owner；管理命令仅供 administration 编排。返回 DTO 不含秘密、完整 Prompt、业务正文或模型原始响应。

## learning 公开服务

| 服务 | 关键输入 | 结果 | 典型错误 |
| --- | --- | --- | --- |
| `submit_knowledge_document` | owner, staged asset, statement version/accepted, idempotency key | document + review run | 无附件能力、格式/大小、声明过期、账户内重复、配额 |
| `retry_document_review` | owner/admin-approved appeal, document version | new review run | 状态非法、权限撤销、并发运行 |
| `delete/restore_knowledge_document` | owner, document, expected version | deletion/restored state | 非本人、过期、管理员锁/申诉竞态 |
| `submit/withdraw/review_learning_appeal` | actor, target, Markdown reason/decision, row version | appeal state | 非法目标、已有 pending、并发 409 |
| `generate_question_bank` | owner, approved document, title/description, type switches | generation run | 非本人、无附件能力、至少一题型、配额/并发 |
| `revise_question_bank` | owner/admin, series/bank, full revision, reason, version | new immutable revision | admin 锁、schema、并发 409 |
| `set_question_bank_visibility` | owner/admin, target state, version | visibility state | owner 解除 admin 锁、状态非法 |
| `delete/restore_question_bank` | owner/admin, bank, version | deletion/restored state | 冷静期/管理员锁/申诉竞态 |
| `create/save/submit_quiz_attempt` | actor, bank revision/config or attempt version/answers | attempt/result | 未登录、配置过期、非本人、并发 409 |
| `submit_quiz_response` | actor, practice attempt, response version, final answer | one graded/revealed response | 非刷题模式、未登录、非本人、已关闭、并发 409 |
| `set_wrong_question_mastery` | actor, wrong item, state, version | wrong item | 非本人、非法状态 |
| `delete/restore_quiz_records` | actor, explicit attempt IDs, versions | per-item result | 非本人、数量/状态冲突 |

公开 queries 为 `public_question_bank_page/detail`；本人 queries 为文档、访问历史、答题、错题和记录；管理员 queries 为安全配置、运行、申诉与显式选择列表。HTML 与 API transport 必须复用公开 filter DTO/projection；API gate、CORS 与限流在进入公开 query 前执行。

## 返回与错误规则

- 表单可修复错误：稳定业务错误码 + 字段映射，例如 `account.email_taken`。
- 权限错误：对私人/草稿读取返回 `content.not_found`，避免对象存在性泄露；管理写入可返回 `access.denied`。
- 冲突：返回 409 语义的 `content.edit_conflict` 和安全版本列表。
- 限流：返回明确用户文案与可重试时间，但不暴露内部 Redis 键。
- 未预期错误：用户只见通用提示与 trace code；完整脱敏诊断进入 RuntimeError。

服务不能返回“已成功排队”并在 UI 显示业务完成。异步动作返回 `JobAccepted(job_id)`，界面显示进行中；只有 Job `COMPLETED` 才显示完成。
