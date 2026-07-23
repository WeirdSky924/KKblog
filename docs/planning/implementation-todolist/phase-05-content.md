# P5 文章、修订、分类与发布任务（11）

退出门禁：文章三指针、分类、发布/排期、冲突、恢复、删除和容量/审计/任务基础集成完成。

### CNT-001 建立 Article/不可变 Revision 与正交状态 schema
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：使用 ULID 文章/修订、不可变 sequence、working/published/scheduled 三指针、publication/deletion 正交字段与 row_version；作者不可转移。
- 来源：访谈 Q001-Q002、Q036-Q053、Q291；ADR-002；`data/02-identity-content-fields.md` §Article/Revision；`flows/02-article-state-machine.md`。
- 依赖：前置 `FND-003`、`FND-006`、`ACC-001`；后续 `CNT-002`、`CNT-010`、`CNT-011`、`CNT-004`、`CNT-006`、`CNT-008`、`EXC-001`、`QA-001`、`QA-006`。
- 文件：`apps/content/models/{article,revision}.py`、migrations、policy/service skeleton、tests。
- 边界：正文/草稿/版本只在 PostgreSQL；Revision 不原地更新；不压成单 status、不转移 owner、不存文件正文。
- 影响：数据：核心聚合/约束/索引；权限：author FK；审计：版本 ID；缓存/异步/媒体/通知后续。
- 测试/验收：RED 指针同文章、sequence唯一、软删时间成对、格式/正文列匹配；migration 与真实 DB 读回。
- 风险/停止：指针可跨文章、revision 可 update 或 schema 无法支持旧发布稳定性即停止。
- 证据：RED `/root/.local/bin/uv run pytest apps/content/tests/test_cnt001.py -q` 收集期退出 2，准确报告 `apps.content.models` 缺失。新增 ULID Article/ArticleRevision、working/published/scheduled 三指针、发布/删除正交字段、row version、完整正文/摘要/可见性/评论快照列，以及 sequence/正文/摘要/排期/删除形状约束；PostgreSQL 复合外键保证三指针与 based-on/restore-source 均属于同一文章，数据库 trigger 阻止作者转移、修订 UPDATE 和独立 DELETE，父 Article 使用数据库 `ON DELETE CASCADE` 仍可清理完整聚合。真实 PostgreSQL 聚焦 GREEN 退出 0，`13 passed`；账户、媒体绑定与架构回归退出 0，`28 passed`。隔离 migration 从零应用与反向/重放均退出 0；catalog 读回三条指针复合 FK、revision article `ON DELETE CASCADE`、正文/sequence/排期/删除约束和两条不可变 trigger。migration drift、Django check、Ruff lint/format 与 `git diff --check` 均退出 0。一次未显式设置 settings 的 migration 误落到开发 SQLite 后立即读回文章/修订均为 0，只反向撤销本轮 content migration，并确认 content migration 记录和 article 表均归零；未执行生产 migration、生产数据写入或 Git 交付。
- 授权：schema/隔离 migration `否`；生产 migration `是`。

### CNT-002 实现新建、格式选择、云草稿与正文/媒体校验
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：作者新建默认大众/草稿/评论开启且访客可看评/顶层评论；选 Markdown/TipTap 后普通编辑不可改；显式保存创建新 Revision。
- 来源：访谈 Q036-Q037、Q234、Q254、Q262、Q314、Q317；`contracts/01-application-services.md` §content；`modules/03-content-versioning.md`。
- 依赖：前置 `CNT-001`、`MED-003`、`MED-007`、`DEC-005`；后续 `CNT-003`、`CNT-006`、`EXC-003`、`AUT-001`、`AUT-002`、`AUT-003`、`QA-003`、`QA-006`。
- 文件：content create/save services、snapshot DTO、body limit/summary validation、tests。
- 边界：标题≤30可重复；正文默认≤`2 MiB`且不计图片，管理员可配范围仅为`64 KiB`至`2 MiB`；本地草稿不由 content 存；不允许普通格式切换。
- 影响：数据：Article/Revision；权限：仅作者；审计：版本元数据；缓存无；异步：outbox可无；媒体：绑定；通知无。
- 测试/验收：RED 默认值、两格式、正文 `64 KiB`/`2 MiB` 配置与正文边界、媒体 owner/purpose、非作者 POST、普通格式切换；DB读回新不可变修订。
- 风险/停止：保存覆盖旧行、正文限制只在前端或绑定失败留下 ACTIVE 孤儿即停止。
- 证据：RED `pytest apps/content/tests/test_cnt002.py -q` 收集期退出 2，准确报告 `apps.content.public` 缺失。新增不可变 `ArticleSnapshot`、`create_article`/`save_revision`、默认 `2 MiB` 且仅允许 `64 KiB..2 MiB` 的 `ArticleBodyLimit`，统一验证 30 字标题、摘要模式、两种正文序列化、P4 sanitizer 与媒体引用集合；启用作者、对象 owner、容量和 row version 均由服务端重判，普通保存禁止格式切换并创建新 Revision。accounts/operations/media 分别提供启用作者、文字容量和同 Article 修订媒体快照公共端口；同一资产可保留在同文章多个历史 Revision，跨文章、跨 owner、错 purpose 或错 slot 均失败并回滚新 Revision/指针/Binding。真实 PostgreSQL 聚焦 GREEN 退出 0，`10 passed`，精确 `64 KiB`/`2 MiB` 与 +1 字节边界、Markdown/TipTap、旧修订稳定、row version、媒体文件/Binding 读回均通过；content/media/accounts/架构相关回归退出 0，`111 passed`。migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。该卡只交付 content 服务契约，未提前创建 P10 authoring 页面；未执行生产数据写入、生产 migration 或 Git 交付。
- 授权：`否`。

### CNT-010 实现分区唯一管理、发布要求与未知分区
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：管理员按唯一名称 CRUD 分区；普通发布必须一个分区；删除后文章进入未知分区，只在首页/标签发现，导入无法映射可同样进入。
- 来源：访谈 Q055-Q057、Q256、Q279；`data/02-identity-content-fields.md` §Section；`flows/02-article-state-machine.md` §分类例外。
- 依赖：前置 `CNT-001`、`OBS-004`；后续 `CNT-003`、`DSC-003`、`EXC-002`、`ADM-005`、`QA-001`、`QA-003`、`QA-006`。
- 文件：section model/service/query/migration、publication validator、tests。
- 边界：分区仅名称；不级联删文章；未知不是伪造“未分类”记录，不进入导航/分区页。
- 影响：数据：Section/revision FK；权限：admin写；审计：CRUD；缓存：列表失效；异步/媒体/通知无。
- 测试/验收：RED 名称并发唯一、删除关联、普通发布缺失、导入例外；DB与发现query读回。
- 风险/停止：删除分区使文章消失/被删、旧URL泄露或缓存未失效即停止。
- 证据：RED `pytest apps/content/tests/test_cnt010.py -q` 收集期退出 2，准确报告 Section owner 缺失。新增 UUID Section、NFKC+Unicode casefold 唯一规范名、管理员 create/rename/delete 服务、稳定 `section_list` 查询、发布分类 validator、事务 AuditEntry 与 `section.changed.v1` Outbox；未知分区始终以 Revision `section_id=NULL` 表示，不伪造记录。PostgreSQL 使用 deferrable `ON DELETE SET NULL`，不可变 trigger 仅允许分区物理删除引起且其他列逐项不变的 `section_id -> NULL`，其余 Revision UPDATE 仍拒绝。真实 PostgreSQL 聚焦 GREEN 退出 0，`3 passed`，并发 `Straße/STRASSE` 只有一个成功；删除读回 Article 仍存在、Revision 进入未知、导航查询为空、普通发布拒绝而导入例外放行，Audit/Outbox 各与业务同事务。CNT-001/002、审计与架构回归退出 0，`33 passed`；隔离 migration `0002 -> 0001 -> 0002` 反向/重放均退出 0，catalog 读回规范名 UNIQUE、section FK `ON DELETE SET NULL` 和受控 trigger 分支。migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。未提前创建 P11 管理页面，未执行生产 migration、生产缓存动作或 Git 交付。
- 授权：`否`。

### CNT-011 实现标签提议、审核、十标签与删除恢复
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：作者可提议待审标签并立即显示，管理员直接建/通过/驳回；驳回移除并通知；全站标签删除保留历史，恢复合法关联；每篇≤10。
- 来源：访谈 Q054、Q058-Q061、Q257-Q258、Q280；`data/02-identity-content-fields.md` §Tag；`flows/02-article-state-machine.md` §分类例外。
- 依赖：前置 `CNT-001`、`FND-005`、`OBS-004`；后续 `CNT-003`、`DSC-003`、`OBS-008`、`EXC-002`、`ADM-005`、`QA-001`、`QA-003`、`QA-006`。
- 文件：tag/proposal/history models、classification services/events、constraints/queries/tests。
- 边界：作者不能直接激活全站标签；删除旧链接为空；恢复超过10个记录冲突并通知管理员，不能静默丢弃。
- 影响：数据：Tag/RevisionTag/ArticleTag/History；权限：author提议/admin审核；审计：管理员动作；缓存：列表/文章失效；异步：通知事件；通知：作者/冲突；媒体无。
- 测试/验收：RED 规范名并发、10标签并发、驳回移除、删除/恢复、超限冲突；真实DB锁/索引读回。
- 风险/停止：表单层独占约束、历史关联漂移或恢复制造幽灵/超限标签即停止。
- 证据：RED `pytest apps/content/tests/test_cnt011.py -q` 收集期退出 2，准确报告 Tag 聚合缺失。新增 Tag `PENDING/ACTIVE/REJECTED/DELETED` 生命周期、RevisionTag 历史快照、ArticleTag 当前投影、TagAssociationHistory 和 TagRestoreConflict；作者同名提议以 NFKC+Unicode casefold 并发收敛，待审标签可被多位作者立即使用，管理员直建/通过/驳回/删除/恢复均写事务审计与版本化事件。驳回从所有当前文章移除并为所有受影响作者写 `tag.reviewed.v1`；删除保留历史，恢复只处理仍存在文章，十标签超限持久化冲突并一次写 `tag.restore_conflict.v1`，后续腾出位置可重入恢复并标冲突解决。保存修订锁 Article 后锁 Tag，同事务写 RevisionTag/ArticleTag；PostgreSQL trigger 再锁 Article 并拒绝第 11 个投影，数据库级 Article/Revision 级联 FK 保证物理清理无悬挂。真实 PostgreSQL 聚焦 GREEN 退出 0，`4 passed`：同名并发、两作者待审共用、审核通知、双保存 10 标签裁决、raw 第 11 个拒绝、删除/恢复/超限/重入均通过；content/media/Outbox/审计/架构回归退出 0，`58 passed`。隔离 migration `0003 -> 0002 -> 0003` 反向/重放均退出 0，catalog 读回 live-name partial unique、两条 `ON DELETE CASCADE` FK 和 tag-limit trigger；migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。最终 Notification Receipt 留给明确后续 `OBS-008`，未创建 P11 标签页面，未执行生产 migration、生产通知或 Git 交付。
- 授权：`否`。

### CNT-003 实现终稿审查、立即发布与已发布重发
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：安全终稿审查令牌后立即发布；读者只见 published 指针；已发布编辑仍显示旧版，显式重发或作者偏好自动重发均创建新修订并保留首次发布时间。
- 来源：访谈 Q048-Q053、Q263-Q264、Q298；`flows/02-article-state-machine.md` §创建/发布；`modules/07-authoring-workbench.md` §发布审查。
- 依赖：前置 `CNT-002`、`CNT-010`、`CNT-011`、`MED-007`、`FND-005`；后续 `CNT-004`、`CNT-005`、`CNT-007`、`DSC-002`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：publication services/review token、author preference bridge、events/cache hooks/tests。
- 边界：首次发布/历史恢复必须终稿审查；自动重发仍做完整校验；UI 不能把 202/保存当发布完成。
- 影响：数据：发布指针/时间；权限：作者；审计：版本/事件；缓存：失效事件；异步：outbox；媒体：发布绑定；通知无默认。
- 测试/验收：RED 编辑发布文不变读者版、令牌重放/过期、分区缺失、自动偏好；读者/作者双会话读回。
- 风险/停止：发布指针先于校验、首次 published_at 被重置或缓存仍返回旧/私密内容即停止。
- 证据：RED `pytest apps/content/tests/test_cnt003.py -q` 收集期退出 2，准确报告 PublicationReviewGrant 缺失。新增 15 分钟一次性终稿审查 grant：原始随机 token 只返回调用者，PostgreSQL 仅存 SHA-256 摘要、actor/article/revision/row version、过期与消费时间；复合 FK 阻止跨文章 grant。`prepare_publication` 与 `publish_article` 均在 Article 行锁下重判启用作者、owner、row version、working revision、分区、标签、ACTIVE 媒体 Binding 与统一 sanitizer；执行后原子消费同目标全部 grant、切 published 指针、清排期字段并写 `article.published.v1`，事件不含正文/token。读者查询只取 published 指针并执行基础 visibility/作者启用策略；保存已发布文章仍读旧版，显式重发和 `republish_saved_revision` 偏好桥均复做完整校验，首次 `published_at` 永不重置，历史恢复仍强制终稿审查。真实 PostgreSQL 聚焦 GREEN 退出 0，`5 passed`；token 摘要/重放/过期/越权、执行期分区删除、旧/新读者版本与显式/自动重发均读回。content/media renderer/Outbox/架构回归退出 0，`80 passed`；隔离 migration `0004 -> 0003 -> 0004` 反向/重放均退出 0，catalog 读回复合 FK、摘要形状、唯一摘要和 expires-after-create 约束。migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。浏览器 authoring/review 页面由 P10 消费此契约，本卡未提前建立第二页面 owner；未执行生产 migration、生产缓存/通知或 Git 交付。
- 授权：`否`。

### CNT-004 实现排期、取消与幂等定时发布
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：终稿审查后以 Asia/Shanghai 输入、UTC 存储，锁定 scheduled revision；作者可取消；每分钟扫描到期事实，双 Worker 只发布一次。
- 来源：访谈 Q048-Q049、Q224、Q301；`flows/02-article-state-machine.md` §发布状态；`contracts/05-background-tasks.md` §定时发布。
- 依赖：前置 `CNT-001`、`CNT-003`、`RUN-002`、`OBS-006`；后续 `CNT-009`、`AUT-001`、`AUT-005`、`QA-003`、`QA-004`、`QA-006`。
- 文件：schedule/cancel services、publication task、Beat schedule、TaskRun bridge/tests。
- 边界：不依赖长期 ETA；任务执行时重判作者/删除/隐藏/修订/时间/分类；排期后继续编辑不漂移目标。
- 影响：数据：scheduled 指针/时间；权限：作者；审计：事件；缓存：发布后失效；异步：Celery；媒体：约束重判；通知：终败后。
- 测试/验收：RED 过去时间、取消竞态、双 Worker、作者禁用、修订变化、前两次失败第三次成功；真实 worker smoke。
- 风险/停止：任务按入队快照盲发、Beat 成为事实或重复发布即停止。
- 证据：RED `pytest apps/content/tests/test_cnt004.py -q` 收集期退出 2，准确报告排期服务缺失。新增终稿 grant 驱动的 `schedule_article`、作者取消、数据库到期查询、可重入 `publish_scheduled_article` 和两个 Celery 薄入口；上海 naive 输入明确绑定 `Asia/Shanghai` 后 UTC 存储，Article 锁定 scheduled revision，后续保存只移动 working pointer。任务执行时重新检查作者启用、删除、排期状态/指针/时间、RevisionTag 快照、分区、媒体、sanitizer 与可注入管理遮罩；业务失效明确取消转草稿，旧/重复任务返回 stale，不依赖 ETA 或 Beat 文件。每篇任务使用 `article:<id>:schedule:<revision>` TaskRun 幂等键，dispatcher 每分钟扫描数据库事实；1/5/30 分钟重试与三次终态复用 operations owner。真实 PostgreSQL 聚焦 GREEN 退出 0，`6 passed`：过去时间、UTC 读回、取消、编辑不漂移、双线程仅一条发布事件、作者禁用、分区删除、遮罩、TaskRun 首成，以及前两次 retry_wait/第三次 succeeded 均通过；content/TaskRun/任务入口/架构回归退出 0，`56 passed`。临时真实 solo Worker 经隔离 Redis broker 投递后读回 Article `PUBLISHED`、scheduled pointer 为空，TaskRun `attempt=1/status=succeeded/result_ref=...:published`；Worker 随后温和停止且进程读回为空，未启动 Beat。Celery 在主机 root smoke 中输出非生产 superuser 警告；未重启 Compose/生产 Worker，最终部署仍需按容器非特权用户复核。Beat 注册值 60 秒、migration drift、Ruff lint/format 与 `git diff --check` 均退出 0；未执行生产任务、生产排期或 Git 交付。
- 授权：代码/隔离 worker `否`；启动真实 worker/Beat `是`。

### CNT-005 实现文章可见性策略、管理员只读例外与即时变更
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：PUBLIC/AUTHENTICATED/PRIVATE 服务端矩阵统一；变更已发布可见性立即创建/发布新修订并移出/加入发现；管理员可读他人所有状态但按日通知，不能代编/发布。
- 来源：访谈 Q001-Q007、Q255、Q290、Q302-Q305；ADR-005；`contracts/02-authorization-matrix.md` §文章；`reference/01-requirements-resolution.md`。
- 依赖：前置 `CNT-003`、`ACC-005`、`FND-005`；后续 `CNT-009`、`DSC-002`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`CMT-001`、`CMT-011`、`ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：content policies/queries/admin exception、visibility service/events、capability DTO/tests。
- 边界：无权 PRIVATE/草稿/定时/冷静期返回统一404；管理员例外只读/隐藏/删除/恢复；模板 capability 不授权。
- 影响：数据：新修订/遮罩查询；权限：完整矩阵；审计：管理员写由 moderation；缓存：即时失效；异步：通知事件；媒体：跟随修订；通知：管理员查看按日。
- 测试/验收：参数化四身份×状态、伪造 POST、同日重复查看；浏览器直接 URL + Outbox 通知事实事件读回，最终 Receipt 由 `OBS-008` 回归。
- 风险/停止：查询暴露无 actor QuerySet、错误差异泄露存在性或管理员可改他人设置即停止。
- 证据：RED `pytest apps/content/tests/test_cnt005.py -q` 收集期退出 2，准确报告 actor-aware access 契约缺失。新增显式 `article_for_reader/author/admin` 查询与 ArticleView capability DTO，不暴露无 actor QuerySet；访客访问登录可见发布版得到 `ArticleLoginRequired`，私人、草稿、无发布指针、软删冷静期、作者禁用与读者遮罩统一 `ArticleNotFound`。管理员例外只在 admin 查询启用，可读 working/published、私人/草稿/冷静期/禁用作者内容；他人查看以 `(admin, author, article, Shanghai date)` PostgreSQL UNIQUE 去重并事务写 `article.admin_viewed.v1`，自有文章走作者语义不通知。所有 save/publish/visibility 命令仍重判 owner，伪造管理员修改他人内容被拒绝。`change_visibility` 锁 Article，从当前 published Revision 复制不可变内容/标签/媒体快照并立即切新 published 指针，不发布尚未完成的 working 正文、不重置 `published_at`，保留独立排期并写 `article.visibility_changed.v1` 供发现/缓存即时失效。真实 PostgreSQL 聚焦 GREEN 退出 0，`8 passed`，覆盖三可见性×三读者身份、管理员例外、草稿/冷静期、禁用作者、上海跨日去重、管理员自有查看、待发布编辑稳定与伪造写；content/accounts/Outbox/架构回归退出 0，`75 passed`。隔离 migration `0005 -> 0004 -> 0005` 反向/重放均退出 0，catalog 读回 daily unique 与三条 FK；migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。最终 Notification Receipt 由明确后续 `OBS-008` 回归，article/admin HTTP 页面分别由 P6/P11 消费本契约；未执行生产通知、缓存、migration 或 Git 交付。
- 授权：`否`。

### CNT-006 实现行锁版本令牌与编辑冲突解析契约
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：两个同基线保存只有一个成功；409 返回安全版本元数据并冻结编辑，作者选择基线后获新令牌继续，published 指针不变。
- 来源：访谈 Q296；`flows/02-article-state-machine.md` §并发编辑；`modules/07-authoring-workbench.md` §并发冲突。
- 依赖：前置 `CNT-001`、`CNT-002`；后续 `CNT-007`、`AUT-004`、`QA-003`、`QA-006`。
- 文件：save service row lock、edit token/conflict DTO、409 mapping、tests。
- 边界：不自动 last-write-wins、不合并正文、不在错误 payload 露他人/私人内容；冲突未解不能保存/发布。
- 影响：数据：row_version/新修订；权限：作者；审计：基线元数据；缓存/异步/媒体/通知无额外。
- 测试/验收：RED 两事务同令牌、选择旧/当前基线、冲突后发布禁止；真实 PostgreSQL 并发读回。
- 风险/停止：只靠表单版本、SQLite 测试或冲突覆盖 published_revision 即停止。
- 证据：RED `pytest apps/content/tests/test_cnt006.py -q` 收集期退出 2，准确报告 ArticleEditGrant 缺失。新增 12 小时 ArticleEditGrant：原 token 只返回作者，PostgreSQL 仅存 SHA-256 摘要、actor/article/baseline revision/row version/state/expiry，复合 FK 保证基线同文章。`open_edit_session` 发 ACTIVE grant；token 保存锁 Article 后验证 grant，成功消费旧 grant、创建新不可变 Revision 并发下一 grant，row version 失配则提交 `CONFLICT` 状态后返回只含 revision ID/sequence/time 的安全 DTO。存在任一未解决冲突时普通 `save_revision` 与终稿发布均服务端拒绝；`resolve_edit_conflict` 只接受同文章历史 revision，统一替换该作者的冲突 grant，返回完整本人快照与新 token，后续 Revision 的 based_on 精确指向所选基线。真实 PostgreSQL 聚焦 GREEN 退出 0，`3 passed`：双线程同基线仅一个保存、另一冲突，published pointer 保持旧版；绕过 token 保存/发布均冻结，选择旧基线后可继续；token 摘要、篡改和跨 actor 均通过。全部 content/架构回归退出 0，`55 passed`。隔离 migration `0006 -> 0005 -> 0006` 反向/重放均退出 0，catalog 读回摘要形状/唯一、expires-after-create、actor/article/revision FK 和 baseline 同文章复合 FK；migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。409 HTTP 映射与冻结 UI 留给 P10 authoring 消费此稳定错误/DTO，不提前建立第二 owner；未执行生产 migration、生产数据或 Git 交付。
- 授权：`否`。

### CNT-007 实现完整版本时间线与历史恢复
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：作者查看全部版本元数据/安全差异，恢复标题、正文、格式、封面、可见性、分区、标签、评论设置；恢复生成新工作修订并再走终稿发布。
- 来源：访谈 Q052-Q053、Q298、Q321；`flows/02-article-state-machine.md` §版本恢复；`data/02-identity-content-fields.md` §ArticleRevision。
- 依赖：前置 `CNT-003`、`CNT-006`；后续 `EXC-003`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：revision queries/prepare+confirm restore services、restore metadata/tests。
- 边界：不覆盖/删除历史；已发布恢复前读者仍见旧版；恢复格式可作为明确例外但需记录来源。
- 影响：数据：新Revision/restore_source；权限：作者；审计：版本ID；缓存：发布后；异步无；媒体：完整绑定快照；通知无。
- 测试/验收：RED 全字段恢复、历史来源保留、冲突令牌、富文本↔Markdown历史；DB指针/媒体读回。
- 风险/停止：恢复直接切 published、丢恢复前状态或恢复已删除媒体无明确错误时停止。
- 证据：交付前聚焦 RED `pytest apps/content/tests/test_cnt007.py -q` 退出 1，`2 failed` 精确暴露 `ArticleRestoreGrant` 模型已存在但 `0007` 持久化表缺失。补齐 15 分钟一次性恢复 grant，原 token 只返回作者、数据库仅存 SHA-256 摘要，并以 `(article_id, source_revision_id)` 复合 FK 保证历史来源属于同一文章；作者时间线只返回 sequence/时间/格式/可见性/来源和三指针标记，不返回标题或正文。prepare/confirm 均锁 Article 并重判启用作者、owner、row version、未解决编辑冲突、标签与媒体状态；确认后复制标题、正文、原格式、封面、可见性、分区、标签、摘要和评论设置，创建 `based_on=恢复前工作版`、`restore_source=历史来源` 的新不可变 Revision，只移动 working 指针并消费 grant，published 指针保持旧版，自动重发明确返回 `content.final_review_required.v1`。真实 PostgreSQL 聚焦 GREEN 退出 0，`5 passed`：全字段/标签/媒体快照、发布指针稳定、冲突 token、正文不进入时间线、Q321 导入后的 Markdown 当前版恢复原 TipTap 格式，以及历史标签/媒体失效的明确错误与事务回滚均读回；全部 content 与架构回归退出 0，`60 passed`。隔离 migration `0007 -> 0006 -> 0007` 反向/重放均退出 0，catalog 读回摘要形状、唯一摘要、expires-after-create、actor/article/source FK 和来源同文章复合 FK；migration drift、Ruff lint/format 与 `git diff --check` 均退出 0。HTTP 时间线/终稿确认页面由 P10 authoring 消费稳定 query/service，本卡未提前创建第二页面 owner；未执行生产 migration、生产数据或 Git 交付。
- 授权：`否`。

### CNT-008 实现文章 7 天软删除、恢复与物理清理 Saga
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：作者/管理员删除进入7天冷静期并404；期限内恢复原状态；到期删除正文/版本/媒体/评论，保留举报/申诉/审计稳定引用。
- 来源：访谈 Q046-Q047、Q284、Q290、Q315；`flows/02-article-state-machine.md` §删除；`contracts/05-background-tasks.md` §文章物理删除 Saga。
- 依赖：前置 `CNT-001`、`MED-006`、`FND-005`、`OBS-004`、`OBS-006`；后续 `CMT-011`、`EXC-004`、`AUT-001`、`QA-002`、`QA-003`、`QA-004`、`QA-006`。
- 文件：deletion/restore/purge services/tasks、tombstone snapshot、cross-domain ports/tests。
- 边界：软删期不删媒体/评论；文件删除在DB提交后；冷静期可导出；过期后作者也404。
- 影响：数据：deleted/purge字段与级联；权限：作者/管理员；审计：动作；缓存：即时失效；异步：小时扫描/Saga；媒体：到期删；通知：管理员他人动作。
- 测试/验收：RED 7天边界、恢复、双Worker、DB提交后文件失败、案件保留；真实DB+临时媒体读回。
- 风险/停止：级联误删案件/审计、先删文件或恢复算法覆盖管理员隐藏即停止。
- 证据：RED `pytest apps/content/tests/test_cnt008.py -q` 收集期退出 2，准确报告永久 `ArticleTombstone` 与删除契约不存在。新增正交软删除/恢复服务：作者只能操作自己文章，管理员删除他人文章后只有管理员可直接恢复；服务锁 Article、校验 row version，设置精确 7 天 `deleted_at/purge_after`，不改 working/published/scheduled 三指针，并把原发布状态、三指针、排期/发布时间、作者、删除 actor 与管理员动作标记写入不含标题/正文且无 Article FK 的安全墓碑。恢复期限为左闭右开，严格在 deadline 前从墓碑恢复原状态并清除墓碑；读者冷静期始终 404，作者可在期限内只读并恢复，deadline 起作者和时间线也 404；管理员隐藏投影未被读写。删除/恢复同事务写永久 AuditEntry 与 `article.deleted/restored.v1`，管理员动作携带作者 recipient，最终 Notification Receipt 由 `OBS-008` 消费。物理清理锁 Article 和墓碑并校验任务 deadline，先调用 comments owner 事务端口，再由 media owner 批量解除全部历史 Revision Binding、仅把无其他引用资产标 `DELETE_PENDING`，写 `article.purge_requested.v1` 与 `purged_at` 后删除数据库聚合；文件删除只注册 `on_commit`，失败保留待删事实，由既有每分钟媒体任务重试。comments app 尚未在 P5 存在，当前无评论数据时返回 0；未来 app 一旦安装却未由 `CMT-011` 注册清理端口会 fail closed，测试替身证明评论端口失败会回滚文章、Binding、资产状态与文件。新增每小时扫描、`article:{id}:purge:{deadline-us}` TaskRun 幂等任务；双 Worker 读回仅 `purged/already_purged`。真实 PostgreSQL 聚焦 GREEN 退出 0，`6 passed`，覆盖发布版隐藏/恢复、7 天边界、删除期间排期不被旧任务取消、管理员权限/审计/事件、多历史 Revision 共享媒体只释放一次、数据库提交后文件删除失败及后续成功重试、comments 失败全回滚、双 Worker、TaskRun 与 Beat；content/media/operations/架构相关回归退出 0，`148 passed`。隔离 migration `0008 -> 0007 -> 0008` 反向/重放均退出 0，catalog 读回 publication/schedule/deadline/purged-at CHECK、永久主键与 0 个 FK。真实隔离 Redis solo Worker 经 broker 投递后读回 TaskRun `succeeded/attempt=1/result_ref=...:purged`、Article 0、已清理墓碑 1、purge 事件 1；Worker 随后温和停止且进程读回为空。主机 root Worker 仅用于隔离 smoke 并输出非生产 superuser 警告；部署仍须容器非特权用户。migration drift、Django 架构契约、Ruff lint/format 与 `git diff --check` 均退出 0；未提前创建 P7 comments/P10/P11 页面，未执行生产物理清理、生产 migration 或 Git 交付。
- 授权：隔离测试 `否`；生产物理清理 `是`。

### CNT-009 收敛作者禁用/启用与文章排期生命周期
- 元数据：状态 `完成`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：消费账户事件：禁用作者隐藏全部已发布并取消定时转草稿；启用只恢复因禁用遮罩的文章，不恢复排期；历史评论不受影响。
- 来源：访谈 Q299-Q301；`flows/02-article-state-machine.md` §作者禁用遮罩；`contracts/04-events-errors.md` account事件。
- 依赖：前置 `ACC-011`、`CNT-004`、`CNT-005`、`FND-005`；后续 `DSC-008`、`ADM-002`、`QA-002`、`QA-003`、`QA-006`。
- 文件：content account-event consumers、disabled mask projection/policy、tests。
- 边界：不直接改原 visibility；不解除管理员隐藏/软删除；重复事件幂等；accounts 不写文章表。
- 影响：数据：遮罩/排期转草稿；权限：读/写；审计：账户动作关联；缓存：全相关失效；异步：outbox消费；通知：角色通知由OBS；媒体无删。
- 测试/验收：RED 禁用/启用组合、重复事件、排期到点竞态、缓存命中；跨域读回。
- 风险/停止：简单 visible=true 恢复、排期仍自动发布或事件顺序导致文章泄露即停止。
- 证据：RED `pytest apps/content/tests/test_cnt009.py -q` 收集期退出 2，准确报告 content account-status consumer 不存在。新增无 Account FK 的 `AuthorContentMask` 投影，保存 masked、最后 `occurred_at/event_id/event_type` 并以 `(occurred_at,event_id)` 裁决乱序；`consume_account_status_event` 复用 core `event_id + consumer_name` 持久去重，只接受 schema v1、空 payload 的 account disabled/enabled 信封。禁用事件把遮罩设为 true，并锁定/取消该事件时刻之前建立的全部 SCHEDULED Article：清三项排期事实、转 DRAFT、递增 row version、逐篇写 `article.schedule_cancelled.v1`；同事务同步未清理 ArticleTombstone 的原排期快照，保证冷静期恢复也不复活排期。启用事件只在顺序更新时把遮罩设为 false，不改 visibility、发布指针、管理员隐藏、软删除或任何排期；较旧禁用事件仍只取消其发生时已存在的旧排期，不会取消较新启用后建立的排期。Article 新增 `scheduled_at` PostgreSQL 事实，schedule/publish/cancel/删除恢复全链路写清；reader、published query、author timeline、发布/排期命令和 article media access 均读取持久遮罩，因此 Account 已启用但 enabled 事件尚未消费时仍 fail closed。投影变化写 `article.author_mask_changed.v1` 供 discovery 缓存/索引按作者失效，事件注册表已同步；历史评论 owner 未被读取或修改。真实 PostgreSQL 聚焦 GREEN 退出 0，`5 passed`：真实 accounts disabled/enabled Outbox、重复消费、已发布可见性与媒体、管理员独立遮罩、启用事件滞后、普通与冷静期排期取消、不自动恢复、乱序旧/新排期裁决，以及到点发布 Worker 与 consumer 双线程竞态最终只有一次取消均读回；accounts/content/media/Outbox/架构相关回归退出 0，`165 passed`。`0009` 在隔离 `0008` schema 下先插入缺 `scheduled_at` 的真实旧 SCHEDULED Article 与墓碑，应用时分别从 `updated_at/deleted_at` 正确回填，再执行 `0009 -> 0008 -> 0009` 反向/重放均退出 0；catalog 读回 Article/Tombstone schedule CHECK、mask event type/ULID CHECK 与主键，旧事实每次回填均为 true，验证夹具随后定向清理并读回 Article/Revision/Tombstone 均为 0。migration drift、Django check、Ruff lint/format 与 `git diff --check` 均退出 0。最终 discovery 缓存消费者与 HTTP 页面分别由 P6/P10/P11 消费稳定投影/事件/服务，本卡未提前创建平行 owner；未执行生产事件、生产 migration、生产缓存动作或 Git 交付。
- 授权：`否`。

## 阶段总审计（2026-07-23）

- 状态与拓扑：结构化读回 P5 精确 11 张 `CNT` 任务卡、11 条 `完成`、11 条证据和 11 条授权，`进行中/待处理/阻塞/待确认` 为 0；所有前置 `FND/ACC/MED/OBS/RUN` 均在所属阶段为完成。总索引已从过期的 P2 状态修正为 P0-P5 共 50/102 项完成，下一项只指向 P6 `DSC-001`，未提前建立 P6/P10/P11 页面。架构契约检查覆盖 owner 与依赖方向，content 只依赖 accounts/media/operations 公共端口和 core 协议；comments 清理由 P5 注册端口留给其后置 owner，安装 comments 却未注册时关闭失败。
- 数据与回归：全新 loopback PostgreSQL 测试库从零应用全部 migration 后，全仓 `pytest --create-db -q` 与最终代码后的 `pytest -q` 均退出 0，`328 passed`；P5 聚焦恢复、删除和作者状态分别为 `5/6/5 passed`。真实 PostgreSQL 并发覆盖标签上限、编辑冲突、双 Worker 发布/清理与禁用到点竞态；临时媒体覆盖跨修订共享、事务回滚、提交后文件失败及待删重试；Outbox consumer 读回重复/乱序事件终态。Ruff lint、299 文件 format check、compileall、Django check、`uv lock --check`、migration drift、架构/Outbox/task-entry 合约 20 项和 `git diff --check` 均退出 0。
- Migration 与 catalog：隔离基库最终读回 `content.0001..0009` 全部应用。各任务卡记录 `0001..0006` 的反向/重放；本阶段收口又完成 `0007 -> 0006 -> 0007`、`0008 -> 0007 -> 0008` 与 `0009 -> 0008 -> 0009`。`0009` 在旧 schema 真实插入缺排期建立时间的 SCHEDULED Article/墓碑，应用和重放均正确回填后再建立 CHECK，验证夹具定向清理为 0。最终 catalog 读回 9 条 content migration、Article 排期三事实 CHECK、Revision 不可变 trigger、恢复来源复合 FK、墓碑 0 FK 与作者遮罩主键/事件约束；全新测试库同时证明零基线向前迁移。
- 运行时与清理：排期和物理清理分别完成真实隔离 Redis broker + solo Worker smoke，读回 Article 指针/删除终态和 TaskRun `succeeded/attempt=1`；Worker 均温和停止且进程为空。主机 root Worker 只用于隔离 smoke 并产生 Celery 非生产 superuser 警告，生产仍须容器非特权用户。专用 `kaj-p5-postgres/redis/mailpit` 最终执行定向停止，`docker ps -a` 对三个名称读回为空；未终止其他项目进程。P5 没有用户可见页面，HTTP/Playwright 状态矩阵由明确后置 P6/P10/P11 消费，本阶段未用静态截图冒充页面验收。
- 未执行与残余边界：未执行生产 migration/数据清理、生产事件消费、生产缓存、真实通知/邮件、部署、服务重启或新的 Git add/commit/push。全域 `OUTBOX_TRANSPORT` 按 P1 基础设计继续默认关闭失败，P5 交付的是可由后续 P8 全域注册表路由的持久幂等 content consumer，未用只识别账户事件的局部 transport 吞掉其他领域事件。当前改动保留在 `codex/p5-content-finalize` 工作树，等待新的 Git 交付授权。

[返回总索引](../implementation-todolist.md)
