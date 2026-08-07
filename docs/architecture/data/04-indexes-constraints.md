# 数据库约束、索引与迁移纪律

数据库约束保护“不因任何入口而改变”的事实；服务校验处理依赖身份、时间或外部状态的规则。两者不能互相替代。

## 必须落到数据库的约束

| 表 | 约束 |
| --- | --- |
| `account` | `lower(email)` 唯一；有效 nickname 规范化值唯一；状态枚举检查 |
| `role_assignment` | `(account_id, role)` 唯一；`role=ADMINISTRATOR` 部分唯一 |
| `login_session` | `token_digest` 唯一；`expires_at > created_at` |
| `invite_code` | `code_digest` 唯一；兑换账户唯一；过期时间晚于创建时间 |
| `ip_block` | 未解除的规范化 IP 部分唯一 |
| `article` | 作者不可空；三个修订指针必须属于同一文章；软删除时间成对出现 |
| `article_revision` | `(article_id, sequence)` 唯一；标题非空；格式与正文列匹配 |
| `revision_tag` / `article_tag` | `(revision/article, tag)` 唯一 |
| `tag` | 未删除的规范化名称唯一 |
| `media_asset` | `storage_key` 唯一；`0 < size_bytes <= 2097152` |
| `media_binding` | `(asset_id, target_type, target_id, slot)` 唯一 |
| `discussion_thread` | `(target_type, target_id)` 唯一 |
| `comment` | parent 与 child 属于同一 thread；`depth >= 0`；可见时间不早于创建时间 |
| `report` | `(reporter_id, target_comment_id)` 唯一 |
| `report_appeal` | `report_id` 唯一 |
| `notification_receipt` | `(notification_id, recipient_id)` 唯一 |
| `discovery_reading_bookmark` | `(account_id, article_id)` 唯一；`0 <= progress <= 1` |
| `task_run` | `(task_name, idempotency_key)` 唯一 |
| `export_job` | `state IN (RUNNING, CANCEL_REQUESTED)` 全局部分唯一 |
| `navigation_node` | 深度 `0..2`；父子不能形成环由延迟触发器或服务加锁校验 |

“恰好一个管理员”“每篇最多十标签”“父评论同线程”“修订指针同文章”在普通 `CHECK` 难以完整表达时，使用以下优先级：原生唯一/外键约束、延迟约束触发器、加锁的领域服务、数据库回归测试。不要只在表单层校验。

## 服务端事务与锁

| 动作 | 锁与隔离策略 |
| --- | --- |
| 兑换邀请码注册 | `SELECT ... FOR UPDATE` 锁邀请码；创建账户与写兑换结果同事务 |
| 昵称修改 | 依赖唯一索引裁决并捕获冲突；冷却时间在账户行锁内检查 |
| 新建修订 | 锁 Article 行，校验 `row_version`，分配 sequence，切换 working 指针 |
| 发布/定时发布 | 锁 Article；确认目标修订、权限、分区和遮罩，再原子切指针 |
| 标签增删 | 锁 Article；服务检查最多十个，再同步修订快照与当前投影 |
| 评论回复 | 锁 parent 或 thread；计算 depth 并原子增加根评论 reply_count |
| 评论缓冲公开 | 条件更新 `BUFFERED -> VISIBLE`，重复运行影响行数为零 |
| 评论置顶 | 锁 thread；`thread_id`/`comment_id` 各自唯一；置顶另一条时原子替换 |
| 文章点赞 | `(account_id, article_id)` 唯一；重复写入幂等 |
| 举报裁决 | 锁 Report；只允许从当前状态走一条合法边 |
| 单全局导出 | 先插入 `RUNNING`，并让 `RUNNING/CANCEL_REQUESTED` 共用部分唯一约束作为最终并发裁决 |
| 软删除到期清理 | `skip_locked` 小批量领取；每个文章独立事务与幂等文件清理 |

默认使用 PostgreSQL `READ COMMITTED` 加显式行锁，不为“看起来更安全”全局升到 SERIALIZABLE。只有已证明的跨行写偏差再局部采用更高隔离级别。

## 查询索引

索引必须对应真实查询和排序，首版建议：

| 查询 | 索引 |
| --- | --- |
| 邮箱登录/搜索 | `lower(account.email)` unique；管理员模糊搜索再用 `pg_trgm` GIN |
| 昵称唯一/搜索 | `normalized_nickname` unique + trigram |
| 有效会话 | `(account_id, revoked_at, expires_at)` |
| 邀请码状态列表 | `(created_at desc)`；`expires_at`；部分索引 active rows |
| 公开首页 | Article 的 `(published_at desc, id)` 部分索引，加发布/删除条件 |
| 作者文章列表 | `(author_id, updated_at desc)`，包含状态 |
| 定时发布 | `(scheduled_for, id)` where state scheduled and not deleted |
| 软删除清理 | `(purge_after, id)` where `purge_after is not null` |
| 标题模糊搜索 | 发布修订标题 `gin(title gin_trgm_ops)`；结果再按可见策略过滤 |
| 分区文章 | `(section_id, published_at desc)` 当前发布投影 |
| 标签筛选 | `article_tag(tag_id, article_id)` 与文章发布时间索引 |
| 评论第一页 | `(thread_id, state, created_at, id)` where parent null |
| 回复批次 | `(parent_id, created_at, id)` |
| 热门评论 | `(thread_id, reply_count desc, created_at, id)` where parent null |
| 缓冲评论 | `(visible_at, id)` where state buffered |
| 点赞计数 | `(article_id, created_at)` |
| 待审核举报 | `(state, created_at, id)` |
| 未读通知 | `(recipient_id, read_at, notification_id)` where read_at null |
| 最近更新的阅读书签 | `(account_id, updated_at desc, article_id)` |
| 审计检索 | `(created_at desc)`、`(action, created_at)`、`(target_type,target_id)` |
| 运行错误 | `(last_seen_at desc)`、`(error_code,last_seen_at)` |
| 任务监控 | `(state, scheduled_at)`、唯一幂等键 |

分页使用稳定二级键。文章传统页码可以 OFFSET；评论无限滚动、通知和日志使用 keyset cursor，避免数据增长后重复/漏项。

## 标题相关度

标题搜索初始使用 PostgreSQL `pg_trgm` 相似度，无需引入 Elasticsearch。查询先限定调用者可见的发布修订，再按 `similarity(title, query) DESC, published_at DESC, article_id DESC` 排序。阈值由配置与真实中文样本调校。

## 数据删除与外键策略

- 账户删除：会话、收藏、点赞、阅读书签和通知回执 `CASCADE`；评论置顶操作者 `SET NULL`；评论作者 `SET NULL` 并先写删除身份标志；举报和审计使用删除身份快照。
- 文章物理删除：修订、当前标签、讨论线程、评论 `CASCADE`；报告/申诉保留稳定目标 ID，不级联。
- 媒体资产：不得由任意业务外键直接 `CASCADE` 删除磁盘文件；先解绑，再由媒体服务/任务删除文件并标记。
- 标签删除：业务软删除，不依赖级联；当前关联移除并保留恢复历史。
- 通知管理员删除：业务软删除并从用户查询排除，审计仍保留。

## 迁移模板

每个 schema 变更在 PR/实施记录中填写：

1. 当前结构、目标结构与受影响读写入口。
2. 是否添加 nullable 列、回填、约束、索引或删除旧列。
3. 表量级、锁类型、索引是否 `CONCURRENTLY`、预计时长。
4. 应用向前/向后兼容窗口和发布顺序。
5. 失败时应用回滚能否继续读取新 schema。
6. 是否需要迁移前备份；本项目生产迁移一律需要。
7. 数据读回 SQL/pytest 与迁移后健康检查。

采用 expand/migrate/contract：先增加兼容结构，再部署双读/新写并回填，最后在后续明确授权的部署中移除旧结构。数据库迁移不自动回滚，应用回滚必须保持可读。
