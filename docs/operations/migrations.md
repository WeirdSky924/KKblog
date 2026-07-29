# Migration 验证与兼容记录

本页记录 P12 `QA-001` 对当前 43 条 Django migration 的空库、锁、兼容、备份和回滚限制审计。它是部署输入，不代表生产 migration 已获授权或已经执行。

当前源码可作为部署候选，但没有生产域名、管理员邮箱、Resend 身份或密钥，也没有生产数据库的规模与锁窗口读回。P12 未连接或迁移生产数据库，未创建生产迁移前备份，未执行生产部署或服务重启。

## 当前结构与目标结构

- 当前代码的 11 个 migration leaf 已全部应用到 P12 隔离 PostgreSQL 16；`makemigrations --check --dry-run` 无漂移。
- 目标结构就是仓库当前 models 与 migration graph；P12 不新增 schema，也不回填生产数据。
- 空库读回覆盖 43 条 migration、`pg_trgm`、核心表、命名约束、部分唯一索引、查询索引、延迟触发器和关键外键删除动作。
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
| `comments.0001_initial` | thread/comment、树外键、延迟树触发器与索引 | N/C0 | B/R1 |
| `comments.0002_comment_created_at_clock` | created_at 默认值语义校正 | M/C1 | B/R1 |
| `comments.0003_thread_deep_alert` | thread 增加深层告警时间 | M/C0 | B/R1 |
| `comments.0004_thread_settings_revision` | thread 增加设置修订标识 | M/C0 | B/R1 |
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
| `core.0001_outbox_foundation` | Outbox 表、租约/就绪索引与状态约束 | N/C0 | B/R1 |
| `discovery.0001_article_view_counter` | 浏览计数与 article 级联外键 | N/C0 | B/R1 |
| `discovery.0002_bookmark` | 私有收藏与 account 级联外键 | N/C0 | B/R1 |
| `exchange.0001_initial` | 导入 Job/Item、幂等与形状约束 | N/C0 | B/R1 |
| `exchange.0002_export_jobs` | 导出 Job/Selection、活动任务部分唯一和索引 | N/C0 | B/R1 |
| `media.0001_initial` | asset/binding、大小/用途/slot 约束与索引 | N/C0 | B/R1 |
| `media.0002_owner_cleanup_lifecycle` | asset owner 删除语义改为 SET NULL | M/C1 | B/R1 |
| `media.0003_owner_lifecycle_constraint` | owner 生命周期配对约束 | M/C1 | B/R1 |
| `moderation.0001_initial` | 举报、删除身份与基础约束/队列索引 | N/C0 | B/R1 |
| `moderation.0002_reportrecoverysnapshot` | 举报恢复快照 | N/C0 | B/R1 |
| `moderation.0003_reportappeal` | 一次申诉与状态形状约束 | N/C0 | B/R1 |
| `moderation.0004_article_cases_and_account_closure` | 文章案件、账户关闭快照、约束替换 | M+D/C2 | B/R2 |
| `navigation.0001_initial` | 三层导航树、版本、排序唯一与默认树 | N+D/C1 | B/R2 |
| `navigation.0002_site_content` | 站点设置、静态页、友链、可信来源与默认值 | N+D/C1 | B/R2 |
| `notifications.0001_notification_foundation` | 通知/receipt、dedupe 与未读索引 | N/C0 | B/R1 |
| `operations.0001_task_run` | TaskRun、幂等、租约和重试索引 | N/C0 | B/R1 |
| `operations.0002_audit_entry` | 永久审计表与检索索引 | N/C0 | B/R1 |
| `operations.0003_runtime_error` | 错误聚合/occurrence、去重与索引 | N/C0 | B/R1 |
| `operations.0004_operationalalert_operationalalertemailwindow_and_more` | 运维告警与邮件窗口 | N/C0 | B/R1 |
| `operations.0005_capacitysnapshot_servicehealthsnapshot_and_more` | 容量/健康快照、约束与活动告警索引 | N/C0 | B/R1 |
| `operations.0006_backuprecord` | 备份记录、单运行租约、周唯一与到期索引 | N/C0 | B/R1 |

## 执行门禁

1. 候选镜像先运行 `manage.py makemigrations --check` 和空库 migrate。
2. 获授权后读取生产 migration plan；无待执行项则跳过迁移与迁移前备份。
3. 有待执行项时先完成新鲜数据库备份，再启用维护页并执行迁移。
4. 迁移失败保留当前应用；迁移成功但新应用健康失败只回滚应用镜像，不反向迁移数据库。
5. 读回 leaf、关键约束/索引、live/ready 和关键请求后才关闭维护页。
