# P5 文章、修订、分类与发布任务（11）

退出门禁：文章三指针、分类、发布/排期、冲突、恢复、删除和容量/审计/任务基础集成完成。

### CNT-001 建立 Article/不可变 Revision 与正交状态 schema
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：使用 ULID 文章/修订、不可变 sequence、working/published/scheduled 三指针、publication/deletion 正交字段与 row_version；作者不可转移。
- 来源：访谈 Q001-Q002、Q036-Q053、Q291；ADR-002；`data/02-identity-content-fields.md` §Article/Revision；`flows/02-article-state-machine.md`。
- 依赖：前置 `FND-003`、`FND-006`、`ACC-001`；后续 `CNT-002`、`CNT-010`、`CNT-011`、`CNT-004`、`CNT-006`、`CNT-008`、`EXC-001`、`QA-001`、`QA-006`。
- 文件：`apps/content/models/{article,revision}.py`、migrations、policy/service skeleton、tests。
- 边界：正文/草稿/版本只在 PostgreSQL；Revision 不原地更新；不压成单 status、不转移 owner、不存文件正文。
- 影响：数据：核心聚合/约束/索引；权限：author FK；审计：版本 ID；缓存/异步/媒体/通知后续。
- 测试/验收：RED 指针同文章、sequence唯一、软删时间成对、格式/正文列匹配；migration 与真实 DB 读回。
- 风险/停止：指针可跨文章、revision 可 update 或 schema 无法支持旧发布稳定性即停止。
- 授权：schema/隔离 migration `否`；生产 migration `是`。

### CNT-002 实现新建、格式选择、云草稿与正文/媒体校验
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：作者新建默认大众/草稿/评论开启且访客可看评/顶层评论；选 Markdown/TipTap 后普通编辑不可改；显式保存创建新 Revision。
- 来源：访谈 Q036-Q037、Q234、Q254、Q262、Q314、Q317；`contracts/01-application-services.md` §content；`modules/03-content-versioning.md`。
- 依赖：前置 `CNT-001`、`MED-003`、`MED-007`、`DEC-005`；后续 `CNT-003`、`CNT-006`、`EXC-003`、`AUT-001`、`AUT-002`、`AUT-003`、`QA-003`、`QA-006`。
- 文件：content create/save services、snapshot DTO、body limit/summary validation、tests。
- 边界：标题≤30可重复；正文默认≤`2 MiB`且不计图片，管理员可配范围仅为`64 KiB`至`2 MiB`；本地草稿不由 content 存；不允许普通格式切换。
- 影响：数据：Article/Revision；权限：仅作者；审计：版本元数据；缓存无；异步：outbox可无；媒体：绑定；通知无。
- 测试/验收：RED 默认值、两格式、正文 `64 KiB`/`2 MiB` 配置与正文边界、媒体 owner/purpose、非作者 POST、普通格式切换；DB读回新不可变修订。
- 风险/停止：保存覆盖旧行、正文限制只在前端或绑定失败留下 ACTIVE 孤儿即停止。
- 授权：`否`。

### CNT-010 实现分区唯一管理、发布要求与未知分区
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：管理员按唯一名称 CRUD 分区；普通发布必须一个分区；删除后文章进入未知分区，只在首页/标签发现，导入无法映射可同样进入。
- 来源：访谈 Q055-Q057、Q256、Q279；`data/02-identity-content-fields.md` §Section；`flows/02-article-state-machine.md` §分类例外。
- 依赖：前置 `CNT-001`、`OBS-004`；后续 `CNT-003`、`DSC-003`、`EXC-002`、`ADM-005`、`QA-001`、`QA-003`、`QA-006`。
- 文件：section model/service/query/migration、publication validator、tests。
- 边界：分区仅名称；不级联删文章；未知不是伪造“未分类”记录，不进入导航/分区页。
- 影响：数据：Section/revision FK；权限：admin写；审计：CRUD；缓存：列表失效；异步/媒体/通知无。
- 测试/验收：RED 名称并发唯一、删除关联、普通发布缺失、导入例外；DB与发现query读回。
- 风险/停止：删除分区使文章消失/被删、旧URL泄露或缓存未失效即停止。
- 授权：`否`。

### CNT-011 实现标签提议、审核、十标签与删除恢复
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：作者可提议待审标签并立即显示，管理员直接建/通过/驳回；驳回移除并通知；全站标签删除保留历史，恢复合法关联；每篇≤10。
- 来源：访谈 Q054、Q058-Q061、Q257-Q258、Q280；`data/02-identity-content-fields.md` §Tag；`flows/02-article-state-machine.md` §分类例外。
- 依赖：前置 `CNT-001`、`FND-005`、`OBS-004`；后续 `CNT-003`、`DSC-003`、`OBS-008`、`EXC-002`、`ADM-005`、`QA-001`、`QA-003`、`QA-006`。
- 文件：tag/proposal/history models、classification services/events、constraints/queries/tests。
- 边界：作者不能直接激活全站标签；删除旧链接为空；恢复超过10个记录冲突并通知管理员，不能静默丢弃。
- 影响：数据：Tag/RevisionTag/ArticleTag/History；权限：author提议/admin审核；审计：管理员动作；缓存：列表/文章失效；异步：通知事件；通知：作者/冲突；媒体无。
- 测试/验收：RED 规范名并发、10标签并发、驳回移除、删除/恢复、超限冲突；真实DB锁/索引读回。
- 风险/停止：表单层独占约束、历史关联漂移或恢复制造幽灵/超限标签即停止。
- 授权：`否`。

### CNT-003 实现终稿审查、立即发布与已发布重发
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：安全终稿审查令牌后立即发布；读者只见 published 指针；已发布编辑仍显示旧版，显式重发或作者偏好自动重发均创建新修订并保留首次发布时间。
- 来源：访谈 Q048-Q053、Q263-Q264、Q298；`flows/02-article-state-machine.md` §创建/发布；`modules/07-authoring-workbench.md` §发布审查。
- 依赖：前置 `CNT-002`、`CNT-010`、`CNT-011`、`MED-007`、`FND-005`；后续 `CNT-004`、`CNT-005`、`CNT-007`、`DSC-002`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：publication services/review token、author preference bridge、events/cache hooks/tests。
- 边界：首次发布/历史恢复必须终稿审查；自动重发仍做完整校验；UI 不能把 202/保存当发布完成。
- 影响：数据：发布指针/时间；权限：作者；审计：版本/事件；缓存：失效事件；异步：outbox；媒体：发布绑定；通知无默认。
- 测试/验收：RED 编辑发布文不变读者版、令牌重放/过期、分区缺失、自动偏好；读者/作者双会话读回。
- 风险/停止：发布指针先于校验、首次 published_at 被重置或缓存仍返回旧/私密内容即停止。
- 授权：`否`。

### CNT-004 实现排期、取消与幂等定时发布
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：终稿审查后以 Asia/Shanghai 输入、UTC 存储，锁定 scheduled revision；作者可取消；每分钟扫描到期事实，双 Worker 只发布一次。
- 来源：访谈 Q048-Q049、Q224、Q301；`flows/02-article-state-machine.md` §发布状态；`contracts/05-background-tasks.md` §定时发布。
- 依赖：前置 `CNT-001`、`CNT-003`、`RUN-002`、`OBS-006`；后续 `CNT-009`、`AUT-001`、`AUT-005`、`QA-003`、`QA-004`、`QA-006`。
- 文件：schedule/cancel services、publication task、Beat schedule、TaskRun bridge/tests。
- 边界：不依赖长期 ETA；任务执行时重判作者/删除/隐藏/修订/时间/分类；排期后继续编辑不漂移目标。
- 影响：数据：scheduled 指针/时间；权限：作者；审计：事件；缓存：发布后失效；异步：Celery；媒体：约束重判；通知：终败后。
- 测试/验收：RED 过去时间、取消竞态、双 Worker、作者禁用、修订变化、前两次失败第三次成功；真实 worker smoke。
- 风险/停止：任务按入队快照盲发、Beat 成为事实或重复发布即停止。
- 授权：代码/隔离 worker `否`；启动真实 worker/Beat `是`。

### CNT-005 实现文章可见性策略、管理员只读例外与即时变更
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：PUBLIC/AUTHENTICATED/PRIVATE 服务端矩阵统一；变更已发布可见性立即创建/发布新修订并移出/加入发现；管理员可读他人所有状态但按日通知，不能代编/发布。
- 来源：访谈 Q001-Q007、Q255、Q290、Q302-Q305；ADR-005；`contracts/02-authorization-matrix.md` §文章；`reference/01-requirements-resolution.md`。
- 依赖：前置 `CNT-003`、`ACC-005`、`FND-005`；后续 `CNT-009`、`DSC-002`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`CMT-001`、`CMT-011`、`ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：content policies/queries/admin exception、visibility service/events、capability DTO/tests。
- 边界：无权 PRIVATE/草稿/定时/冷静期返回统一404；管理员例外只读/隐藏/删除/恢复；模板 capability 不授权。
- 影响：数据：新修订/遮罩查询；权限：完整矩阵；审计：管理员写由 moderation；缓存：即时失效；异步：通知事件；媒体：跟随修订；通知：管理员查看按日。
- 测试/验收：参数化四身份×状态、伪造 POST、同日重复查看；浏览器直接 URL + Outbox 通知事实事件读回，最终 Receipt 由 `OBS-008` 回归。
- 风险/停止：查询暴露无 actor QuerySet、错误差异泄露存在性或管理员可改他人设置即停止。
- 授权：`否`。

### CNT-006 实现行锁版本令牌与编辑冲突解析契约
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：两个同基线保存只有一个成功；409 返回安全版本元数据并冻结编辑，作者选择基线后获新令牌继续，published 指针不变。
- 来源：访谈 Q296；`flows/02-article-state-machine.md` §并发编辑；`modules/07-authoring-workbench.md` §并发冲突。
- 依赖：前置 `CNT-001`、`CNT-002`；后续 `CNT-007`、`AUT-004`、`QA-003`、`QA-006`。
- 文件：save service row lock、edit token/conflict DTO、409 mapping、tests。
- 边界：不自动 last-write-wins、不合并正文、不在错误 payload 露他人/私人内容；冲突未解不能保存/发布。
- 影响：数据：row_version/新修订；权限：作者；审计：基线元数据；缓存/异步/媒体/通知无额外。
- 测试/验收：RED 两事务同令牌、选择旧/当前基线、冲突后发布禁止；真实 PostgreSQL 并发读回。
- 风险/停止：只靠表单版本、SQLite 测试或冲突覆盖 published_revision 即停止。
- 授权：`否`。

### CNT-007 实现完整版本时间线与历史恢复
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P1。
- 目标/行为：作者查看全部版本元数据/安全差异，恢复标题、正文、格式、封面、可见性、分区、标签、评论设置；恢复生成新工作修订并再走终稿发布。
- 来源：访谈 Q052-Q053、Q298、Q321；`flows/02-article-state-machine.md` §版本恢复；`data/02-identity-content-fields.md` §ArticleRevision。
- 依赖：前置 `CNT-003`、`CNT-006`；后续 `EXC-003`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：revision queries/prepare+confirm restore services、restore metadata/tests。
- 边界：不覆盖/删除历史；已发布恢复前读者仍见旧版；恢复格式可作为明确例外但需记录来源。
- 影响：数据：新Revision/restore_source；权限：作者；审计：版本ID；缓存：发布后；异步无；媒体：完整绑定快照；通知无。
- 测试/验收：RED 全字段恢复、历史来源保留、冲突令牌、富文本↔Markdown历史；DB指针/媒体读回。
- 风险/停止：恢复直接切 published、丢恢复前状态或恢复已删除媒体无明确错误时停止。
- 授权：`否`。

### CNT-008 实现文章 7 天软删除、恢复与物理清理 Saga
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：作者/管理员删除进入7天冷静期并404；期限内恢复原状态；到期删除正文/版本/媒体/评论，保留举报/申诉/审计稳定引用。
- 来源：访谈 Q046-Q047、Q284、Q290、Q315；`flows/02-article-state-machine.md` §删除；`contracts/05-background-tasks.md` §文章物理删除 Saga。
- 依赖：前置 `CNT-001`、`MED-006`、`FND-005`、`OBS-004`、`OBS-006`；后续 `CMT-011`、`EXC-004`、`AUT-001`、`QA-002`、`QA-003`、`QA-004`、`QA-006`。
- 文件：deletion/restore/purge services/tasks、tombstone snapshot、cross-domain ports/tests。
- 边界：软删期不删媒体/评论；文件删除在DB提交后；冷静期可导出；过期后作者也404。
- 影响：数据：deleted/purge字段与级联；权限：作者/管理员；审计：动作；缓存：即时失效；异步：小时扫描/Saga；媒体：到期删；通知：管理员他人动作。
- 测试/验收：RED 7天边界、恢复、双Worker、DB提交后文件失败、案件保留；真实DB+临时媒体读回。
- 风险/停止：级联误删案件/审计、先删文件或恢复算法覆盖管理员隐藏即停止。
- 授权：隔离测试 `否`；生产物理清理 `是`。

### CNT-009 收敛作者禁用/启用与文章排期生命周期
- 元数据：状态 `待处理`；阶段 P5；owner `content`；优先级 P0。
- 目标/行为：消费账户事件：禁用作者隐藏全部已发布并取消定时转草稿；启用只恢复因禁用遮罩的文章，不恢复排期；历史评论不受影响。
- 来源：访谈 Q299-Q301；`flows/02-article-state-machine.md` §作者禁用遮罩；`contracts/04-events-errors.md` account事件。
- 依赖：前置 `ACC-011`、`CNT-004`、`CNT-005`、`FND-005`；后续 `DSC-008`、`ADM-002`、`QA-002`、`QA-003`、`QA-006`。
- 文件：content account-event consumers、disabled mask projection/policy、tests。
- 边界：不直接改原 visibility；不解除管理员隐藏/软删除；重复事件幂等；accounts 不写文章表。
- 影响：数据：遮罩/排期转草稿；权限：读/写；审计：账户动作关联；缓存：全相关失效；异步：outbox消费；通知：角色通知由OBS；媒体无删。
- 测试/验收：RED 禁用/启用组合、重复事件、排期到点竞态、缓存命中；跨域读回。
- 风险/停止：简单 visible=true 恢复、排期仍自动发布或事件顺序导致文章泄露即停止。
- 授权：`否`。

[返回总索引](../implementation-todolist.md)
