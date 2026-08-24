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
| `content_article_publication` | `(article_id, revision_id)` 唯一；复合外键保证 revision 属于同一文章；文章删除级联清理 |
| `revision_tag` / `article_tag` | `(revision/article, tag)` 唯一 |
| `tag` | 未删除的规范化名称唯一 |
| `media_asset` | `storage_key` 唯一；图片 `0 < size_bytes <= 2 MiB`，附件及 Hero 视频 `<= 10 MiB`；视频格式只能属于 `HERO`，Hero 只允许普通图片或 MP4/WebM |
| `media_binding` | `(target_type, target_id, slot)` 与 `(asset_id, target_type, target_id)` 分别唯一；目标类型受注册白名单约束 |
| `discussion_thread` | `(target_type, target_id)` 唯一 |
| `comment` | parent 与 child 属于同一 thread；`depth >= 0`；可见时间不早于创建时间 |
| `report` | `(reporter_id, target_comment_id)` 唯一 |
| `report_appeal` | `report_id` 唯一 |
| `notification_receipt` | `(notification_id, recipient_id)` 唯一 |
| `discovery_reading_bookmark` | `(account_id, article_id)` 唯一；`0 <= progress <= 1` |
| `task_run` | `(task_name, idempotency_key)` 唯一 |
| `export_job` | `state IN (RUNNING, CANCEL_REQUESTED)` 全局部分唯一 |
| `navigation_node` | 深度 `0..2`；`GROUP` 目标均为空、`SECTION` 仅有目标 ID、链接节点仅有 URL；`default_expanded` 非空且默认 false；叶节点不得开启及父子不能成环由服务加锁校验 |
| `opportunity_source` | 规范官方 URL 唯一；来源/检查状态枚举；公开必须已启用；同域请求间隔至少 2 秒；页数、岗位数、时长和行版本均为正数 |
| `opportunity_filter_option` / `opportunity_source_filter_option` | 全站 `(kind, normalized_label)` 唯一；每来源每选项唯一；最近发现时间不早于首次发现时间 |
| `opportunity` / `opportunity_filter_assignment` | 岗位以来源和“规范 URL + 规范采集标题”的固定身份摘要唯一，同一列表 URL 可承载多个独立岗位；招聘/核实/发布/来源枚举；每岗位、选项、赋值来源唯一；来源停用快照与下架状态形状一致 |
| `opportunity_check` / `opportunity_review_item` | 检查目标、完成时间、HTTP 状态和到期时间形状受约束；每岗位每审核类型至多一个开放项 |
| `opportunity_check_run` / `opportunity_check_run_source` | 全站同时至多一个等待/运行/待取消任务；运行完成时间与终态匹配；每运行来源和位置唯一 |
| `opportunity_collection_snapshot` / `opportunity_state_transition` | 完整与截断不能同时为真、到期晚于观察；岗位状态转换前后不同且只能使用固定核实状态 |
| `opportunity_bookmark` / `opportunity_settings` | `(account_id, opportunity_id)` 唯一；设置表只允许主键 `1` 且行版本为正数 |
| `opportunity_default_filter_selection` | 每个设置、筛选种类与选项/来源/枚举值唯一；城市/类别/届别只能引用筛选选项，企业只能引用来源，状态/招聘类型只能保存非空枚举值 |
| `agent_endpoint` / `agent_profile` / `agent_prompt_revision` | Endpoint 安全名称唯一；profile stable key 唯一；`(profile_id, sequence)` 唯一且当前 Prompt 必须属于 profile；运行参数与每日额度有范围/交叉 CHECK |
| `agent_invocation` / `agent_token_ledger` / `agent_token_reservation` / `agent_token_adjustment` / `agent_token_reset_operation` | `(caller_type, caller_id, idempotency_key)` 唯一；ledger scope/date 唯一；reservation/adjustment/reset 幂等键唯一；token 数非负，reset 范围、终态与租约时间形状一致 |
| `knowledge_document` / `knowledge_review_run` | 同 owner 未清理 `content_sha256` 条件唯一；声明版本/确认事实成对；一个文档至多一个活跃 review run；删除/30 天清理时间与状态匹配 |
| `learning_appeal` / `knowledge_document_access` | 每目标至多一个 PENDING appeal；access 必须有管理员 actor、用途和成功读取时间，不含正文列 |
| `question_bank_series` / `question_bank` / `question_bank_revision` / `question` | 每 series 卷号 `1..2` 唯一；`(bank, sequence)` 与 `(revision, ordinal)` 唯一；current revision 属于同 bank；题型/选项/答案与覆盖计数受约束 |
| `question_bank_tag` / `question_bank_tag_assignment` | learning 内规范名称唯一；每 series/tag 唯一，不引用 content tag |
| `quiz_attempt` / `quiz_response` / `wrong_question` | response 每 attempt/question logical ID 唯一；wrong item 每 account/bank/question logical ID 唯一；计时、版本、分数与 mastery 枚举受约束 |

“恰好一个管理员”“每篇最多十标签”“父评论同线程”“修订指针同文章”在普通 `CHECK` 难以完整表达时，使用以下优先级：原生唯一/外键约束、延迟约束触发器、加锁的领域服务、数据库回归测试。不要只在表单层校验。

## 服务端事务与锁

| 动作 | 锁与隔离策略 |
| --- | --- |
| 兑换邀请码注册 | `SELECT ... FOR UPDATE` 锁邀请码；创建账户与写兑换结果同事务 |
| 昵称修改 | 依赖唯一索引裁决并捕获冲突；冷却时间在账户行锁内检查 |
| 新建修订 | 锁 Article 行，校验 `row_version`，分配 sequence，切换 working 指针 |
| 发布/定时发布 | 锁 Article；确认目标修订、权限、分区和遮罩，再原子切指针 |
| 标签增删 | 锁 Article；服务检查最多十个，再同步修订快照与当前投影 |
| 分区封面更新 | 锁 Section；名称、可空 asset ID 与 `SECTION/default-cover` 单槽绑定同事务替换，文件清理只在提交后执行 |
| 评论回复 | 锁 parent 或 thread；计算 depth 并原子增加根评论 reply_count |
| 评论缓冲公开 | 条件更新 `BUFFERED -> VISIBLE`，重复运行影响行数为零 |
| 评论置顶 | 锁 thread；`thread_id`/`comment_id` 各自唯一；置顶另一条时原子替换 |
| 文章点赞 | `(account_id, article_id)` 唯一；重复写入幂等 |
| 举报裁决 | 锁 Report；只允许从当前状态走一条合法边 |
| 单全局导出 | 先插入 `RUNNING`，并让 `RUNNING/CANCEL_REQUESTED` 共用部分唯一约束作为最终并发裁决 |
| 导航编辑/移动/删除 | 锁全树与树版本；默认展开只允许父节点，原父节点失去最后子项时同事务复位并推进节点版本 |
| 软删除到期清理 | `skip_locked` 小批量领取；每个文章独立事务与幂等文件清理 |
| AGENT 首次外呼与结算 | 锁全站/Endpoint 当日 ledger 并按稳定顺序原子预留；结算/adjustment 依幂等键，活跃 reservation 不被 reset 清除 |
| 文档提交/审核领取 | 锁账户配额、文档和运行；摘要唯一约束裁决重复；领取同时占用业务并发和 token reservation |
| 题库生成/修订 | 锁文档、系列/题库当前指针与账户配额；所有卷完整校验后原子发布，不暴露半卷 |
| 答题保存/提交 | 锁本人 attempt 并校验 row version；重复自动保存/提交幂等，提交后 wrong book 更新同事务 |

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
| 管理发布历史 | `(article_id, published_at)`，列表再以 revision sequence 和记录 ID 稳定排序 |
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
| 公开岗位 | `(publication_state, verification_status, source_id)` 过滤索引；`(published_at desc, id)` 支持发布时间倒序且空值最后，再按来源规范企业名、标题和稳定 ID 收口 |
| 后台岗位 | `(source_id, origin, updated_at)`；审核队列 `(state, kind, created_at)` |
| 公开招聘来源 | `(enabled, publicly_visible, normalized_company_name)`；检查摘要 `(check_state, last_checked_at)` |
| 岗位筛选与收藏 | `(option_id, opportunity_id)`；账户收藏 `(account_id, created_at desc, opportunity_id)` |
| 检查历史 | 来源/目标类型/开始时间、岗位/开始时间及到期清理索引 |
| AGENT 管理/用量 | endpoint 启用+名称；profile stable key；invocation 状态/创建时间；ledger scope/date；reservation lease expiry 部分索引 |
| 本人知识文档 | `(owner_id, state, created_at desc, id)`；待审核/清理使用 `(state, purge_after, id)` 部分索引 |
| 公开题库 | 可见题库 `(published_at desc, id)`；完成次数/题量排序稳定索引；标题/简介/learning tag trigram 与关联索引 |
| 审核/生成运行 | `(state, scheduled_at, id)`、业务幂等键、lease expiry 部分索引 |
| 答题/错题/记录 | `(account_id, updated_at desc, id)`；wrong `(account_id, mastery, bank_snapshot_id, id)`；response `(attempt_id, ordinal)` |

分页使用稳定二级键。文章传统页码可以 OFFSET；评论无限滚动、通知和日志使用 keyset cursor，避免数据增长后重复/漏项。

## 标题相关度

标题搜索初始使用 PostgreSQL `pg_trgm` 相似度，无需引入 Elasticsearch。查询先限定调用者可见的发布修订，再按 `similarity(title, query) DESC, published_at DESC, article_id DESC` 排序。阈值由配置与真实中文样本调校。

## 数据删除与外键策略

- 账户删除：会话、收藏、点赞、阅读书签和通知回执 `CASCADE`；评论置顶操作者 `SET NULL`；评论作者 `SET NULL` 并先写删除身份标志；举报和审计使用删除身份快照。
- 文章物理删除：修订、当前标签、讨论线程、评论 `CASCADE`；报告/申诉保留稳定目标 ID，不级联。
- 媒体资产：不得由任意业务外键直接 `CASCADE` 删除磁盘文件；先解绑，再由媒体服务/任务删除文件并标记。
- 标签删除：业务软删除，不依赖级联；当前关联移除并保留恢复历史。
- 通知管理员删除：业务软删除并从用户查询排除，审计仍保留。
- 知识文档最终清理：先经 learning 解除 media 绑定并保留无正文 tombstone；不得级联已生成题库。
- 题库最终清理：停止公开/API/新答题并删除本体；历史 response/wrong 快照置空引用后继续限本人读取。
- 账户彻底删除：删除本人文档、题库、attempt/wrong；其他账户历史中作者引用置空并匿名化，审计只保留不可反向识别的计数/时间桶。

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
