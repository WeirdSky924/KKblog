# P9 导入导出、备份与 Umami（7）

退出门禁：导入预览/部分成功、导出、下载、备份保留和 Umami 入口完成，所有异步状态真实。

### EXC-001 建立 ImportJob/Item 与安全上传解包/解析预览
- 元数据：状态 `待处理`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：所有作者上传 ZIP/Markdown 后只创建 Job/Item 预览，不写文章；压缩包限制 `64 MiB` 压缩大小、`256 MiB` 展开量、`1000` 项、`8` 层嵌套和 `100:1` 压缩比，拒绝 zip-slip/bomb/链接/设备文件；Front Matter 白名单，图片统一校验。
- 来源：访谈 Q275-Q280、Q321；`flows/04-import-export-sequences.md` §Markdown导入/包安全；`modules/10-exchange-analytics-maintenance.md`。
- 依赖：前置 `MED-002`、`MED-007`、`CNT-001`、`DEC-005`；后续 `EXC-002`、`AUT-006`、`QA-001`、`QA-003`、`QA-006`。
- 文件：ImportJob/Item models/migrations、package reader/front matter/markdown/archive parsers、staging/tests。
- 边界：预览不得创建Tag/Article/正式Binding；安全YAML仅标量/列表；上传源任务结束后清理；无普通用户导出。
- 影响：数据：Job/Item预览；权限：author；审计：Job元数据；缓存无；异步：解析可Job；媒体：暂存；通知仅失败终态。
- 测试/验收：RED `64 MiB`/`256 MiB`/`1000` 项/`8` 层/`100:1` 的边界与超限、zip-slip/绝对路径/symlink/恶意 YAML/坏图/HTML XSS；临时目录始终在 job 根并清理。
- 风险/停止：解包前无上限、预览执行HTML或正式表出现任何导入记录即停止。
- 授权：`否`；对未知来源真实包执行需明确安全测试环境。

### EXC-002 实现逐项冲突分类、预览选择与元数据映射
- 元数据：状态 `待处理`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：逐篇分类NEW/重复ID/同标题警告/跨作者冲突/无效；作者选SKIP/UPDATE/CREATE、纳入项、分区/标签映射；无分区进未知，新标签待审即关联。
- 来源：访谈 Q277-Q280；`flows/04-import-export-sequences.md` §判定表；`contracts/01-application-services.md` §exchange。
- 依赖：前置 `EXC-001`、`CNT-010`、`CNT-011`；后续 `EXC-003`、`AUT-006`、`QA-003`、`QA-006`。
- 文件：preview/classifier/decision services、preview version、queries/DTO/forms/tests。
- 边界：ID是唯一更新键；标题仅精确警告；跨作者ID只能跳过；文章归导入者；修改选择递增preview_version。
- 影响：数据：Item决策/映射；权限：导入者/目标owner；审计：决策摘要；缓存无；异步无；媒体：预览引用；通知：跨作者同标题坚持发布后。
- 测试/验收：RED 全判定矩阵、逐项排除、preview并发版本、未知分区/待审标签；Playwright预览/字段错误。
- 风险/停止：允许跨作者更新/另建同ID、标题误作更新键或预览变更静默覆盖即停止。
- 授权：`否`。

### EXC-003 实现幂等确认、逐项事务与部分成功导入
- 元数据：状态 `待处理`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：确认冻结预览后逐项独立事务，成功/跳过/失败均留原因；重复确认不重复写；更新保留历史并可将富文本当前格式改Markdown；成功项不因其他失败回滚；导入警告通过 `OBS-008` 的注册端口扩展 Exchange 模板并生成回执。
- 来源：访谈 Q277-Q280、Q321；`flows/04-import-export-sequences.md` §时序/失败语义；`modules/10-exchange-analytics-maintenance.md` §导入。
- 依赖：前置 `EXC-002`、`CNT-002`、`CNT-007`、`MED-003`、`OBS-006`、`OBS-008`；后续 `AUT-006`、`QA-003`、`QA-004`、`QA-006`。
- 文件：confirm/importer services/tasks、content/media/notification ports、Exchange 通知模板、item idempotency/result UI DTO/tests。
- 边界：不提供整批撤销；格式例外必须写版本原因；媒体仅文章事务成功后绑定；疑似他人标题坚持通过通知注册端口通知管理员，不复制通知模型、文案拼装、去重或回执实现。
- 影响：数据：Job/Item终态+ArticleRevision；权限：author/owner；审计：导入摘要；缓存：发布项失效；异步：Job/TaskRun；媒体：绑定/清理；通知：管理员警告/终败。
- 测试/验收：RED 重复确认、混合有效无效、更新历史、富转Markdown、媒体绑定失败、worker崩溃、Exchange 模板重复事件；逐项 DB/文件/通知 Receipt 读回。
- 风险/停止：重复文章/版本、部分失败全回滚或失败项遗留ACTIVE媒体即停止。
- 授权：`否`。

### EXC-004 建立管理员导出选择、全局并发与任务授权
- 元数据：状态 `待处理`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：仅管理员按全站/作者/分区/选文选择草稿、定时、私人、冷静期及完整历史；数据库保证全站最多一个RUNNING，额外请求拒绝不排队。
- 来源：访谈 Q275-Q283；`data/03-interaction-operations-fields.md` §ExportJob；`data/04-indexes-constraints.md` §全局导出。
- 依赖：前置 `CNT-008`、`CMT-011`、`OBS-004`；后续 `EXC-005`、`ADM-008`、`QA-001`、`QA-003`、`QA-006`。
- 文件：ExportJob/Selection models/migrations、request policy/service/query/forms/tests。
- 边界：普通用户/作者不可导出；选择快照固定；冷静期可选；不生成公开链接；Job接受不等于完成。
- 影响：数据：Job/Selection/部分唯一；权限：admin；审计：请求范围；缓存无；异步：build任务；媒体：归档目标；通知后续。
- 测试/验收：RED 两并发请求仅一RUNNING、所有状态/范围、普通用户伪造；真实PostgreSQL唯一裁决。
- 风险/停止：仅Redis锁、额外请求被隐式排队或选择在执行时漂移即停止。
- 授权：`否`。

### EXC-005 实现导出归档、取消竞态、鉴权下载与三天清理
- 元数据：状态 `待处理`；阶段 P9；owner `exchange`；优先级 P0。
- 目标/行为：ZIP含manifest/JSON、Markdown、TipTap原JSON、全部版本/媒体；写.part后原子完成；管理员可取消未完成、仅本人后台下载；完成包3天删；导出他人内容按作者/日通知。
- 来源：访谈 Q276、Q281-Q283、Q306；`flows/04-import-export-sequences.md` §管理员导出；`contracts/05-background-tasks.md` §取消竞态。
- 依赖：前置 `EXC-004`、`MED-004`、`MED-006`、`OBS-001`、`OBS-006`、`OBS-008`、`OBS-009`；后续 `ADM-008`、`QA-003`、`QA-004`、`QA-006`。
- 文件：exporter/archive/manifest、build/cancel/download/expire services/tasks、tests。
- 边界：Markdown对TipTap仅便利副本不宣称无损；取消保留Job/审计并删.part；完成与取消仅一个终态；无可转发URL。
- 影响：数据：Job终态；权限：admin下载；审计：请求/取消/下载状态；缓存无；异步：build/expire；媒体：ZIP/源；通知：完成/失败/受影响作者。
- 测试/验收：RED取消-完成竞态、双worker、过期、未授权/已过期下载、文件缺失、他人通知去重；真实文件/HTTP读回。
- 风险/停止：部分ZIP可下载、取消删有效完成包、归档路径越界或PRIVATE媒体未授权泄露即停止。
- 授权：`否`；生产导出/下载 `是`。

### EXC-006 实现数据库+媒体周备份、30天保留与人工恢复说明
- 元数据：状态 `待处理`；阶段 P9；owner `operations`；优先级 P0。
- 目标/行为：按 DEC-004 在 `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`）同轮执行 pg_dump+媒体归档，首版仅 `local`、不加密且保留 30 天；成功仅表示命令/文件完成，不自动校验/恢复演练；网页只读记录，恢复服务器人工。
- 来源：访谈 Q148-Q152、Q182、Q189、Q288；`flows/04-import-export-sequences.md` §备份；`modules/10-exchange-analytics-maintenance.md` §备份。
- 依赖：前置 `DEC-004`、`RUN-006`、`OBS-006`、`OBS-007`、`OBS-009`、`OBS-010`；后续 `ADM-008`、`QA-003`、`QA-005`、`QA-006`。
- 文件：BackupRecord、backup/cleanup services/tasks/scripts、Beat schedule、manual restore runbook/tests。
- 边界：不宣称可恢复已验证；无网页下载/恢复；不加密是明确风险；未来外部 adapter 不在首版实现且不得出现在首版 DTO/UI；临时包不算成功。
- 影响：数据：BackupRecord/归档；权限：server-only；审计：设置/记录；缓存无；异步：周/日清理；媒体：全量；通知：最终失败站内+邮件。
- 测试/验收：冻结时钟验证周一 03:00/cron、周幂等、重复调度、非 local 目标拒绝，并模拟 pg_dump/媒体失败/原子改名/30天边界/租约；隔离测试数据执行一次命令并核对记录，不做恢复声明。
- 风险/停止：备份包含.env/秘密、覆盖现有归档、失败标成功或在生产无授权执行即停止。
- 授权：代码/模拟 `否`；真实备份/恢复/清理 `是`。

### EXC-007 集成同源管理员 Umami 与一个月保留
- 元数据：状态 `待处理`；阶段 P9；owner `analytics`；优先级 P1。
- 目标/行为：自托管Umami跟踪公共、登录、私人、个人、管理全部页面；容器无公网端口，仅管理员经同源受控入口访问；每日删除一个月前数据。
- 来源：访谈 Q139-Q140、Q319-Q320；`modules/10-exchange-analytics-maintenance.md` §Umami；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `RUN-001`、`RUN-003`、`DEC-002`、`ACC-001`、`OBS-006`、`OBS-009`；后续 `ADM-008`、`QA-002`、`QA-003`、`QA-005`、`QA-006`。
- 文件：analytics access/proxy/presentation、tracking base integration、retention task/config/tests。
- 边界：Umami不替代产品浏览量/审计/错误；普通用户不能直达dashboard/API；分析数据只留1月；production 缺真实域名或必需秘密时不启用跟踪与管理入口。
- 影响：数据：Umami独立库/清理；权限：admin同源；审计：入口只读不审计；缓存无；异步：每日清理；媒体无；通知：终败。
- 测试/验收：RED 未授权代理/直端口、各页面脚本覆盖、30天边界/重复清理；隔离容器HTTP与DB读回。
- 风险/停止：后台绕过博客认证、秘密暴露给浏览器或清理影响近30天数据即停止。
- 授权：代码 `否`；启动Umami、真实跟踪/数据清理 `是`。

[返回总索引](../implementation-todolist.md)
