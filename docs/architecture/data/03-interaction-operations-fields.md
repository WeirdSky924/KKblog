# 互动、通知、运维与交换字段字典

本文覆盖评论、审核、通知、审计、任务和数据交换。正文与证据中的敏感信息遵循统一脱敏策略。

## MediaAsset 与 MediaBinding

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `MediaAsset.id` | ULID | 不暴露真实磁盘路径 |
| `owner_id` | UUID FK | 上传者；站点资产可指管理员 |
| `purpose` | enum | `AVATAR/COVER/BODY/COMMENT/EVIDENCE/LOGO/FRIEND_LOGO/IMPORT` |
| `storage_key` | varchar | 媒体服务生成的相对键，唯一；禁止用户路径片段 |
| `original_name` | varchar | 清洗后仅供展示，不参与寻址 |
| `detected_mime` | enum | 解码后真实 PNG/JPEG/GIF/WebP；Logo 另允许 ICO |
| `size_bytes` | bigint | `1..2 MiB` 检查约束 |
| `sha256` | char(64) | 完整性与重复诊断，不作为公开 ID |
| `width` / `height` | int | 解码结果，正数；ICO 可按帧处理 |
| `state` | enum | `STAGED/ACTIVE/DELETE_PENDING/DELETED` |
| `created_at` / `deleted_at` | time | 生命周期追踪 |

`MediaBinding` 保存 asset、受控 `target_type`、目标稳定 ID、`slot` 和创建时间，联合唯一。它不允许任意字符串目标；类型必须来自媒体模块注册表并由目标领域服务绑定。

## DiscussionThread 与 Comment

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `DiscussionThread.id` | UUID | 每篇文章一个；全站留言板一个 |
| `target_type` | enum | `ARTICLE`、`GUESTBOOK` |
| `target_id` | varchar | 文章 ULID 或固定留言板键 |
| `owner_id` | UUID FK | 文章作者或管理员 |
| `comments_enabled` | bool | 从文章发布修订投影或留言板设置同步 |
| `view_login_required` | bool | 文章/留言板策略 |
| `post_login_required` | bool | 只影响顶层评论；回复始终登录 |
| `Comment.id` | ULID | 稳定评论 ID |
| `CommentPin.thread_id` | UUID unique | 每个文章线程至多一个置顶位置 |
| `CommentPin.comment_id` | ULID unique | 仅指向同线程公开顶层评论 |
| `CommentPin.pinned_by_id/pinned_at` | UUID?/datetime | 操作者删除后保留置顶事实与时间 |
| `thread_id` | UUID FK | 目标线程 |
| `parent_id` | ULID self FK | 顶层为空 |
| `root_id` | ULID FK | 顶层等于自身，回复指向根，便于分页 |
| `author_id` | UUID FK | 访客为空；账户删除时置空并标注销来源 |
| `author_kind` | enum | `ANONYMOUS/ACCOUNT/DELETED_ACCOUNT` |
| `body` | varchar(100) | 删除后清空；长度按产品字符口径 |
| `state` | enum | `BUFFERED/VISIBLE/DELETED` |
| `visible_at` | timestamptz | 创建后 10 分钟；删除则不公开 |
| `depth` | int | 父深度 + 1，无上限；超过 100 触发一次通知 |
| `reply_count` | bigint | 热门排序投影，事务维护 |
| `client_ip` | inet | 永久保存，仅管理员详情可见完整值 |
| `deleted_by_kind` | enum | `SELF/OWNER/ADMIN/REPORT` |
| `deletion_reason` | varchar(200) | 仅管理员动作可选；对相关通知安全展示 |

顶层评论最多三个媒体绑定；回复不允许图片。删除评论立即解绑并删除图片，但保留节点和子回复位置。文章物理删除时评论节点一并物理删除。

`discovery_article_like` 以 `(account_id, article_id)` 唯一，账户或文章物理删除时级联；公开列表按文章 ID 批量聚合计数，不能逐条查询。

## Report 与 ReportAppeal

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `Report.id` | ULID | 主键 |
| `target_comment_id` | ULID FK | 初审时目标必须存在或有删除占位 |
| `reporter_id` | UUID FK | 必须登录；对被举报方隐藏 |
| `reason` | enum | 垃圾广告、辱骂骚扰、违法危险、隐私泄露、无关内容、其他 |
| `description` | varchar(200) | 可空 |
| `state` | enum | `PENDING/UPHELD/REJECTED/APPEAL_PENDING/FINAL_UPHELD/FINAL_REJECTED/CLOSED` |
| `reviewed_by` / `reviewed_at` | UUID / time | 管理员裁决 |
| `decision_reason` | varchar(200) | 管理端说明，按通知模板展示 |

同一举报人对同一评论只能创建一次 `Report`。`ReportAppeal` 至多一条：初审失败时仅举报人可申诉，初审成功时仅被举报账户可申诉；复审后进入终局状态。首次举报和申诉分别最多三张证据图。

举报人删除账户时未结案举报进入 `CLOSED`；被举报账户删除时结案为“内容已删除”并通知仍存在的举报人。举报与申诉永久保留，账户引用转为不可复用的删除身份快照。

## ArticleModerationCase 与 ArticleAppeal

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | ULID | 管理动作案件 |
| `article_id` | ULID | 文章删除后仍以稳定 ID 保留 |
| `action` | enum | `HIDE/DELETE` |
| `state` | enum | `ACTIVE/RESTORED/APPEALED/FINAL_UPHELD/FINAL_REJECTED` |
| `pre_action_snapshot` | jsonb | 仅状态、可见性、修订 ID等安全小字段 |
| `reason` | varchar(200) | 可空 |
| `acted_by` / `acted_at` | UUID / time | 唯一管理员 |

每个有效管理动作只允许作者提交一次 `ArticleAppeal`，限制 200 字和三张证据图。准许申诉调用内容恢复服务；驳回为终局。文章正文不复制到案件 JSON 中。

## Notification 与 Receipt

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `Notification.id` | ULID | 主键 |
| `type` | enum | 模板注册表键，不允许任意 HTML |
| `actor_id` | UUID | 可空；系统通知无 actor |
| `target_type` / `target_id` | string | 用于安全跳转和聚合 |
| `payload_safe` | jsonb | 仅模板所需非敏感字段，写前 schema 校验 |
| `dedupe_key` | varchar | 可空；存在时唯一 |
| `hidden_at` / `deleted_at` | time | 管理员群发的全局可见性控制 |
| `NotificationReceipt.recipient_id` | UUID | 与通知联合唯一 |
| `read_at` | timestamptz | 空为未读 |

群发面向所有注册用户并创建收件回执；用户不能删除。隐藏可恢复，删除对全体不可见但保留管理员审计。个人通知按事件生成；管理员查看文章和导出他人文章用“作者 + 文章/事件 + 上海日期”去重。

## AuditEntry、RuntimeError 与 TaskRun

`AuditEntry` 永久保存：ULID、trace code、管理员 actor、动作、目标类型/ID、发生时间、完整 IP、非敏感摘要、`before_safe`、`after_safe`。正文和媒体变化只记修订/媒体版本 ID。只读浏览不审计，但管理员查看他人内容的通知投递有独立事件记录。

`RuntimeError` 永久保存：错误码、trace code、分类、脱敏消息、脱敏堆栈、请求/任务来源、首次/最近发生时间、次数、关联 `TaskRun`。禁止保存请求密码、验证码、Cookie、Authorization、`.env`、正文和原始上传内容。

`TaskRun` 保存：任务名、业务对象、幂等键、状态、尝试次数、计划/开始/完成时间、Celery ID、最终错误码。`task_name + idempotency_key` 唯一；三次均失败后写 RuntimeError 与管理员通知。

## ImportJob 与 ImportItem

`ImportJob`：ULID、导入作者、包媒体资产、状态、预览摘要、创建/确认/完成时间。上传解析阶段不写文章。

`ImportItem`：包内路径、导入 ID、检测标题、目标文章、判定 `NEW/DUPLICATE_ID/TITLE_WARNING/FOREIGN_CONFLICT/INVALID`、作者选择 `SKIP/UPDATE/CREATE`、映射后的分区/标签、预览、结果与原因。确认后逐项独立事务，允许部分成功；每项使用 `job_id + item_key` 幂等。

## ExportJob、BackupRecord 与站点配置

`ExportJob` 保存管理员、筛选范围、状态、选择快照、归档媒体 ID、取消/完成/过期时间。数据库部分唯一约束保证全站最多一个 `RUNNING`；完成包三天后删除，审计不删。

`BackupRecord` 保存数据库/媒体备份任务、固定 `local` destination、路径键、开始/完成时间、字节数和失败码；保留 30 天。不把“文件已生成”记录成完整性验证。

站点配置不要放入一个无约束 JSON 大桶：

- `SiteConfiguration` 单例保存站名、描述、版权、图片/正文限制、注册开关、主题默认值、品牌资产引用和可空的验证码 HTML 模板；模板为空表示使用代码内默认模板，SMTP 地址与密钥仍只属于部署配置。
- `StaticPage` 保存 ABOUT/PRIVACY/TERMS 的格式、正文和发布状态。
- `TrustedEmbedSource` 保存来源名、主机规则和启用状态，初始仅 Bilibili。
- `FriendLink` 保存名称、URL、描述、Logo 和排序。
- `NavigationNode` 保存三层树、节点类型、目标、排序和隐藏状态。
