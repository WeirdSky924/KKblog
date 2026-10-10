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
| `agents.0001_initial` | 新增 Endpoint/Profile/不可变 Prompt/Invocation、全站 policy、双层 token ledger/reservation/adjustment/reset operation 及约束索引；只 seed 单例默认 policy，不调用 Provider | N/C0 | B/R1 |
| `agents.0002_endpoint_connection_checks` | 新增显式 Endpoint 连接检查事实与约束，并把 token reservation owner 扩展为 Invocation 或 EndpointCheck 二选一 | N+M/C1 | B/R2 |
| `agents.0003_remove_agentendpoint_agent_endpoint_auth_mode_valid_and_more` | 增加加密自定义 API Key、Invocation/EndpointCheck 凭据快照、CUSTOM_API_KEY 认证形状约束及字段长度扩展；不回填明文或调用 Provider | M/C1 | B/R2 |
| `agents.0004_agentinvocationattempt` | 新增不保存正文的 Invocation attempt 事实，记录 phase、strategy、schema/adapter 摘要、usage trust 与安全错误 | N/C1 | B/R2 |
| `agents.0005_remove_agentinvocation_agent_invocation_state_valid_and_more` | 扩展 Invocation 的 REFUSED/INCOMPLETE 终态约束，保持取消与失败形状兼容 | M/C1 | B/R2 |
| `agents.0006_agentendpointcheck_capability_state_and_more` | 为 Endpoint 检查增加 schema 快照、能力策略与严格 schema 支持状态 | M/C1 | B/R2 |
| `agents.0007_agentendpointcheck_capability_adapter_version` | 保存 capability probe 使用的 adapter version，便于安全读回和协议回归 | M/C1 | B/R2 |
| `agents.0008_agentendpoint_reasoning_effort_and_more` | 增加按 Provider/model 映射的 reasoning effort、旧版 thinking budget 及 Endpoint/Check/Invocation 快照字段与约束；不回填旧配置、不调用 Provider | M/C1 | B/R2 |
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
| `learning.0001_initial` | 新增知识文档、审核运行、全站/账户业务配额、自然日 usage 与模型运行 reservation，并 seed `10/3/5/1/100` 默认 policy | N/C0 | B/R1 |
| `learning.0002_review_runtime` | 为审核运行增加派发、TaskRun/Invocation、attempt、分块、业务 reservation 和安全错误快照字段及形状约束 | M/C1 | B/R2 |
| `learning.0003_appeals_access` | 新增正式申诉与管理员原文成功访问历史，包含单 pending、决定形状、trace 去重和安全用途约束 | N/C0 | B/R1 |
| `learning.0004_question_bank_facts` | 新增题库系列/卷、不可变 revision/question、知识点覆盖与独立题库标签，并安装 PostgreSQL 不可变事实触发器 | N+D/C2 | B/R2 |
| `learning.0005_question_generation_runtime` | 增加题库生成运行快照、失败保留与管理员单卷上限字段/约束 | M/C1 | B/R2 |
| `learning.0006_public_question_bank_projection` | 增加公开题库发布时间/答题计数投影与搜索索引 | N+D/C1 | B/R2 |
| `learning.0007_remove_learningappeal_learning_appeal_one_pending_document_and_more` | 申诉双目标唯一约束、管理员锁定/删除事实和显式批量处置字段 | M+D/C2 | B/R2 |
| `learning.0008_question_bank_api_configuration` | 新增默认关闭的题库只读 API 单例开关与 row version | N/C0 | B/R1 |
| `learning.0009_question_bank_api_policy` | 增加精确 Origin 白名单、分钟/每日限流策略及范围约束 | M/C1 | B/R2 |
| `learning.0010_quiz_learning_facts` | 新增答题会话、回答和错题本快照事实及删除/结果约束 | N+D/C2 | B/R2 |
| `learning.0011_quiz_contract_completion` | 完成答题快照兼容回填、索引与不可变结果形状约束 | M+D/C2 | B/R2 |
| `learning.0012_question_bank_point_source_units` | 题库知识点增加来源单元 ID 快照，既有行使用空列表初始化 | M/C0 | B/R1 |
| `learning.0013_generation_batches` | 新增题库分批生成运行事实、约束与索引 | N/C0 | B/R1 |
| `learning.0014_quizattempt_mode_and_more` | 为答题记录增加考试/刷题模式并初始化既有记录为考试模式，增加模式约束；数据库默认值由下一迁移补齐 | M+D/C1 | B/R2 |
| `learning.0015_quiz_attempt_mode_db_default` | 为模式列增加数据库级 `EXAM` 默认值，保持旧应用省略新列时仍能创建答题记录 | M/C0 | B/R1 |
| `media.0001_initial` | asset/binding、大小/用途/slot 约束与索引 | N/C0 | B/R1 |
| `media.0002_owner_cleanup_lifecycle` | asset owner 删除语义改为 SET NULL | M/C1 | B/R1 |
| `media.0003_owner_lifecycle_constraint` | owner 生命周期配对约束 | M/C1 | B/R1 |
| `media.0004_remove_mediaasset_media_asset_size_range_and_more` | 增加附件用途与格式，放宽附件大小并允许其尺寸为空，替换两条约束 | M+D/C1 | B/R2 |
| `media.0005_remove_mediabinding_media_binding_target_registered_and_more` | 增加 `SECTION_COVER` 用途与 `SECTION` 目标，并替换绑定目标白名单约束 | M+D/C1 | B/R2 |
| `media.0006_remove_mediaasset_media_asset_size_range_and_more` | 增加 `HERO` 与 MP4/WebM，视频上限 10 MiB，并增加 Hero 格式/用途约束 | M+D/C1 | B/R2 |
| `media.0007_knowledge_document_media` | 增加独立 `KNOWLEDGE_DOCUMENT` 用途、`learning_document` 目标、2 MiB/Markdown/无尺寸约束，并把 purpose 长度扩展到 32 | M+D/C1 | B/R2 |
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
| `opportunities.0005_opportunity_published_at` | 为岗位增加可空的来源发布时间及倒序索引；不把采集时间或更新时间回填为发布时间 | N/C1 | B/R1 |

## 执行门禁

1. 候选镜像先运行 `manage.py makemigrations --check` 和空库 migrate。
2. 获授权后读取生产 migration plan；无待执行项则跳过迁移与迁移前备份。
3. 有待执行项时先完成新鲜数据库备份，再启用维护页并执行迁移。
4. 迁移失败保留当前应用；迁移成功但新应用健康失败只回滚应用镜像，不反向迁移数据库。
5. 读回 leaf、关键约束/索引、live/ready 和关键请求后才关闭维护页。

`learning.0014` 与 `learning.0015` 必须在同一维护窗口连续执行。`0014` 先为既有答题记录填入 `EXAM` 并增加模式约束；`0015` 随后保留数据库级默认值，供旧应用省略新列时写入兼容。若 `0015` 失败，继续保持维护页并修复前向迁移，不恢复旧应用承接写请求。候选验证失败且尚未开放用户流时可回退应用镜像；一旦已创建刷题记录，旧应用不理解该模式，后续故障应前向修复，不把数据库反向迁移或旧应用回退视为常规恢复路径。

`media.0004` 应先于新应用开放附件入口。迁移后的旧应用仍可读取既有图片数据，但一旦写入首条 `ATTACHMENT` 资产，数据库就不得反向恢复旧尺寸与用途约束；应用回滚时数据库保持向前，并临时关闭附件入口。

`navigation.0004` 应先于新应用开放“仅分组”写入。旧应用会忽略新增类型，但一旦写入首条 `GROUP` 节点，旧目标形状约束无法重新应用；应用回滚时数据库保持向前，并在管理入口临时禁用该类型。

`navigation.0005` 应先于新应用读取或写入默认展开字段。它只增加非空布尔列并把既有行初始化为 false，旧应用会忽略该列；应用回滚时数据库保持向前。反向迁移会丢失已配置的展开事实，因此不作为自动回滚手段。

`media.0005` 应先于新应用开放分区默认封面入口。它不回填旧数据；一旦写入首条 `SECTION_COVER` 资产或 `SECTION` 绑定，不得反向恢复旧媒体目标白名单。应用回滚时数据库保持向前，并临时关闭分区封面上传与编辑入口。

`media.0006` 应先于新应用开放 Hero 上传入口。迁移不回填既有媒体；一旦写入首条 `HERO` 或视频资产，不得恢复旧 2 MiB 全图片约束。应用回滚时数据库保持向前，并临时关闭 Hero 上传与配置入口，既有图片读取不受影响。

`media.0007` 应先于知识 Markdown 上传入口开放。迁移只扩展用途/目标 choices、purpose 长度并替换 media asset/binding 约束，不回填既有数据；一旦写入首条 `KNOWLEDGE_DOCUMENT` 资产或 `learning_document` 绑定，不得反向恢复 16 字符 purpose 与旧目标白名单。隔离 PostgreSQL 已验证正向、反向到 `0006` 和再次正向；Labs 已于 `2026-08-17` 在明确授权后执行，读回 purpose 长度 `32`、四项目标约束和迁移前后 media 行数不变。生产 migration 仍需当次明确授权；应用回滚时数据库保持向前并关闭知识文档入口。

`navigation.0006` 应与读写 `hero_asset_id` 的新应用同窗口上线，且必须在开放站点 Hero 保存前完成。新列可空且不回填，旧站点仍显示仓库默认图；应用回滚时数据库保持向前并暂停 Hero 配置写入，不自动反向删列。

`navigation.0007` 先由兼容应用停止友链 Logo 新写入和公开读取，再解除历史 `friend_link` Binding、把无其他引用的资产标为 `DELETE_PENDING` 并清空兼容列。迁移事务不访问媒体文件；提交后由既有媒体清理任务删除文件。反向 migration 不恢复绑定、资产状态或旧引用，数据库保持向前；执行前后需统计友链、旧绑定、待删资产与清理失败任务。

`agents.0001` 必须先于任何 AGENT 管理、审核或生成入口开放。它只创建新表并 seed `5,000,000` 的全站默认 policy，不保存密钥、不发网络请求、不回填既有业务数据；旧应用会忽略新表。隔离 PostgreSQL 已验证向前、默认 policy/约束读回、反向到 zero 后 `agent_%` 表为 0、再向前成功。Labs 已于 `2026-08-17` 在明确授权后执行并读回默认 policy `5,000,000/row_version 1`；生产数据库 migration 仍需当次明确授权。应用回滚时数据库保持向前并关闭尚未部署的 AGENT 入口。

`agents.0002` 必须先于开放 Endpoint 显式连接检查。空检查数据的隔离 PostgreSQL 已验证从 `0002` 反向到 `0001` 并再次前向成功，且读回连接检查与 reservation owner 约束；一旦存在 EndpointCheck 或其 reservation，反向会删除检查事实且旧 owner 约束无法容纳检查预留，因此不得作为运行中环境的应用回滚手段。Labs 已于 `2026-08-17` 在明确授权后执行并读回 `agent_endpoint_check`、`agent_token_reservation_owner_shape` 及相关索引；生产 migration 仍需当次明确授权。应用回滚时数据库保持向前，并关闭连接检查与“AI 配置”一级组入口。

`agents.0003` 必须先于开放自定义 API Key 的 Endpoint 管理入口。迁移只增加加密密文列、凭据快照列和认证形状约束，不读取或回填真实 API Key、不调用 Provider；隔离 PostgreSQL 已验证前向和约束读回。Labs 已于 `2026-08-18` 在明确授权后执行，读回三张表的 `api_key_ciphertext*` 列、migration leaf `0003`、`health/live=200`、`health/ready=200`；生产 migration 仍需单独授权。应用回滚时数据库保持向前并关闭自定义凭据写入入口。

`agents.0004` 至 `agents.0007` 必须先于开放 Invocation attempt 观测、拒答/截断终态和 profile schema capability probe；`agents.0008` 必须先于开放 reasoning effort 配置。它们只增加 attempt/能力/推理配置快照字段与约束，不读取 Prompt、正文或密钥，不派发 Provider 请求；隔离 PostgreSQL 需验证 attempt 终态、schema/strategy/adapter version、推理参数和旧数据默认值读回。Labs 已应用到 `0007`，`0008` 需单独授权后执行；生产迁移仍需当次明确授权。应用回滚时数据库保持向前并关闭对应观测、capability probe 和推理配置入口。

`learning.0001` 必须先于知识文档提交或审核入口开放。它只创建 7 张 learning 表并 seed 全站默认业务配额 `10 uploads / 3 pending / 5 generations / 1 concurrent / 100 banks`，不读取媒体正文、不派发任务、不调用 Provider、不回填既有业务数据。隔离 PostgreSQL 已验证前向、默认 policy/条件唯一/状态约束读回、反向到 zero 后 `learning_%` 表为 0、再次前向成功。Labs 已于 `2026-08-17` 在明确授权后执行，读回 7 张表、默认 policy、关键约束及 6 张业务表合计 0；生产 migration 仍需当次明确授权。一旦写入知识文档或 reservation，应用回滚时数据库保持向前并关闭尚未部署的入口。

`learning.0002` 必须先于派发或领取知识审核任务。既有 review 行扩展为 `attempt_count=0`、`dispatch_required=true`，其余运行引用为空；迁移不派发任务、不调用 Provider。隔离 PostgreSQL 已验证前向、10 个字段/5 条约束读回、反向到 `0001` 字段为 0、再次前向成功。Labs 已于 `2026-08-17` 根据当前 Goal 持续授权执行，读回 migration/字段/约束与空 review 表，并 warm restart worker 读回审核任务注册；生产 migration 仍仅在实际生产 Goal 明确需要时执行。一旦派发任务或写入运行快照，应用回滚时数据库保持向前并暂停审核 worker。

`learning.0003` 必须先于开放知识文档申诉或管理员原文访问。它只创建 Appeal/Access 两表，不读取正文、不派发审核、不回填既有文档。隔离 PostgreSQL 已验证前向、单 pending/决定/trace 约束读回、反向到 `0002` 表数恢复、再次前向成功；Labs 已根据持续授权执行并读回两表为空、ready 200。生产 migration 仍仅在实际生产 Goal 明确需要时执行；应用回滚时数据库保持向前并关闭申诉/访问历史入口。
