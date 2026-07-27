# P9 导入导出、备份与 Umami（7）

退出门禁：导入预览/部分成功、导出、下载、备份保留和 Umami 入口完成，所有异步状态真实。

### EXC-001 建立 ImportJob/Item 与安全上传解包/解析预览
- 元数据：状态 `完成`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：所有作者上传 ZIP/Markdown 后只创建 Job/Item 预览，不写文章；压缩包限制 `64 MiB` 压缩大小、`256 MiB` 展开量、`1000` 项、`8` 层嵌套和 `100:1` 压缩比，拒绝 zip-slip/bomb/链接/设备文件；Front Matter 白名单，图片统一校验。
- 来源：访谈 Q275-Q280、Q321；`flows/04-import-export-sequences.md` §Markdown导入/包安全；`modules/10-exchange-analytics-maintenance.md`。
- 依赖：前置 `MED-002`、`MED-007`、`CNT-001`、`DEC-005`；后续 `EXC-002`、`AUT-006`、`QA-001`、`QA-003`、`QA-006`。
- 文件：ImportJob/Item models/migrations、package reader/front matter/markdown/archive parsers、staging/tests。
- 边界：预览不得创建Tag/Article/正式Binding；安全YAML仅标量/列表；上传源任务结束后清理；无普通用户导出。
- 影响：数据：Job/Item预览；权限：author；审计：Job元数据；缓存无；异步：解析可Job；媒体：暂存；通知仅失败终态。
- 测试/验收：RED `64 MiB`/`256 MiB`/`1000` 项/`8` 层/`100:1` 的边界与超限、zip-slip/绝对路径/symlink/恶意 YAML/坏图/HTML XSS；临时目录始终在 job 根并清理。
- 风险/停止：解包前无上限、预览执行HTML或正式表出现任何导入记录即停止。
- 证据：一次性专项 RED `pytest tests/test_exc001_temp.py tests/test_exc001_security_temp.py -q` 在收集期因 `apps.exchange` 不存在退出 2。新增 exchange owner 的 ImportJob/ImportItem schema、受控 Job staging、结构化 ZIP/Markdown/Front Matter 解析和配置组合端口；ZIP 从不调用 `extractall`，在写入前拒绝绝对/驱动器/穿越/重复路径、加密项、symlink/字符或块设备，并以元数据加流式计数双重执行 `64 MiB` 压缩、`256 MiB` 展开、`1000` 项、`8` 层和单项/全包 `100:1`。PyYAML 6 `safe_load` 前额外拒绝 tag/anchor/alias，只接受白名单根 mapping 与标量/标量列表；Markdown 预览复用 media owner 的 sanitizer，引用图片复用同一解码、格式、2 MiB、`8192`/`25 MP`、`200` 帧/`100 MP` 清洗端口，只写 Job 私有预览 staging，不创建 Article、Tag、MediaAsset 或 MediaBinding。源包和未清洗展开目录在预览任务结束前删除；Job/账户删除通过提交后回调清理预览 staging，ImportJob/Item 对账户级联，未破坏既有账户删除。专项最终退出 0，`24 passed`，包含五类限制等于边界和超限、默认 1000/1001 项、直接正文上限、zip-slip/Windows/绝对路径、链接/设备文件、恶意 YAML、坏图逐项 INVALID、XSS 清洗、作者权限、账户删除和零正式事实。账户删除、媒体上传/清理/渲染及架构相关回归为 `55 passed, 1 failed`；唯一失败是 `origin/main` 已有 comments/moderation→`operations.public` 九处白名单漂移，新 exchange owner 对其他 app 的直接导入为 0。隔离 PostgreSQL 从零应用全仓 migration，并完成 `exchange.0001 -> zero -> 0001`；catalog 读回 Job/Item FK、三条逐 Job 唯一约束、状态/解析 shape CHECK 和作者/状态索引。首次 catalog SQL 仅因内部 `char` 拼接未 cast 退出 1，显式 cast 重跑退出 0；配置入口真实读回 `PREVIEW_READY`、1 VALID、sanitized script absent，Article/Tag/MediaAsset/Binding 均 0，源目录不存在，定向清理后 Job/Item/账户与临时根均 0。目标 Ruff lint/format、Django check、migration drift、`uv lock --check` 与 `git diff --check` 均退出 0；Django 仅报告已清理 `static/dist` 的既有 warning。本卡没有用户页面，`authoring:import` 由后续 `AUT-006` 组装并执行浏览器验收；未处理未知来源真实包，未执行生产 migration、生产媒体/数据、提交、推送、部署或服务重启。
- 授权：`否`；对未知来源真实包执行需明确安全测试环境。

### EXC-002 实现逐项冲突分类、预览选择与元数据映射
- 元数据：状态 `完成`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：逐篇分类NEW/重复ID/同标题警告/跨作者冲突/无效；作者选SKIP/UPDATE/CREATE、纳入项、分区/标签映射；无分区进未知，新标签待审即关联。
- 来源：访谈 Q277-Q280；`flows/04-import-export-sequences.md` §判定表；`contracts/01-application-services.md` §exchange。
- 依赖：前置 `EXC-001`、`CNT-010`、`CNT-011`；后续 `EXC-003`、`AUT-006`、`QA-003`、`QA-006`。
- 文件：preview/classifier/decision services、preview version、queries/DTO/forms/tests。
- 边界：ID是唯一更新键；标题仅精确警告；跨作者ID只能跳过；文章归导入者；修改选择递增preview_version。
- 影响：数据：Item决策/映射；权限：导入者/目标owner；审计：决策摘要；缓存无；异步无；媒体：预览引用；通知：跨作者同标题坚持发布后。
- 测试/验收：RED 全判定矩阵、逐项排除、preview并发版本、未知分区/待审标签；Playwright预览/字段错误。
- 风险/停止：允许跨作者更新/另建同ID、标题误作更新键或预览变更静默覆盖即停止。
- 证据：专项 RED `pytest tests/test_exc002_temp.py -q --create-db` 在收集期退出 2，准确报告 `apps.exchange.public.ImportDecisionError` 尚不存在。content owner 新增只读冲突/分区/标签事实端口，exchange owner 新增分类、owner-scoped 预览 DTO 和行锁决策服务，配置层只做 DTO 转换与端口注入；有 ID 且属于本人分类 `DUPLICATE_ID`，跨作者 ID 分类 `FOREIGN_CONFLICT` 并强制排除/只允许 SKIP，无 ID 的精确同标题只产生 SELF/FOREIGN/MIXED 警告且绝不成为更新键，其余为 NEW。ACTIVE/PENDING 标签映射稳定 ID，缺失标签只保存提议名、不提前创建 Tag；未知分区映射为空，REJECTED 标签只把对应 Item 置 INVALID。每次有效用户决策在 Job 行锁内递增 `preview_version`，同版本双写者最终精确一成一冲突；决策与只含 Job/Item ID、选择、映射数量和版本的安全 AuditEntry 同事务，审计失败时 Item 与版本均回滚。专项 GREEN 最终退出 0，`6 passed`，覆盖全分类/动作矩阵、逐项排除、owner 隐私、陈旧版本、两线程竞态、映射与零提前 Tag 写；EXC-001/002、content、media、operations 与架构相关回归为 `103 passed, 1 deselected, 1 failed`，deselected 是当前上海午夜窗口已知的 OBS-004 UTC 日期测试，唯一失败仍是 origin/main 已有 comments/moderation→`operations.public` 九处白名单漂移，exchange 对其他 app 直接导入为 0。首次在较早 EXC-001 schema 的 `kaj_test_p9` 反向当前未提交 `0001` 因新约束不存在退出 1且事务回滚；随后全新 `kaj_test_p9_exc002` 从零应用全仓 migration，并成功完成 `exchange.0001 -> zero -> 0001`，反向读回两表为 0，重放后 catalog 读回 `proposed_tag_names`、`conflict_summary` 与 decision/target shape CHECK，Job/Item 均为 0。目标 Ruff lint/format、Django check、migration drift、`uv lock --check` 和 `git diff --check` 均退出 0，Django 仅报告已清理 `static/dist` 的既有 warning。本卡只交付 authoring 后续消费的稳定 DTO/服务，`authoring:import` 页面与 Playwright 字段错误流仍由 `AUT-006` 组装，不提前建立第二页面 owner；未执行生产 migration、生产导入、提交、推送、部署或服务重启。
- 授权：`否`。

### EXC-003 实现幂等确认、逐项事务与部分成功导入
- 元数据：状态 `完成`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：确认冻结预览后逐项独立事务，成功/跳过/失败均留原因；重复确认不重复写；更新保留历史并可将富文本当前格式改Markdown；成功项不因其他失败回滚；导入警告通过 `OBS-008` 的注册端口扩展 Exchange 模板并生成回执。
- 来源：访谈 Q277-Q280、Q321；`flows/04-import-export-sequences.md` §时序/失败语义；`modules/10-exchange-analytics-maintenance.md` §导入。
- 依赖：前置 `EXC-002`、`CNT-002`、`CNT-007`、`MED-003`、`OBS-006`、`OBS-008`；后续 `AUT-006`、`QA-003`、`QA-004`、`QA-006`。
- 文件：confirm/importer services/tasks、content/media/notification ports、Exchange 通知模板、item idempotency/result UI DTO/tests。
- 边界：不提供整批撤销；格式例外必须写版本原因；媒体仅文章事务成功后绑定；疑似他人标题坚持通过通知注册端口通知管理员，不复制通知模型、文案拼装、去重或回执实现。
- 影响：数据：Job/Item终态+ArticleRevision；权限：author/owner；审计：导入摘要；缓存：发布项失效；异步：Job/TaskRun；媒体：绑定/清理；通知：管理员警告/终败。
- 测试/验收：RED 重复确认、混合有效无效、更新历史、富转Markdown、媒体绑定失败、worker崩溃、Exchange 模板重复事件；逐项 DB/文件/通知 Receipt 读回。
- 风险/停止：重复文章/版本、部分失败全回滚或失败项遗留ACTIVE媒体即停止。
- 证据：专项 RED `pytest tests/test_exc003_temp.py -q` 首次收集退出 2，准确报告确认入口尚不存在；exchange owner 随后冻结精确 preview version、为 CREATE 预分配稳定文章 ID，并以 Job 行锁、`import:{job}:{item}` revision key 和每 Item 独立事务实现重复确认/处理幂等与部分成功。content owner 的导入端口保留不可变历史，允许 TipTap 当前格式显式转 Markdown 并记录 `IMPORT/IMPORT_FORMAT_CHANGE` 原因，创建缺失 PENDING 标签并立即关联；media owner 只为成功 Item 创建并绑定 BODY/COVER 资产，失败时定向清理该 Item 新资产；发布/排期事件及跨作者同标题警告通过 Outbox 与已注册 `exchange.import_title_warning.v1` 模板生成单份 Notification/Receipt。当前代码上专项 `--create-db` 退出 0，`7 passed`，覆盖陈旧/重复确认、混合成功/跳过/失败、结果 DTO、历史格式、标签、媒体失败清理、直接/Celery 重试、通知去重及提交后进程崩溃恢复；EXC-001..003、content、media、notifications、Outbox 与 TaskRun 相关回归退出 0，`206 passed`。全新 `kaj_test_p9_exc003` 从零应用全仓 migration 后，`exchange.0001 -> zero -> 0001` 与 `content.0011 -> 0010 -> 0011` 均退出 0；catalog 读回 Job/Item 最终状态 shape CHECK、`reason/import_key` 字段及 `import_key` 唯一约束，Job/Item/import revision 均为 0。目标 Ruff lint、Django check、migration drift、`uv lock --check` 与 `git diff --check` 均退出 0，format check 仅要求一次性测试采用当前格式后已修正。本卡提供 `AUT-006` 后续组装的稳定确认/结果 DTO，没有提前建立导入页面；未执行生产导入、生产 migration、真实邮件、提交、推送、部署或服务重启。
- 授权：`否`。

### EXC-004 建立管理员导出选择、全局并发与任务授权
- 元数据：状态 `完成`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：仅管理员按全站/作者/分区/选文选择草稿、定时、私人、冷静期及完整历史；数据库保证全站最多一个RUNNING，额外请求拒绝不排队。
- 来源：访谈 Q275-Q283；`data/03-interaction-operations-fields.md` §ExportJob；`data/04-indexes-constraints.md` §全局导出。
- 依赖：前置 `CNT-008`、`CMT-011`、`OBS-004`；后续 `EXC-005`、`ADM-008`、`QA-001`、`QA-003`、`QA-006`。
- 文件：ExportJob/Selection models/migrations、request policy/service/query/forms/tests。
- 边界：普通用户/作者不可导出；选择快照固定；冷静期可选；不生成公开链接；Job接受不等于完成。
- 影响：数据：Job/Selection/部分唯一；权限：admin；审计：请求范围；缓存无；异步：build任务；媒体：归档目标；通知后续。
- 测试/验收：RED 两并发请求仅一RUNNING、所有状态/范围、普通用户伪造；真实PostgreSQL唯一裁决。
- 风险/停止：仅Redis锁、额外请求被隐式排队或选择在执行时漂移即停止。
- 证据：一次性专项 RED `pytest tests/test_exc004_temp.py -q --reuse-db` 在收集期退出 2，准确报告 content 导出快照端口不存在。content owner 新增包含草稿、定时、已发布、三种可见性和 7 天冷静期文章的全历史 revision ID 只读快照；exchange owner 新增 ExportJob/ExportSelection、ALL/AUTHOR/SECTION/ARTICLES 严格范围 shape、请求服务和 JobAccepted DTO，选择行固定文章/作者/当前指针/全部 revision ID 与状态，后续新增修订不改变既有快照。服务重判启用的唯一管理员，与只含范围、数量和其他作者数量的 AuditEntry 同事务，提交后才调用 build dispatcher；审计失败时 Job/Selection/dispatch 全回滚。聚焦 GREEN 退出 0，`7 passed`，覆盖四种范围、所有状态/PRIVATE/冷静期、完整历史、不漂移、普通用户伪造、非法 scope、两线程竞态、额外请求拒绝和审计失败；EXC-001..004、content、operations 与架构相关回归退出 0，`117 passed, 2 deselected`，两项仍为已知 OBS-004 上海日期边界与 comments/moderation 架构白名单基线。全新 `kaj_test_p9_exc004` 从零应用全仓 migration，并完成 `exchange.0002 -> 0001 -> 0002`；catalog 读回基于常量表达式的 `exchange_export_active_unique` 部分唯一索引覆盖 RUNNING/CANCEL_REQUESTED、scope/state CHECK、Selection 双唯一/FK/非空 revisions CHECK，Job/Selection 均为 0。目标 Ruff lint/format、Django check、migration drift、`uv lock --check` 与 `git diff --check` 均退出 0；本卡只在事务提交后分派稳定 Job ID，不生成归档、不显示假完成，实际 build/cancel/download 由 EXC-005 闭合。未执行生产导出、生产 migration、提交、推送、部署或服务重启。
- 授权：`否`。

### EXC-005 实现导出归档、取消竞态、鉴权下载与三天清理
- 元数据：状态 `完成`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：ZIP含manifest/JSON、Markdown、TipTap原JSON、全部版本/媒体；写.part后原子完成；管理员可取消未完成、仅本人后台下载；完成包3天删；导出他人内容按作者/日通知。
- 来源：访谈 Q276、Q281-Q283、Q306；`flows/04-import-export-sequences.md` §管理员导出；`contracts/05-background-tasks.md` §取消竞态。
- 依赖：前置 `EXC-004`、`MED-004`、`MED-006`、`OBS-001`、`OBS-006`、`OBS-008`、`OBS-009`；后续 `ADM-008`、`QA-003`、`QA-004`、`QA-006`。
- 文件：exporter/archive/manifest、build/cancel/download/expire services/tasks、tests。
- 边界：Markdown对TipTap仅便利副本不宣称无损；取消保留Job/审计并删.part；完成与取消仅一个终态；无可转发URL。
- 影响：数据：Job终态；权限：admin下载；审计：请求/取消/下载状态；缓存无；异步：build/expire；媒体：ZIP/源；通知：完成/失败/受影响作者。
- 测试/验收：RED取消-完成竞态、双worker、过期、未授权/已过期下载、文件缺失、他人通知去重；真实文件/HTTP读回。
- 风险/停止：部分ZIP可下载、取消删有效完成包、归档路径越界或PRIVATE媒体未授权泄露即停止。
- 证据：专项 RED `pytest tests/test_exc005_temp.py -q` 在收集期因 `ExportArchiveStorage` 缺失退出 2；exchange owner 随后建立受控绝对归档根、排他 `.zip.part`、原子改名、路径/链接防护与 manifest/文章/全修订/Markdown/TipTap 原 JSON/有损便利副本/去重媒体格式，content/media owner 只提供完整修订与 ACTIVE 媒体字节端口。Job 行锁裁决完成/取消唯一终态，构建周期检查 heartbeat 与取消，完成包精确三天到期；下载重判启用管理员和请求人、校验大小/SHA 且不生成 URL，取消/下载审计与 Job 同步，最终失败经 OBS-009 消费者清理 `.part`、标记 FAILED 并释放全局槽。完成通知按 Job 一次，导出他人内容按作者与上海日去重。修复收口时先准确复现导入标题警告 builder 被截断及过期 dispatcher 绕过 TaskRun 两个回归；恢复 builder 后将扫描入口按 Celery request ID 接入 `execute_celery_entry`，实际 Job 仍用 `export:{job}:expire` 幂等。专项与 TaskRun 契约退出 0、`9 passed`；EXC-001..005、content、media、notifications、operations、Outbox 与架构相关联合回归退出 0、`234 passed, 1 deselected`，唯一排除仍为已知 comments/moderation 架构白名单基线。真实 Redis broker + solo Worker 在从零迁移的隔离 PostgreSQL 上完成一篇 PRIVATE 文章导出：TaskRun `attempt=1/succeeded`，Job `COMPLETED`、lease 释放、到期时间精确三天，ZIP 仅有最终文件且大小 `1900`、SHA-256 与数据库一致、`ZipFile.testzip()` 无损坏；第二个真实 Worker 任务发布 Outbox，管理员完成通知与作者内容通知各一份。目标 Ruff lint/format、Django check、migration drift、`uv lock --check` 与 `git diff --check` 均退出 0，Django 仅有已清理 `static/dist` 的既有 warning；隔离记录、Redis、Worker、临时归档和临时 settings 已定向清理。`admin:exchange` 页面与真实 HTTP 下载由后续 `ADM-008` 组装；未执行生产导出/下载/清理、生产 migration、真实邮件、提交、推送、部署或服务重启。
- 授权：`否`；生产导出/下载 `是`。

### EXC-006 实现数据库+媒体周备份、30天保留与人工恢复说明
- 元数据：状态 `完成`；阶段 P9；owner `operations`；优先级 P0。
- 目标/行为：按 DEC-004 在 `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`）同轮执行 pg_dump+媒体归档，首版仅 `local`、不加密且保留 30 天；成功仅表示命令/文件完成，不自动校验/恢复演练；网页只读记录，恢复服务器人工。
- 来源：访谈 Q148-Q152、Q182、Q189、Q288；`flows/04-import-export-sequences.md` §备份；`modules/10-exchange-analytics-maintenance.md` §备份。
- 依赖：前置 `DEC-004`、`RUN-006`、`OBS-006`、`OBS-007`、`OBS-009`、`OBS-010`；后续 `ADM-008`、`QA-003`、`QA-005`、`QA-006`。
- 文件：BackupRecord、backup/cleanup services/tasks/scripts、Beat schedule、manual restore runbook/tests。
- 边界：不宣称可恢复已验证；无网页下载/恢复；不加密是明确风险；未来外部 adapter 不在首版实现且不得出现在首版 DTO/UI；临时包不算成功。
- 影响：数据：BackupRecord/归档；权限：server-only；审计：设置/记录；缓存无；异步：周/日清理；媒体：全量；通知：最终失败站内+邮件。
- 测试/验收：冻结时钟验证周一 03:00/cron、周幂等、重复调度、非 local 目标拒绝，并模拟 pg_dump/媒体失败/原子改名/30天边界/租约；隔离测试数据执行一次命令并核对记录，不做恢复声明。
- 风险/停止：备份包含.env/秘密、覆盖现有归档、失败标成功或在生产无授权执行即停止。
- 证据：收口新增崩溃恢复 RED `pytest tests/test_exc006_temp.py::test_expired_attempt_rebuilds_after_atomic_publish_crash -q --reuse-db` 退出 1，先准确报告原子改名后数据库未提交的孤儿归档导致 `operations.backup_archive_conflict.v1`，再扩展同一测试准确报告旧 token 的 `.part/.work` 残留；operations owner 改为新租约持有者在 BackupRecord 仍为 RUNNING 时定向清理该记录的孤儿归档和全部未完成尝试，旧 Worker 仅在行锁内确认仍持有 lease 后才可删除自己的已发布文件，COMPLETED 记录不进入覆盖路径。BackupRecord 以 PostgreSQL 周唯一、全局 RUNNING 部分唯一、local-only 与 RUNNING/COMPLETED/FAILED/EXPIRED shape 约束裁决；服务执行真实 PostgreSQL custom dump、全媒体 tar.gz、排他 `.part`、fsync/原子改名、SHA-256、周幂等、30 天到期和到期只删归档保留记录，Beat 固定 UTC 周日 19:00 对应上海周一 03:00；TaskRun 统一处理三次退避、租约、终败 RuntimeError/站内通知/Mailpit 邮件，人工 runbook 明确未验证可恢复且无网页下载/恢复。专项 GREEN 退出 0，`8 passed`；P9 导入/导出/备份与 operations/notifications/Outbox 联合回归退出 0，`121 passed`，崩溃恢复与 TaskRun 联合回归退出 0，`19 passed`。专用 `kaj_test_p9_exc006_runtime` 从零应用全仓 migration，完成 `operations.0006 -> 0005 -> 0006`，catalog 读回表反向后不存在、重放后记录为 0，周/全局唯一索引及 local/state CHECK 均存在。DaoCloud 基础镜像候选构建退出 0；真实 `pg_dump 16.14` 首次读回暴露 `/usr/bin/pg_dump` 为被安全边界拒绝的 wrapper symlink，默认改为版本化真实二进制后重建退出 0。候选镜像以 UID 10001 对隔离数据库和两份媒体完成真实归档：`PGDMP`、BackupRecord `COMPLETED/local`、归档 `62536` 字节、SHA 长度 64、两份媒体、无未完成文件、精确 30 天，manifest 为未加密/未自动校验/未验证恢复；真实 Redis DB 14 + solo Worker 再完成 TaskRun `attempt=1/succeeded` 与 `62849` 字节原子归档，数据库 dump `488710` 字节、lease 释放。目标 Ruff、全仓 format、Django check、migration drift、`uv lock --check`、Compose、npm build 与 `git diff --check` 均退出 0；完整 Ruff 唯一失败仍是未修改 P7 `apps/comments/tests/test_cmt004.py` 的既有导入排序。专用 Worker 温和退出，Redis DB 14 已清空；隔离运行库、测试归档和候选镜像在阶段清理时定向删除。本卡无用户页面，备份只读 UI 由 `ADM-008` 组装；未执行生产备份/恢复/清理、生产 migration、真实邮件、提交、推送、部署或服务重启。
- 授权：代码/模拟 `否`；真实备份/恢复/清理 `是`。

### EXC-007 集成同源管理员 Umami 与一个月保留
- 元数据：状态 `完成`；阶段 P9；owner `analytics`；优先级 P1。
- 目标/行为：自托管Umami跟踪公共、登录、私人、个人、管理全部页面；容器无公网端口，仅管理员经同源受控入口访问；每日删除一个月前数据。
- 来源：访谈 Q139-Q140、Q319-Q320；`modules/10-exchange-analytics-maintenance.md` §Umami；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `RUN-001`、`RUN-003`、`DEC-002`、`ACC-001`、`OBS-006`、`OBS-009`；后续 `ADM-008`、`QA-002`、`QA-003`、`QA-005`、`QA-006`。
- 文件：analytics access/proxy/presentation、tracking base integration、retention task/config/tests。
- 边界：Umami不替代产品浏览量/审计/错误；普通用户不能直达dashboard/API；分析数据只留1月；production 缺真实域名或必需秘密时不启用跟踪与管理入口。
- 影响：数据：Umami独立库/清理；权限：admin同源；审计：入口只读不审计；缓存无；异步：每日清理；媒体无；通知：终败。
- 测试/验收：RED 未授权代理/直端口、各页面脚本覆盖、30天边界/重复清理；隔离容器HTTP与DB读回。
- 风险/停止：后台绕过博客认证、秘密暴露给浏览器或清理影响近30天数据即停止。
- 证据：初始专项 RED `pytest apps/analytics/tests/test_exc007.py -q` 在收集期因 `apps.analytics` 不存在退出 2。新增 analytics owner、全站同源 tracker 与管理员分析页；Caddy 只公开 `GET/HEAD /analytics/script.js` 和 `POST/OPTIONS /analytics/collect`，dashboard/API 全部先经 Django 唯一管理员鉴权，并从发往 Umami 的请求删除 Cookie、从鉴权子请求删除 Authorization。Umami 固定 `v2.19.0`、无宿主端口、使用独立 analytics 网络和独立 `umami` 数据库；production 缺真实域名、数据库 URL、网站 UUID 或其他必需配置时 fail closed，Umami 自身拒绝短于 32 字符的 `APP_SECRET`，Django 不接收该秘密。保留任务固定每日 03:45 `Asia/Shanghai`，以 advisory lock 和固定 schema 门禁在同一事务内按依赖顺序严格删除 `< 执行时刻 - 30 天`，边界记录保留，重复执行删除 0；统一 TaskRun 最多三次并接入脱敏终败通知。专项 GREEN 新鲜退出 0，`9 passed`；P9 `EXC-001..007` 联合回归退出 0，`69 passed`；独立固定 Umami `v2.19.0` 表子集 PostgreSQL 集成退出 0，`1 passed`，读回旧记录各删除 1、边界记录各保留 1、第二次删除 0。候选 Postgres 镜像在无网络、无宿主端口的临时容器中用全新数据目录初始化，读回 `kaj_init_test` 与 `umami` 两个数据库后已定向清理。浏览器使用真实密码和博客会话读回匿名 403、普通用户 403、管理员 200 与同源 iframe 内容；390/768/1440 三视口及浅色/深色/护眼三主题均无页面或 iframe 横向溢出，原尺寸截图无裁切/遮挡，首个 Tab 跳到主要内容且主题按钮可用 Tab+Enter 切换。stub 日志中 tracker、collect、dashboard 请求均为 `cookie=0 authorization=0`；Chrome 由 `blog-browser` UID 999/GID 988 运行且未使用 `--no-sandbox`。浏览器验收曾发现 Caddy 全局指令排序先 strip prefix、后 forward auth，使管理员 iframe 鉴权收到错误路径并 404；改为显式 `route` 后 adapter 读回顺序为鉴权、strip、Umami proxy，专项与真实浏览器均恢复。目标改动集 Ruff、517 文件 format、Django check、migration drift、`uv lock --check`、Compose、架构契约 3 项和 npm build 均退出 0；全仓 Ruff 唯一失败是未修改 P7 `apps/comments/tests/test_cmt004.py` 的既有导入排序。隔离浏览器、PostgreSQL、Redis、Mailpit、Caddy、stub、账户、截图和临时配置均已定向清理。真实 Umami 未启动，未创建真实网站或采集真实流量，未执行生产分析清理、生产 migration、部署、提交或推送。
- 授权：代码 `否`；启动Umami、真实跟踪/数据清理 `是`。

[返回总索引](../implementation-todolist.md)
