# 账户与内容字段字典

类型是逻辑类型；实现时映射为 Django/PostgreSQL 类型。所有时间 UTC 存储，界面与自然日规则按 `Asia/Shanghai` 转换。

## Account

| 字段 | 类型 | 空值 | 规则 |
| --- | --- | --- | --- |
| `id` | UUIDv4 | 否 | 主键、永不复用、不得由邮箱或昵称推导 |
| `email` | varchar(254) | 否 | 保存规范化地址，大小写不敏感唯一 |
| `password_hash` | Django password | 否 | 仅使用 Django 哈希器，不进入日志/审计 |
| `nickname` | varchar(16) | 是 | 安全可见字符；汉字计 2、其他字符计 1，总预算 16；拒绝空白、控制和不可见字符，保留用户输入的原始大小写用于展示 |
| `normalized_nickname` | text | 是 | 由 `nickname` 以唯一共享函数产生 Unicode `casefold` 规范值；大小写不敏感唯一约束和冲突裁决作用于此字段 |
| `status` | enum | 否 | `ACTIVE`、`DISABLED`；删除账户物理移除并保留匿名历史引用 |
| `theme` | enum | 否 | `LIGHT`、`DARK`、`EYE_CARE`，默认 `LIGHT` |
| `auto_republish_enabled` | bool | 否 | 默认关闭；仅普通已发布文章的显式云保存可自动重发，首次发布与历史恢复仍强制终稿审查 |
| `attachment_upload_enabled` | bool | 否 | 默认关闭；只有作者可由管理员授予，撤销作者角色时同步关闭 |
| `avatar_asset_id` | media id | 是 | 只能绑定本人头像用途资产 |
| `nickname_changed_at` | timestamptz | 是 | 7 天冷却判断来源 |
| `must_change_password` | bool | 否 | 首次管理员登录前为真 |
| `created_at` / `updated_at` | timestamptz | 否 | 服务维护 |

账户名回退为邮箱 `@` 前的稳定展示值；不能在页面暴露完整邮箱。删除后历史评论不保存可复用昵称，只显示“该账号已注销”。

## RoleAssignment

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `account_id` | UUID FK | 与 `role` 联合唯一 |
| `role` | enum | `AUTHOR`、`ADMINISTRATOR` |
| `granted_by` | UUID FK | 首次引导可为空，其后必须是管理员 |
| `granted_at` | timestamptz | 永久审计来源之一 |

数据库保证最多一个 `ADMINISTRATOR`；初始化命令和健康检查保证系统恰有一个。管理员必须同时持有 `AUTHOR`，撤销作者角色服务不得作用于管理员。

## LoginSession

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | UUID | 浏览器可见会话标识，不是认证凭证 |
| `account_id` | UUID FK | 账户删除时删除 |
| `token_digest` | char(64) | 只保存随机令牌摘要，唯一 |
| `kind` | enum | `STANDARD_12H`、`REMEMBER_30D` |
| `created_at` / `last_seen_at` | timestamptz | 活跃时间允许节流更新 |
| `expires_at` / `revoked_at` | timestamptz | 二者任一失效即不可认证 |
| `user_agent_summary` | varchar(255) | 解析后的设备/浏览器展示值 |
| `created_ip` | inet | 仅管理员详情可见完整值 |

密码重置撤销全部会话；登录态改密保留当前会话但旋转令牌，撤销其他会话；“退出所有设备”包括当前会话。

## InviteCode

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | UUID | 主键 |
| `code_digest` | char(64) | 对 16 位 Crockford Base32 原码做带密钥摘要，唯一 |
| `display_suffix` | char(4) | 历史列表仅显示尾部，不可用于兑换 |
| `expires_at` | timestamptz | 只允许生成时选择 1、3、7、30 天 |
| `revoked_at` | timestamptz | 仅未使用码可撤销 |
| `redeemed_by` / `redeemed_at` | UUID / time | 创建账户成功的同一事务写入 |
| `created_by` / `created_at` | UUID / time | 管理员与审计追踪 |

原码只在生成结果页显示一次，批量最多 1,000。状态从时间和字段派生为 `ACTIVE`、`USED`、`REVOKED`、`EXPIRED`，不保存可能漂移的重复状态。

## IpBlock 与 SecurityEvent

`IpBlock` 使用规范化 PostgreSQL `inet` 唯一保存地址、可选管理员备注、创建/解除时间和操作者。解除后保留记录但不再拦截。

`SecurityEvent` 永久记录事件类型、账户（可空）、完整 IP、请求 trace code、时间和安全摘要。验证码值、密码、会话令牌、邮件正文不得进入摘要。

## Article

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | ULID char(26) | 公开永久链接、不可变 |
| `author_id` | UUID FK | 创建后不可转移 |
| `publication_state` | enum | `DRAFT`、`SCHEDULED`、`PUBLISHED` |
| `working_revision_id` | ULID FK | 当前作者工作版本，必有 |
| `published_revision_id` | ULID FK | 尚未发布时为空；读者永远只读此版本 |
| `scheduled_revision_id` | ULID FK | 定时发布锁定的修订；非定时时为空 |
| `scheduled_for` | timestamptz | 仅 `SCHEDULED` 必填 |
| `published_at` | timestamptz | 首次发布排序；重发不重置 |
| `last_published_at` | timestamptz | 最近发布/重发时间 |
| `deleted_at` / `purge_after` | timestamptz | 软删除时同时设置，间隔 7 天 |
| `row_version` | bigint | 每次工作版本切换递增，用于并发令牌 |
| `created_at` / `updated_at` | timestamptz | 服务维护 |

管理员隐藏不写入 Article；由 `ArticleModerationCase` 形成独立遮罩。作者禁用遮罩由账户状态和查询策略派生。这样恢复时无需猜测原可见性。

## ArticleRevision

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | ULID | 不可变修订标识 |
| `article_id` | ULID FK | 与 `sequence` 联合唯一 |
| `sequence` | bigint | 文章内单调递增，在行锁事务中分配 |
| `based_on_id` | ULID FK | 记录编辑/恢复基线，可为空 |
| `restore_source_id` | ULID FK | 版本恢复时指向历史来源 |
| `content_format` | enum | `MARKDOWN`、`TIPTAP_JSON` |
| `title` | varchar(30) | 非空、不唯一，按 Unicode 字符计数 |
| `body_source` | text/jsonb | 二者按格式只用其一；序列化后默认最大 `2 MiB`，管理员可配范围仅为 `64 KiB` 至 `2 MiB` |
| `summary_mode` | enum | `NONE`、`AUTO`、`CUSTOM` |
| `custom_summary` | varchar(100) | 仅 `CUSTOM` 使用 |
| `visibility` | enum | `PUBLIC`、`AUTHENTICATED`、`PRIVATE` |
| `section_id` | UUID FK | 可空表示未知分区；普通发布流程必须非空 |
| `cover_asset_id` | media id | 空时使用全站默认封面 |
| `attachment_asset_id` | media id | 空或一个文章附件；必须与修订的固定 `attachment` 绑定槽一致 |
| `comments_enabled` | bool | 默认真 |
| `comments_view_login` | bool | 默认假 |
| `comments_post_login` | bool | 默认假；只控制顶层访客评论 |
| `created_by` / `created_at` | UUID / time | 修订作者与时间 |

修订写入后不做原地更新。发布、导入更新和恢复都创建新修订并更新指针。正文格式通常由首个修订固定；Markdown 导入和历史恢复是经过服务明确批准的两种例外。

## ArticlePublication

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | ULID | 不可变发布记录标识 |
| `article_id` / `revision_id` | ULID FK | 必须指向同一文章；联合唯一，同一 revision 只记录一次 |
| `published_at` | timestamptz | 该 revision 实际发布、导入发布或可见性重发的时间 |
| `created_at` | timestamptz | 发布历史记录写入时间 |

发布历史是 content 的持久事实，只追加、不原地更新。旧数据由 `article.published.v1` 事件回填历史版本，并以 Article 当前发布指针补齐缺少事件的最新版本；事件表不是后续查询来源。

## Section、Tag 与关联

`Section`：UUID、唯一规范化名称、创建与更新时间。可空默认封面只保存为 `SECTION_COVER -> SECTION/default-cover` 的 ACTIVE 媒体绑定，不在 Section 重复存 asset ID；删除分区会物理移除分区记录，把当前文章投影置为未知分区，并由 media owner 解除默认封面绑定、提交后清理无其他引用的文件；不删除文章。

`Tag`：UUID、显示名、规范化名、`PENDING/ACTIVE/REJECTED/DELETED` 状态、提议作者、审核者和时间。作者新标签先 `PENDING` 且可立即显示；拒绝时从当前文章投影移除；删除的全站标签保留记录。

`RevisionTag` 保存历史修订快照；`ArticleTag` 保存当前工作/发布查询投影并限制每篇最多 10 个；`TagAssociationHistory` 记录管理员删除标签时受影响的文章，以便恢复标签时自动恢复仍合法的关联。

## 文章读取口径

- 作者编辑：`working_revision_id`。
- 普通读者：`published_revision_id`，且无删除、管理员隐藏或作者禁用遮罩。
- 定时任务：只发布 `scheduled_revision_id`，防止排期后继续编辑导致内容漂移。
- 管理员查看：可选工作修订或 `ArticlePublication` 中任一发布修订，必须经过策略并对其他作者按日聚合通知。
- SEO、搜索、首页：只使用满足公开策略的 `published_revision_id`。
