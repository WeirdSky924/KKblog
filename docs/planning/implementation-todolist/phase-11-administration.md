# P11 管理后台、导航与站点设置（8）

退出门禁：管理后台、导航树、站点设置和所有领域写操作均重判权限并与审计同成败。

### ADM-001 实现无仪表盘的管理后台外壳与统一权限
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：唯一管理员从个人菜单直达功能入口；桌面窄侧栏、手机横向/菜单模块导航；普通用户/作者所有管理URL和HTMX均服务端拒绝。
- 来源：访谈 Q104、Q168、Q241-Q253；`modules/08-administration-navigation.md` §后台原则/UI；原型全部管理页。
- 依赖：前置 `RUN-005`、`ACC-001`、`FND-004`；后续 `ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-003`、`QA-006`。
- 文件：admin navigation registry/layout/templates、permission mixin/policy adapter、shared table/dialog shells/tests。
- 边界：不建空仪表盘；代码模块导航不等于数据库公共导航；共享shell不承载领域规则；Django admin不写高风险模型。
- 影响：数据无事实；权限：admin全入口；审计由领域写服务；缓存禁用户串；异步/媒体/通知仅展示槽。
- 测试/验收：RED 普通用户/作者直接GET/POST/HTMX；Playwright桌面/390/768导航、焦点、长ID、空/错误/禁用。
- 风险/停止：任一管理写绕过service/audit、手机主要操作不可达或UI路由成为授权即停止。
- 授权：`否`。

### ADM-002 实现用户、作者角色、禁用/启用与账户删除管理
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：管理员按邮箱/昵称搜索、正常/禁用筛选，授予/撤销作者、禁用/启用、删除非管理员；删除作者前明确文章处理/可选导出提醒。
- 来源：访谈 Q130-Q134、Q284-Q301；`contracts/03-frontend-contract-map.md` §admin:users；原型 users。
- 依赖：前置 `ADM-001`、`ACC-007`、`ACC-011`、`CNT-009`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：user query/presenter/forms/views/templates/confirm dialogs/tests。
- 边界：administration只委托accounts/content/exchange；不能授权第二管理员、自删、代看收藏/会话或转移文章。
- 影响：数据：委托账户/角色/删除；权限：admin；审计：每写；缓存：账户/内容失效事件；异步：删除收敛；媒体：头像/文章清理；通知：角色变化。
- 测试/验收：Playwright搜索/筛选/授予/撤销/禁用/启用/删除确认，普通用户伪造POST；三方DB/通知/审计读回。
- 风险/停止：删除提示遗漏文章后果、部分跨域成功或禁用后会话/文章仍可见即停止。
- 授权：`否`；生产账户管理动作 `是`。

### ADM-003 实现邀请码、IP 与临时安全限制管理
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：提供邀请码1..1000生成/一次原码/状态筛选/批量撤销/使用者详情；IP掩码列表/完整详情/备注/解封；清账户/IP验证码限制与登录限制。
- 来源：访谈 Q126-Q134、Q226-Q229、Q292-Q294；`contracts/03-frontend-contract-map.md` §invites/ip；原型 notifications/users。
- 依赖：前置 `ADM-001`、`ACC-002`、`ACC-009`、`ACC-010`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：admin invite/ip/security views/presenters/forms/partials/tests。
- 边界：列表不显示邀请码原码/完整IP；备注不对用户；清除范围明确；不在管理页复制生成/封禁算法。
- 影响：数据：委托Invite/IpBlock/Redis限制；权限：admin；审计：全部写；缓存：清Redis；异步无；媒体/通知无。
- 测试/验收：Playwright批量边界、状态/掩码/详情、撤销/解封/清限；DB+Redis+审计读回。
- 风险/停止：原码可回看、列表泄露IP、清除所有用户限制或普通管理员URL绕过即停止。
- 授权：`否`；真实IP封禁/解封 `是`。

### ADM-004 实现文章、评论、举报和申诉管理队列
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P0。
- 目标/行为：管理员查看任意文章并触发按日通知，只能隐藏已发布、删除/恢复；管理缓冲/按文章评论、直接删除理由、举报初审/申诉终局与证据详情。
- 来源：访谈 Q105-Q125、Q302-Q313；`contracts/03-frontend-contract-map.md` §admin articles/comments/reports；原型 moderation/interactive-report。
- 依赖：前置 `ADM-001`、`CNT-005`、`CMT-006`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-004`；后续 `QA-002`、`QA-003`、`QA-006`。
- 文件：admin content/comment/report presenters/views/templates/actions/tests。
- 边界：不能编辑/发布/排期/改他人设置；列表隐藏reporter/IP，详情按权限；所有动作委托content/comments/moderation。
- 影响：数据：委托案件/内容/评论；权限：admin例外；审计：全部写；缓存：内容即时失效；异步：通知/清理；媒体：证据/评论图；通知：作者/双方。
- 测试/验收：Playwright 查看同日去重、隐藏/恢复/删除/申诉、举报隐私/终局、直接删原因；伪造禁用动作。
- 风险/停止：管理页拥有第二套状态机、举报人泄露或管理员越权代编即停止。
- 授权：`否`；生产内容裁决 `是`。

### ADM-005 实现标签审核/历史与分区管理界面
- 元数据：状态 `待处理`；阶段 P11；owner `administration`；优先级 P1。
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
