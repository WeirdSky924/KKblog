# P12 后迭代任务

本文件只记录 P0-P12 完成后新增的产品迭代，不改变基础清单的 13 个阶段和 102 个历史任务计数。新需求仍需有唯一 owner、验收场景、依赖、权限/数据影响与独立验证记录。

## ITER-001 新用户通知与一次性作者权限申请

- 元数据：状态 `待处理`；阶段 `post-P12`；owner `accounts`；优先级 `P1`。
- 目标/行为：成功注册后管理员收到站内通知；所有已登录用户看见“我的文章”；普通用户进入后只见作者权限提示和一次申请按钮；提交后按钮替换为已通知状态；管理员通知可定位对应账户；作者继续使用原工作台。
- 来源：需求 `Q323`；`requirements-interview.md`；账户、通知与页面状态契约。
- 依赖：既有 `ACC-004` 注册、`ACC-011` 账号角色服务、`OBS-001` 通知/Receipt/Outbox、`AUT-001` 作者路由。
- 文件：`apps/accounts` registration/model/service/event/query/migration；`apps/notifications` consumer/template/target；`config/outbox_transport.py`；`apps/authoring` entry view/template/style；`apps/administration/forms/users.py`；对应测试、架构文档与 Labs 公告记录。
- 边界：不通过申请自动授予 AUTHOR；管理员只使用现有用户管理确认流程；不发送邮件；其它作者工作台命令继续做服务端作者授权。
- 影响：Account 增加 nullable `author_permission_requested_at`；账户行锁保证单次申请；成功注册/申请与 Outbox event 同事务；Notification 消费幂等并只发给启用管理员；管理员目标链接按 UUID 精确筛选。
- 测试/验收：注册 Outbox 读回；普通用户入口和一次提交持久化读回；重复 POST 仅一条事件；作者工作台兼容；管理页 UUID 过滤和通知 target URL；消费重复不产生重复 Notification/Receipt。
- 风险/回滚/停止：迁移前保持字段兼容为 nullable；Labs 迁移未授权时功能代码不能在 Labs 数据库实时使用；Outbox runtime 故障不得通过直接改写事件状态规避。
- 授权：用户已授权本功能代码与隔离测试；Labs migration、生产 migration、部署、服务重启、Git add/commit/push 均未授权。
- 当前证据：聚焦 RED 复现入口隐藏；最终聚焦 GREEN `12 passed in 247.51s`；Ruff lint/format、Django check、CSS 构建及 Labs 只读读回记录在 `docs/releases/2026-10-13-next-iteration/author-permission-request-20261016.md`。Labs schema migration 与认证态浏览器流仍待授权/会话。

## ITER-002 管理员邮件密码重置

- 元数据：状态 `待处理`；阶段 `post-P12`；owner `accounts`；优先级 `P1`。当前会话先实现 ITER-003；本项剩余真实认证态浏览器/隔离邮件验收继续保留，不视为已完成。
- 目标/行为：管理员从用户管理中确认发送密码重置邮件；用户点击邮件链接，在 30 分钟内输入并确认新密码；链接只可使用一次；成功后清除强制改密状态并撤销目标账户全部现有会话，不自动登录。
- 来源：用户 2026-10-16 明确指令。
- 依赖：既有账号邮件发送、密码强度校验、LoginSession、用户管理确认弹窗、operations AuditEntry。
- 文件：`apps/accounts/models/admin_password_reset.py`、`services/admin_password_reset.py`、独立重置 view/form/template/JS、`accounts.0011_admin_password_reset`、用户管理确认入口、审计 schema、账户架构/页面矩阵和 Labs 独立更新记录。
- 边界：邮件只发给目标账户绑定邮箱；原始 token 不入库/审计/日志，URL fragment 读取后移除；重发覆盖旧链接；凭据变化使旧链接失效；禁用状态不因重置变化。仅测试 Mailpit，不发送真实邮件。
- 影响：新增 `account_admin_password_reset` 一对一表；token 摘要以服务器密钥 HMAC 并绑定当前 password hash 与 email；`expires_at > created_at`；管理员请求审计和账户安全事件不包含令牌。
- 测试/验收：管理员授权/确认、Mailpit 邮件真实读回、精确 30 分钟期限、重发/过期/凭据变化失效、密码确认和强度、一次性消费、全部会话撤销、非管理员拒绝、错误与隐私响应头、真实页面交互。
- 风险/回滚/停止：migration 仅增加独立表；迁移未应用时页面服务返回安全不可用错误，不执行共享数据写入；如迁移失败，保留当前 schema 且不启用兑换。生产 migration/部署/真实邮件/服务重启均不在本任务授权内。
- 授权：代码与隔离验证由当前功能请求授权；新 Labs migration `accounts.0011_admin_password_reset` 尚未授权。生产操作、真实邮件和 Git 写入未授权。
- 当前证据：RED 路由回归实现前 `1 failed in 3.03s`；目标 Ruff、JS 语法、Django check、migration autodetector 和 diff check 退出 `0`；前端构建完成。Labs live 与匿名兑换页 `200`，390px 真实浏览器确认 fragment 清除、表单可见、无横溢及 Tab 焦点顺序。隔离 pytest 未运行（4 项 `KAJ_TEST_*` 缺失）；没有执行新 migration、邮件发送或真实管理员/用户兑换流。详情见 `docs/releases/2026-10-13-next-iteration/admin-password-reset-20261016.md`。

## ITER-003 登录用户文章专注模式

- 元数据：状态 `已实现（Labs）`；阶段 `post-P12`；主用户流 owner `discovery`；全站策略配置 owner `navigation`；优先级 `P1`。
- 目标/行为：沿用当前登录用户公开文章的 `article-reading-tools` 工具栏和展开胶囊，提供专注开始/结束、手动暂停/继续、失焦/页面隐藏/鼠标离开视口/配置时长无操作自动暂停提醒；第三次手动暂停结束会话。工具栏只保留专注入口；活动计时、圆形暂停图标和纯文本暂停次数在页面左下角计时区单行排列。手动暂停显示黄色页面边缘流光，失焦/无操作告警显示红色流光，正常状态不显示流光。
- 配置：管理员在“内容与互动”的文章阅读设置中配置无操作阈值（默认 3 分钟、1..15 分钟）和单次专注手动暂停上限（默认 3 次、1..10 次）；自动暂停不计入次数。配置沿用 SiteConfiguration 版本校验与审计。
- 来源：用户 2026-10-20 明确需求及后续架构边界确认；文章工具栏继续只对登录用户、公开文章显示，不调整外层工具栏架构。
- 依赖：现有 `article_explanation_settings` query/service、`SiteConfiguration`、文章阅读工具栏和全局操作反馈。
- 文件：`apps/navigation` 配置字段/迁移/query/service/audit schema，`apps/administration` 表单和设置页，`apps/discovery` 文章页上下文/模板，独立 `static/src/article-focus.js` 与阅读样式/构建产物；同步 discovery、navigation、admin 架构及页面契约、独立公告记录。
- 边界：会话时长与状态仅在当前页面内存中，不写账号偏好、服务端历史或遥测；浏览器拒绝全屏时明确提醒但允许继续；页面不能强制抢回浏览器/操作系统焦点，失焦只暂停并提醒；当前会话冻结启动时配置；不改变匿名用户可见性和工具栏根结构。
- 影响：`SiteConfiguration` 增加两个带数据库范围约束的数值字段，新增 `navigation.0009`；仅目标 Labs 测试数据库应用，不做生产 migration、部署、服务重启、邮件或招聘采集。
- 测试/验收：设置默认值、上下界/非法值/非管理员拒绝、row_version 冲突、AuditEntry before/after 与读回；文章匿名不渲染工具、登录公开文章含真实配置；浏览器验证全屏请求、运行/暂停时钟、自动暂停不计数、手动第三次结束、失焦恢复、窄屏 timer/工具栏不重叠、Reduced Motion 和 Labs health/static 读回。
- 风险/停止：全屏及窗口聚焦受浏览器安全策略限制；只能报告全屏失败并提供普通页面继续方式，不能声称可以强制抢焦点。缺少获授权登录态时不创建/借用 Labs 真实账户，改用隔离浏览器测试会话并说明限制。
- 授权：当前用户请求覆盖本功能代码、隔离测试及必要的 Labs 测试 schema 更新；生产 migration/deploy、服务/容器重启、真实邮件、Provider/AGENT、招聘采集和 Git add/commit/push 均未授权。
- 当前证据：初始实现回归 `11 passed in 199.74s`；左下计时区/展开工具栏几何、图标显隐与主题颜色已读回。边缘光晕已迭代为灼烧式循环后再收窄至上下 `22%`、左右 `24%`，动态 blur `7–18px`、内阴影最大 `56px`。window blur/focus 和 pointerout/pointerover 在实际 Labs app bundle 中读回自动暂停/恢复/清除光效；手动暂停保持、结束清理均读回通过。CSS/JS build 与语法检查通过，Labs 首页最终版本 `article-focus-return-20261021g`；CSS/JS hash 分别为 `6feedc6d28ec5e4677c9d9d80eb9b8027da28832ad849da508119f8d6abff59d` 和 `dfbf689ad4ed6e7ea1d063a5f80bc7d8873a3b910aeab125144feb9c507a905a`，本地/公网一致，health `200`。工具栏 padding-only 首次微调无可见变化，根因是胶囊 `max-width:12rem` 导致按钮收缩/裁切；当前已扩为桌面 `22rem`、按钮禁止收缩、padding `1.5rem`，窄屏按视口限宽且 padding `0.75rem`。最终 CSS cache key `article-reading-toolbar-fit-20261021i`，hash `72a614c68a55c316160b79a8c5bc7532d833eb18d9a05b6ee056173bee1a87e`，本地/公网一致，health `200`。按用户要求不做浏览器验收，由用户自行检查观感。专注模式与工具栏修正记录见对应 Labs 切片文档。

## ITER-004 手机版文章阅读模式

- 元数据：状态 `已实现（Labs；待用户手机验收）`；阶段 `post-P12`；owner `discovery`；优先级 `P1`。
- 目标/行为：手机版文章右侧快捷操作栏增加阅读模式按钮；阅读页支持连续滚动、左右翻页、上下单页手势翻页、文章目录、页码/进度和字号调整，并提供日间/护眼/深色外观。左右模式点击区域分为左/中/右：上/下一页和顶部设置显隐；上下模式单击页面切换顶部设置显隐。两种分页模式的设置均浮在正文上方，不改变正文视口尺寸；首次左右翻页或上下滑动后自动收起设置。左右模式底部只保留居中页码；上下模式上划/下划一次固定翻一屏，不跟手自由滚动。
- 来源：用户 2026-10-21 要求手机版增加小说阅读器式的多种阅读方式，并指定入口位于文章右侧点赞操作栏且只在手机版出现。
- 依赖：公开文章 `article:detail`、既有移动端文章操作 dock、主题 token、已清洗的 `.article-prose` 与目录锚点。
- 边界：仅公开文章页面客户端行为；模式、主题与字号偏好保存在浏览器 `localStorage`，不增加账户字段、API、数据库写入或 migration。正文节点在阅读对话框打开期间移入阅读视口，关闭后恢复原 DOM 与进入前的页面滚动位置。
- 文件：文章详情模板、`static/src/article-reader-mode.js`、`app.js`、`discovery.css`、`bookmarks.css`、静态资源缓存版本、文章阅读架构/页面契约与本轮 Labs 公告记录。
- 测试/验收：语法、CSS/JS 构建、差异检查、Labs health 和文章页静态资源版本读回；真实手机交互由用户验收，覆盖入口显隐、三种阅读方式、左右三分区与设置显隐（设置覆盖正文且不改变正文视口尺寸）、上下单次手势一屏、目录跳转、字号/主题、旋转重排及退出位置恢复。
- 风险/停止：浏览器多列分页对长代码块、表格与嵌入内容的断页体验需真实手机确认；不执行生产操作、服务重启或 Git 写入。
