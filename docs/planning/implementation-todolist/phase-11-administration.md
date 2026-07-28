# P11 管理后台、导航与站点设置（8）

退出门禁：管理后台、导航树、站点设置和所有领域写操作均重判权限并与审计同成败。

### ADM-001 实现无仪表盘的管理后台外壳与统一权限
- 元数据：状态 `完成`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：唯一管理员从个人菜单直达功能入口；桌面窄侧栏、手机横向/菜单模块导航；普通用户/作者所有管理URL和HTMX均服务端拒绝。
- 来源：访谈 Q104、Q168、Q241-Q253；`modules/08-administration-navigation.md` §后台原则/UI；原型全部管理页。
- 依赖：前置 `RUN-005`、`ACC-001`、`FND-004`；后续 `ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-003`、`QA-006`。
- 文件：admin navigation registry/layout/templates、permission mixin/policy adapter、shared table/dialog shells/tests。
- 边界：不建空仪表盘；代码模块导航不等于数据库公共导航；共享shell不承载领域规则；Django admin不写高风险模型。
- 影响：数据无事实；权限：admin全入口；审计由领域写服务；缓存禁用户串；异步/媒体/通知仅展示槽。
- 测试/验收：RED 普通用户/作者直接GET/POST/HTMX；Playwright桌面/390/768导航、焦点、长ID、空/错误/禁用。
- 风险/停止：任一管理写绕过service/audit、手机主要操作不可达或UI路由成为授权即停止。
- 证据：RED `.venv/bin/pytest -q apps/administration/tests/test_adm001.py` 在实现前退出 1，准确因 `admin:index` 不存在触发 `NoReverseMatch`；最小实现加入代码导航注册表、统一 `administrator_required`、无仪表盘直达入口、共享管理布局和响应式模块导航，领域写端点仍由原 owner service 最终授权与审计。当前 GREEN 同命令退出 0，`2 passed in 6.75s`；相关 administration/accounts/analytics/operations/前端与 HTTP 安全回归退出 0，`38 passed in 17.37s`；目标 Ruff 与 format 检查分别退出 0，26 个文件格式正确。隔离 PostgreSQL/Redis/Mailpit 中以真实 visitor/user/author/admin 身份读回：管理员 `/admin/` 302 到 `/admin/invites/`，其余三身份均 403，GET/POST/HTMX 权限探针均拒绝；授权页响应 `private, no-store` 且 `Vary: Cookie`。`blog-playwright-cli` 真实 Chrome 验证 1440 light、768 eye-care、390 dark：文档宽分别等于视口，桌面侧栏与移动横向导航按断点互斥，390 导航 `390/510` 可受控横滚，表单控件保持 16px 安全边距且提交按钮 44px；空邀请码、IP、群发、错误页面均保留壳层，审计非法日期诚实返回 422，未配置 Umami 诚实返回 503；首个 Tab 聚焦跳转链接，Enter 后焦点为 `#main-content`。临时 RED/GREEN 测试和浏览器运行产物均已清理/忽略；未执行生产数据、生产 migration、真实邮件、部署、提交或推送。后续模块仅扩展注册表和 owner DTO，不改变本卡权限边界。
- 授权：`否`。

### ADM-002 实现用户、作者角色、禁用/启用与账户删除管理
- 元数据：状态 `完成`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：管理员按邮箱/昵称搜索、正常/禁用筛选，授予/撤销作者、禁用/启用、删除非管理员；删除作者前明确文章处理/可选导出提醒。
- 来源：访谈 Q130-Q134、Q284-Q301；`contracts/03-frontend-contract-map.md` §admin:users；原型 users。
- 依赖：前置 `ADM-001`、`ACC-007`、`ACC-011`、`CNT-009`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：user query/presenter/forms/views/templates/confirm dialogs/tests。
- 边界：administration只委托accounts/content/exchange；不能授权第二管理员、自删、代看收藏/会话或转移文章。
- 影响：数据：委托账户/角色/删除；权限：admin；审计：每写；缓存：账户/内容失效事件；异步：删除收敛；媒体：头像/文章清理；通知：角色变化。
- 测试/验收：Playwright搜索/筛选/授予/撤销/禁用/启用/删除确认，普通用户伪造POST；三方DB/通知/审计读回。
- 风险/停止：删除提示遗漏文章后果、部分跨域成功或禁用后会话/文章仍可见即停止。
- 证据：RED `.venv/bin/pytest -q tests/test_adm002_temp.py` 在实现前退出 1，`3 failed`，均因 `admin:users` 路由缺失；实现 accounts 管理查询、administration presenter/form/view/template 以及 content owner 的账户文章事务处置，管理页仅委托既有账户生命周期与审计/Outbox 端口，不提供第二管理员、自删、会话/收藏代看或文章转移。聚焦 GREEN 同一临时测试退出 0，`4 passed in 9.73s`；新增逐文章缓存失效事件的聚焦测试退出 0，`1 passed in 6.04s`；administration/accounts/notifications/架构相关回归退出 0，`17 passed in 12.20s`，content 删除/禁用与架构回归退出 0，`14 passed in 13.16s`。目标 Ruff lint/format、Django check、migration drift、正式前端 build 与 `git diff --check` 均退出 0。隔离 PostgreSQL/Redis/Mailpit 真实读回：角色授予后撤销、账户禁用后启用，最终目标账户为 ACTIVE 且非作者；永久删除另一作者后账户与 1 篇文章均不存在，`AccountDeletion=delete_all/article_count=1`，角色/状态/删除 AuditEntry 分别 2/2/1，角色通知 Receipt 2；Outbox 两批 `5+2` 条全部发布、失败 0、待发布 0，物理文章清理另写 `article.purge_requested.v1` 供 discovery 失效。`blog-playwright-cli` 以真实管理员验证邮箱/昵称搜索、角色授予/撤销、禁用/启用、删除 1 篇文章后果及导出提醒、唯一管理员保护和成功态；确认框初始焦点为取消，Escape/取消清理确认参数并精确恢复原触发点。1440 light、768 eye-care、390 dark 文档宽等于视口，表格只在本地横滚，操作控件高度至少 44px，无重叠/裁切；临时测试、浏览器、runserver 与 P11 隔离容器均已清理。实现提交 `fecd60a` 已 fast-forward 进入远端 `main`；未执行生产账户、生产 migration、真实邮件、部署或服务重启。
- 授权：`否`；生产账户管理动作 `是`。

### ADM-003 实现邀请码、IP 与临时安全限制管理
- 元数据：状态 `完成`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：提供邀请码1..1000生成/一次原码/状态筛选/批量撤销/使用者详情；IP掩码列表/完整详情/备注/解封；清账户/IP验证码限制与登录限制。
- 来源：访谈 Q126-Q134、Q226-Q229、Q292-Q294；`contracts/03-frontend-contract-map.md` §invites/ip；原型 notifications/users。
- 依赖：前置 `ADM-001`、`ACC-002`、`ACC-009`、`ACC-010`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：admin invite/ip/security views/presenters/forms/partials/tests。
- 边界：列表不显示邀请码原码/完整IP；备注不对用户；清除范围明确；不在管理页复制生成/封禁算法。
- 影响：数据：委托Invite/IpBlock/Redis限制；权限：admin；审计：全部写；缓存：清Redis；异步无；媒体/通知无。
- 测试/验收：Playwright批量边界、状态/掩码/详情、撤销/解封/清限；DB+Redis+审计读回。
- 风险/停止：原码可回看、列表泄露IP、清除所有用户限制或普通管理员URL绕过即停止。
- 证据：聚焦 RED `.venv/bin/pytest -q tests/test_adm003_temp.py` 在实现前退出 1，`3 failed`，分别准确暴露已用邀请码缺少账户详情、账户限制确认返回 404 和 IP 清限预览返回 422；实现只扩展 accounts owner 的邀请码 query/service 门面、限制清理端口和既有 administration form/view/template，不复制邀请码、封禁或 Redis 算法。聚焦 GREEN 同命令退出 0，`3 passed in 6.60s`；最终权限/安全错误探针与 ACC-002/009/010、现有 administration 回归退出 0，`27 passed in 15.78s`，其中普通账户对三页 GET/POST 均 403，限制 service 二次授权，未处理异常进入不泄密 500。目标 Ruff lint/format、Django check、正式前端 build 与 `git diff --check` 均退出 0。隔离 PostgreSQL/Redis/Mailpit 与真实 Chrome 读回：生成响应一次展示 16 字符 Crockford 原码，离开后历史只显示尾号；当前 2 条 REVOKED、1 条 USED，使用记录打开 `adm003-user@kaj.test` 详情；账户清限后密码失败、一小时登录限制和该账户邮箱计数三个键均不存在且登录不受限，目标 IP 计数为 0，另有 2 个邮箱键和 2 个 IP 键各保留值 1；旧 `198.51.100.201` 封禁已解除，新 `198.51.100.202` 封禁保持有效。10 条相关 AuditEntry 覆盖生成/撤销/封禁/解封/清限，审计安全字段不含目标完整 IP，邀请码持久字段只有 digest/尾号等且没有原码。`blog-playwright-cli` 验证 1440 light、768 eye-care、390 dark：三页文档宽等于视口，访问管理表在 390 为 `358→736` 局部滚动且键盘 ArrowRight 可达，三页无重复 ID，IP 输入各有唯一 label；撤销/清限确认初始焦点为取消，Escape 清理 query 并精确恢复触发点；无效 IP 与筛选返回 422、保留输入/显示安全错误，最终控制台 0 错误。浏览器、runserver、临时测试和截图已清理；P11 隔离支持容器留给下一任务。未执行生产 IP 封禁/解封、生产限制清理、生产 migration、真实邮件、部署、提交或推送。
- 授权：`否`；真实IP封禁/解封 `是`。

### ADM-004 实现文章、评论、举报和申诉管理队列
- 元数据：状态 `完成`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：管理员查看任意文章并触发按日通知，只能隐藏已发布、删除/恢复；管理缓冲/按文章评论、直接删除理由、举报初审/申诉终局与证据详情。
- 来源：访谈 Q105-Q125、Q302-Q313；`contracts/03-frontend-contract-map.md` §admin articles/comments/reports；原型 moderation/interactive-report。
- 依赖：前置 `ADM-001`、`CNT-005`、`CMT-006`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：admin content/comment/report presenters/views/templates/actions/tests。
- 边界：不能编辑/发布/排期/改他人设置；列表隐藏reporter/IP，详情按权限；所有动作委托content/comments/moderation。
- 影响：数据：委托案件/内容/评论；权限：admin例外；审计：全部写；缓存：内容即时失效；异步：通知/清理；媒体：证据/评论图；通知：作者/双方。
- 测试/验收：Playwright 查看同日去重、隐藏/恢复/删除/申诉、举报隐私/终局、直接删原因；伪造禁用动作。
- 风险/停止：管理页拥有第二套状态机、举报人泄露或管理员越权代编即停止。
- 证据：聚焦 RED `tests/test_adm004_temp.py` 在实现前退出 1，准确因 `admin:articles`、`admin:comments`、`admin:reports` 路由缺失触发 `NoReverseMatch`；实现扩展 content/comments/moderation owner 的管理员 query DTO，administration 只组合只读展示、表单和既有 `article_for_admin`、文章案件、评论直删、举报初审/终局 service。实现中发现 `docs/architecture/01-system-directory.md` 与可执行依赖门禁遗漏任务卡/前端契约明确要求的 `administration -> comments`，已同步补齐该允许边；comments 自身仍通过既有 `CommentAccountPolicy` 访问账户能力，没有形成反向依赖或第二状态机。聚焦 GREEN 覆盖普通账户三路由 GET/POST 403、只读查看上海日去重、隐藏/恢复、删除后文章申诉准许、评论直删可选原因、举报列表隐私/详情身份与完整 IP、初审删除恢复快照和终局撤销恢复，退出 0，`4 passed in 8.46s`；三类超长原因均 422、保留输入且不改事实。最终 CNT-005、CMT-001..004、媒体私有访问、审计、架构、前端与 HTTP 安全相关回归退出 0，`56 passed in 28.58s`；目标 Ruff lint/format、Django check、正式前端 build 与 `git diff --check` 均退出 0。隔离 PostgreSQL/Redis/Mailpit 真实读回：管理员对同一私人文章重复查看只有 1 条 `AdminArticleViewReceipt` 和 1 个日去重通知回执；隐藏案件终态 `RESTORED`，删除申诉案件终态 `FINAL_REJECTED`，两篇文章均恢复为 `PUBLISHED/deleted_at=NULL`；两条直接删除评论均为 `DELETED/ADMIN`，一条保留可选原因、一条使用通用原因；举报分别为 `UPHELD` 与 `FINAL_UPHELD`，终局申诉同为 `FINAL_UPHELD`，初审成立案件保留 1 份受限恢复快照。11 条 Outbox 全部发布、0 待处理/失败，并生成文章查看/裁决/恢复、评论删除、举报初审/终局通知回执；12 条相关 AuditEntry 与全部 Outbox payload 均不含 4 个目标完整 IP。`blog-playwright-cli` 真实 Chrome 验证文章查看、隐藏/恢复、文章申诉详情/准许，评论缓冲/按内容分组/掩码列表/完整 IP 详情/直删，以及举报列表隐私/详情/初审/终局；确认框初始焦点为取消，Escape 精确恢复触发点，成功重定向保留案件或线程读回上下文。三路由在 1440 light、768 eye-care、390 dark 均为 HTTP 200、文档宽等于视口、无重复 ID；密集表格只在局部横滚，390 举报表为 `358→1024` 且 ArrowRight 可达，操作控件高度至少 44px，最终控制台 0 错误。临时测试、runserver、浏览器与临时脚本已清理；P11 隔离支持容器保留给下一任务。未执行生产内容裁决、生产 migration、真实邮件、部署、提交或推送。
- 授权：`否`；生产内容裁决 `是`。

### ADM-005 实现标签审核/历史与分区管理界面
- 元数据：状态 `进行中`；阶段 P11；owner `administration`；优先级 P1。
- 目标/行为：待审标签通过/驳回、全站标签新增/删除/恢复及冲突；分区唯一新增/删除并明确文章转未知分区；列表含空/错误/重复提交状态。
- 来源：访谈 Q054-Q061、Q256-Q258；`contracts/03-frontend-contract-map.md` §admin tags/sections；原型 adminrecords。
- 依赖：前置 `ADM-001`、`CNT-010`、`CNT-011`、`OBS-004`；后续 `ADM-006`、`QA-003`、`QA-006`。
- 文件：tag/section admin views/presenters/forms/dialogs/tests。
- 边界：不直接写分类表；删除标签/分区的影响必须在确认中明确；恢复超10冲突不得隐藏。
- 影响：数据：委托分类；权限：admin；审计：全部写；缓存：列表/文章失效；异步：标签通知；媒体无；通知：作者/冲突。
- 测试/验收：Playwright待审→通过/驳回、删除→旧链接空→恢复、分区删除→未知；DB/通知/审计读回。
- 风险/停止：确认文案与真实级联不符、UI静默丢关联或缓存不更新即停止。
- 授权：`否`。

### ADM-006 实现三层公共导航树拖拽、隐藏与并发保护
- 元数据：状态 `待处理`；阶段 P11；owner `navigation`；优先级 P1。
- 目标/行为：管理员管理站内页/分区/外链节点，任意合法位置、最多三层、可隐藏；拖拽提交子树版本令牌，无环/连续排序；移动端子项可展开。
- 来源：访谈 Q241、Q247-Q248；`modules/08-administration-navigation.md` §导航树；`data/04-indexes-constraints.md` §navigation。
- 依赖：前置 `ADM-001`、`ADM-005`、`DSC-001`、`DSC-003`、`OBS-004`；后续 `QA-001`、`QA-003`、`QA-006`。
- 文件：NavigationNode model/migration/tree service/query/version DTO、drag UI/mobile preview/tests。
- 边界：管理模块侧栏不入此树；外链安全新标签；分区删除后目标失效需明确处理；无静默覆盖。
- 影响：数据：树/排序/version；权限：admin写/公众读；审计：整棵受影响前后；缓存：Header失效；异步无；媒体无；通知无。
- 测试/验收：RED环/深度4/并发拖拽/隐藏/删除目标/恶意URL；Playwright拖放、键盘替代、390展开。
- 风险/停止：树损坏导致全站导航不可用、无键盘路径或冲突last-write-wins即停止。
- 授权：`否`。

### ADM-007 实现站点设置、品牌、静态页、友情链接、可信嵌入与留言设置
- 元数据：状态 `待处理`；阶段 P11；owner `navigation`；优先级 P1。
- 目标/行为：分组设置站名/空描述/版权/注册开关/正文限制（默认 `2 MiB`，仅可配 `64 KiB` 至 `2 MiB`）/Logo/favicon；About/Privacy/Terms 富文本或 Markdown 且空时隐藏；友情链接 CRUD；Bilibili 来源；留言开关/登录要求。
- 来源：访谈 Q158-Q165、Q209-Q210、Q231-Q240、Q253、Q312-Q314；`modules/08-administration-navigation.md` §站点与公开内容；DEC-004/005。
- 依赖：前置 `ADM-001`、`MED-005`、`MED-007`、`CMT-007`、`OBS-004`、`DEC-004`、`DEC-005`；后续 `QA-003`、`QA-006`。
- 文件：SiteConfiguration/StaticPage/FriendLink/TrustedSource models/services/queries、admin/public templates/tests。
- 边界：不把 `.env`/备份凭据放网页；备份目标首版只展示/保存 `local`，不出现未实现外部选项；空法律页无同意框；来源移除旧嵌入占位。
- 影响：数据：配置/静态页/链接/来源；权限：admin写/公众已发布读；审计：全部写；缓存：Header/渲染失效；异步无；媒体：Logo/Friend；通知无。
- 测试/验收：服务端 RED 拒绝正文限制 `<64 KiB` 或 `>2 MiB`；Playwright 配置→前台即时读回、备份目标仅 `local` 且不可构造外部值、空/非空页面、Logo/favicon、恶意 URL、正文限制；1440/390 三主题。
- 风险/停止：设置JSON大桶、秘密进入审计/页面、空法律链接出现或旧嵌入继续执行即停止。
- 授权：`否`；真实品牌素材/外部URL确认按需要 `是`。

### ADM-008 整合通知、审计、错误、任务、备份、交换与 Umami 管理入口
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P1。
- 目标/行为：在统一管理外壳中提供群发/读回、审计/错误/任务/健康、导入导出、备份只读记录与Umami入口；后台Job只显示真实状态，无网页重试/恢复/部署按钮。
- 来源：访谈 Q140、Q189、Q195-Q203、Q224-Q225、Q253；`contracts/03-frontend-contract-map.md` §管理员页面；原型 notifications/exchange/operations。
- 依赖：前置 `ADM-001`、`OBS-002`、`OBS-003`、`OBS-004`、`OBS-005`、`OBS-006`、`OBS-007`、`EXC-004`、`EXC-005`、`EXC-006`、`EXC-007`；后续 `QA-003`、`QA-006`。
- 文件：administration adapters/presenters/routes/templates for owner queries/tests。
- 边界：只编排，不拥有Notification/Audit/Job/Backup/Analytics事实；无手动task retry、网页backup restore、.env编辑、部署按钮。
- 影响：数据：只读/委托；权限：admin；审计：写动作owner；缓存无；异步：状态展示；媒体：导出下载；通知：群发/告警。
- 测试/验收：Playwright每入口、空/运行/失败/过期/权限态、390/768/1440；对应DB/文件/Umami代理读回。
- 风险/停止：页面显示假完成、绕过owner下载/查看、把内部endpoint/JSON暴露给管理员主界面即停止。
- 授权：`否`；真实Umami/备份/导出运行按各任务授权。

[返回总索引](../implementation-todolist.md)
