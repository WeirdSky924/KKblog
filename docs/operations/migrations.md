# Migration 验证与兼容记录

本页记录 P12 `QA-001` 及后续能力变更对当前 migration graph 的空库、锁、兼容、备份和回滚限制审计。它是部署输入，不代表生产 migration 已获授权或已经执行。

当前源码可作为部署候选，但没有生产域名、管理员邮箱、Resend 身份或密钥，也没有生产数据库的规模与锁窗口读回。P12 未连接或迁移生产数据库，未创建生产迁移前备份，未执行生产部署或服务重启。

## 当前结构与目标结构

- 当前代码的 migration leaf 已由发布门禁完整应用到隔离 PostgreSQL 16；`makemigrations --check --dry-run` 无漂移。相对上一正式版本，本次新增评论置顶、阅读书签、文章点赞与文章发布历史表；前三者不回填既有数据，发布历史从既有发布事件和当前发布指针定向回填。
- 目标结构就是仓库当前 models 与 migration graph；本次增加账户附件能力、修订附件引用、分区默认封面绑定与可空站点 Hero 引用，并扩展媒体用途、目标、大小与可空尺寸约束，不回填既有分区、站点或媒体数据。
- 空库读回覆盖 58 条 migration；P12 已有的 `pg_trgm`、核心表、命名约束、部分唯一索引、查询索引、延迟触发器和关键外键删除动作验证口径保持不变。
- 生产表量级未知。任何锁时长、索引耗时和备份体积必须在获授权部署前从生产只读统计重新估算。

## expand/migrate/contract

后续变更固定分三次兼容发布：expand 只增加 nullable/可忽略结构；migrate 采用可恢复批次回填并让新旧应用均可读；contract 仅在旧应用与旧数据写入完全退出后、另一次明确授权部署中删除旧结构。不得在同一次发布中增加必填列、立即切换唯一事实并删除旧列。

## 锁与兼容窗口

锁分类：`N` 只创建新对象；`M` 对既有表取得短暂 `ACCESS EXCLUSIVE` 元数据锁；`I` 使用普通 `CREATE INDEX`，构建期间会阻塞目标表写入；`D` 含数据回填或约束替换，必须按真实行数测量。当前迁移没有 `CREATE INDEX CONCURRENTLY`，因此生产执行前必须确认维护页和写入静默窗口。

兼容分类：`C0` 旧应用忽略新表/可空列；`C1` 新约束与新写入必须先证明旧应用仍能读取；`C2` 含事实迁移或约束替换，只能按 expand/migrate/contract 顺序发布。

## 备份与回滚限制

所有生产 migration 均为 `B`：执行前必须创建新鲜数据库备份并记录命令成功。`R0` 表示反向只删除尚未被旧应用依赖的新对象；`R1` 表示反向会删除新事实或索引，不作为自动回滚手段；`R2` 表示包含数据/约束转换，只允许应用镜像回滚，数据库保持向前。数据库不自动回滚，备份成功也不等于已验证可恢复。

| Migration | 结构动作 | 锁/兼容 | 备份/回滚 |
| --- | --- | --- | --- |
| `accounts.0001_accounts_foundation` | account、role、session、bootstrap 与唯一/寿命约束 | N/C0 | B/R1 |
| `accounts.0002_invite_code` | 邀请码表、兑换配对约束与查询索引 | N/C0 | B/R1 |
| `accounts.0003_security_event` | 安全事件表与检索索引 | N/C0 | B/R1 |
| `accounts.0004_ip_block` | IP 封禁表、活动地址部分唯一 | N/C0 | B/R1 |
| `accounts.0005_account_deletion` | 账户删除记录与处置形状约束 | N/C0 | B/R1 |
| `accounts.0006_nickname_history` | 昵称历史表与账户索引 | N/C0 | B/R1 |
| `accounts.0007_account_auto_republish_enabled` | account 增加布尔偏好 | M/C0 | B/R1 |
| `accounts.0008_account_attachment_upload_enabled` | account 增加默认关闭的附件能力 | M/C0 | B/R1 |
| `comments.0001_initial` | thread/comment、树外键、延迟树触发器与索引 | N/C0 | B/R1 |
| `comments.0002_comment_created_at_clock` | created_at 默认值语义校正 | M/C1 | B/R1 |
| `comments.0003_thread_deep_alert` | thread 增加深层告警时间 | M/C0 | B/R1 |
| `comments.0004_thread_settings_revision` | thread 增加设置修订标识 | M/C0 | B/R1 |
| `comments.0005_comment_pin` | 新增每文章线程至多一条的评论置顶表与延迟外键 | N/C0 | B/R1 |
| `content.0001_initial` | article/revision、不可变触发器、同文章指针和基础索引 | N/C0 | B/R1 |
| `content.0002_section_articlerevision_section` | section、可空分区引用及历史兼容处理 | M+D/C2 | B/R2 |
| `content.0003_tag_revisiontag_articletag_tagassociationhistory_and_more` | 标签、修订快照、当前投影、历史与约束 | N+D/C2 | B/R2 |
| `content.0004_publicationreviewgrant` | 发布审查 grant 与旧行兼容初始化 | N+D/C1 | B/R2 |
| `content.0005_adminarticleviewreceipt` | 管理查看日去重 receipt | N/C0 | B/R1 |
| `content.0006_articleeditgrant` | 编辑 grant 与旧行兼容初始化 | N+D/C1 | B/R2 |
| `content.0007_articlerestoregrant` | 恢复 grant 与旧行兼容初始化 | N+D/C1 | B/R2 |
| `content.0008_articletombstone` | 物理删除后 tombstone | N/C0 | B/R1 |
| `content.0009_authorcontentmask_and_more` | 作者遮罩、排期时间、约束替换与数据整理 | M+D/C2 | B/R2 |
| `content.0010_article_revision_title_trgm` | `pg_trgm` 与标题 GIN | I/C1 | B/R1 |
| `content.0011_articlerevision_reason` | revision 增加原因枚举字段 | M/C0 | B/R1 |
| `content.0012_articlerevision_attachment_asset_id` | revision 增加可空附件引用 | M/C0 | B/R1 |
| `content.0013_articlerevision_tiptap_schema_version` | revision 增加 TipTap schema 版本与正文形状约束 | M/C1 | B/R1 |
| `content.0014_allow_rejected_tag_name_reproposal` | 临时允许驳回标签名称再次提议 | M/C1 | B/R1 |
| `content.0015_merge_duplicate_tag_identities` | 归并同名标签及其修订/文章关联、删除恢复历史、审计和通知目标，并改为规范名全局唯一 | M+D/C2 | B/R2 |
| `content.0016_article_publication_history` | 新增不可变发布历史表、同文章复合外键、唯一约束与查询索引；从发布事件回填历史版本，并以当前发布指针补齐最新版本 | N+I+D/C1 | B/R2 |
| `core.0001_outbox_foundation` | Outbox 表、租约/就绪索引与状态约束 | N/C0 | B/R1 |
| `discovery.0001_article_view_counter` | 浏览计数与 article 级联外键 | N/C0 | B/R1 |
| `discovery.0002_bookmark` | 私有收藏与 account 级联外键 | N/C0 | B/R1 |
| `discovery.0003_reading_bookmark` | 新增账户文章唯一的阅读进度书签、范围约束与延迟外键 | N/C0 | B/R1 |
| `discovery.0004_article_like` | 新增账户文章唯一的点赞表、计数索引与延迟外键 | N/C0 | B/R1 |
| `exchange.0001_initial` | 导入 Job/Item、幂等与形状约束 | N/C0 | B/R1 |
| `exchange.0002_export_jobs` | 导出 Job/Selection、活动任务部分唯一和索引 | N/C0 | B/R1 |
| `media.0001_initial` | asset/binding、大小/用途/slot 约束与索引 | N/C0 | B/R1 |
| `media.0002_owner_cleanup_lifecycle` | asset owner 删除语义改为 SET NULL | M/C1 | B/R1 |
| `media.0003_owner_lifecycle_constraint` | owner 生命周期配对约束 | M/C1 | B/R1 |
| `media.0004_remove_mediaasset_media_asset_size_range_and_more` | 增加附件用途与格式，放宽附件大小并允许其尺寸为空，替换两条约束 | M+D/C1 | B/R2 |
| `media.0005_remove_mediabinding_media_binding_target_registered_and_more` | 增加 `SECTION_COVER` 用途与 `SECTION` 目标，并替换绑定目标白名单约束 | M+D/C1 | B/R2 |
| `media.0006_remove_mediaasset_media_asset_size_range_and_more` | 增加 `HERO` 与 MP4/WebM，视频上限 10 MiB，并增加 Hero 格式/用途约束 | M+D/C1 | B/R2 |
| `moderation.0001_initial` | 举报、删除身份与基础约束/队列索引 | N/C0 | B/R1 |
| `moderation.0002_reportrecoverysnapshot` | 举报恢复快照 | N/C0 | B/R1 |
| `moderation.0003_reportappeal` | 一次申诉与状态形状约束 | N/C0 | B/R1 |
| `moderation.0004_article_cases_and_account_closure` | 文章案件、账户关闭快照、约束替换 | M+D/C2 | B/R2 |
| `navigation.0001_initial` | 三层导航树、版本、排序唯一与默认树 | N+D/C1 | B/R2 |
| `navigation.0002_site_content` | 站点设置、静态页、友链、可信来源与默认值 | N+D/C1 | B/R2 |
| `navigation.0003_verification_email_template` | 站点设置增加可空验证码邮件模板 | M/C0 | B/R1 |
| `navigation.0004_navigation_group_nodes` | 节点类型增加仅分组，并替换目标形状约束；不回填数据 | M/C1 | B/R2 |
| `navigation.0005_navigation_default_expanded` | 导航节点增加非空、应用默认关闭的默认展开布尔字段；既有行初始化为 false | M/C0 | B/R1 |
| `navigation.0006_site_hero_media` | 站点单例增加可空 Hero 媒体 ID；不回填既有站点 | M/C0 | B/R1 |
| `navigation.0007_retire_friend_link_logos` | 解除历史友链 Logo 绑定，将无其他引用资产标记待清理，并清空旧兼容列；migration 不删除文件 | M+D/C2 | B/R2 |
| `notifications.0001_notification_foundation` | 通知/receipt、dedupe 与未读索引 | N/C0 | B/R1 |
| `operations.0001_task_run` | TaskRun、幂等、租约和重试索引 | N/C0 | B/R1 |
| `operations.0002_audit_entry` | 永久审计表与检索索引 | N/C0 | B/R1 |
| `operations.0003_runtime_error` | 错误聚合/occurrence、去重与索引 | N/C0 | B/R1 |
| `operations.0004_operationalalert_operationalalertemailwindow_and_more` | 运维告警与邮件窗口 | N/C0 | B/R1 |
| `operations.0005_capacitysnapshot_servicehealthsnapshot_and_more` | 容量/健康快照、约束与活动告警索引 | N/C0 | B/R1 |
| `operations.0006_backuprecord` | 备份记录、单运行租约、周唯一与到期索引 | N/C0 | B/R1 |
| `operations.0007_task_run_cancelled` | TaskRun 增加受控取消终态，并替换尝试/租约/完成形状约束 | M/C0 | B/R1 |
| `opportunities.0001_initial` | 招聘来源、岗位、筛选、检查、审核、收藏和默认筛选基础事实 | N+D/C1 | B/R2 |
| `opportunities.0002_opportunity_check_runtime` | 检查运行/来源明细、结构化快照、岗位状态转换与运行约束 | N+D/C1 | B/R2 |
| `opportunities.0003_opportunity_composite_identity` | 分批回填规范采集标题与固定身份摘要，移除来源+URL 唯一约束，改为来源+身份摘要唯一以允许同列表多个岗位 | M+D/C2 | B/R2 |
| `opportunities.0004_opportunity_default_filters` | 新增规范化公开页默认筛选选择表，把旧单城市/单届别与既有默认核实状态转换为六组多选配置；保留旧列供滚动升级兼容 | N+D/C1 | B/R2 |

## 执行门禁

1. 候选镜像先运行 `manage.py makemigrations --check` 和空库 migrate。
2. 获授权后读取生产 migration plan；无待执行项则跳过迁移与迁移前备份。
3. 有待执行项时先完成新鲜数据库备份，再启用维护页并执行迁移。
4. 迁移失败保留当前应用；迁移成功但新应用健康失败只回滚应用镜像，不反向迁移数据库。
5. 读回 leaf、关键约束/索引、live/ready 和关键请求后才关闭维护页。

`media.0004` 应先于新应用开放附件入口。迁移后的旧应用仍可读取既有图片数据，但一旦写入首条 `ATTACHMENT` 资产，数据库就不得反向恢复旧尺寸与用途约束；应用回滚时数据库保持向前，并临时关闭附件入口。

`navigation.0004` 应先于新应用开放“仅分组”写入。旧应用会忽略新增类型，但一旦写入首条 `GROUP` 节点，旧目标形状约束无法重新应用；应用回滚时数据库保持向前，并在管理入口临时禁用该类型。

`navigation.0005` 应先于新应用读取或写入默认展开字段。它只增加非空布尔列并把既有行初始化为 false，旧应用会忽略该列；应用回滚时数据库保持向前。反向迁移会丢失已配置的展开事实，因此不作为自动回滚手段。

`media.0005` 应先于新应用开放分区默认封面入口。它不回填旧数据；一旦写入首条 `SECTION_COVER` 资产或 `SECTION` 绑定，不得反向恢复旧媒体目标白名单。应用回滚时数据库保持向前，并临时关闭分区封面上传与编辑入口。

`media.0006` 应先于新应用开放 Hero 上传入口。迁移不回填既有媒体；一旦写入首条 `HERO` 或视频资产，不得恢复旧 2 MiB 全图片约束。应用回滚时数据库保持向前，并临时关闭 Hero 上传与配置入口，既有图片读取不受影响。

`navigation.0006` 应与读写 `hero_asset_id` 的新应用同窗口上线，且必须在开放站点 Hero 保存前完成。新列可空且不回填，旧站点仍显示仓库默认图；应用回滚时数据库保持向前并暂停 Hero 配置写入，不自动反向删列。

`navigation.0007` 先由兼容应用停止友链 Logo 新写入和公开读取，再解除历史 `friend_link` Binding、把无其他引用的资产标为 `DELETE_PENDING` 并清空兼容列。迁移事务不访问媒体文件；提交后由既有媒体清理任务删除文件。反向 migration 不恢复绑定、资产状态或旧引用，数据库保持向前；执行前后需统计友链、旧绑定、待删资产与清理失败任务。
