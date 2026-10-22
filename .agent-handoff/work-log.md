# Current Work Log

## 2026-10-22（阅读模式翻页与设置显隐修正）

- 用户要求左右模式顶部设置在开始翻页后收起、中间区点击显隐、左右区翻页、底部仅保留页码，并修正两侧露出邻页内容；随后明确上下模式每次手势只翻一页，正文不跟随拖动。
- 阅读器左右点击采用视口三分区，键盘方向键/Enter 支持同类操作；首次侧区翻页后隐藏标题和设置，显示中央页码。设置区显隐后按相对阅读进度重新排版。
- 横向 CSS 多列宽度和位移统一使用 `.article-reader-mode__content` 实际宽度，并由该内层容器裁切相邻页。上下模式以 `clientHeight` 为步长、上划下一页/下划上一页，禁用触屏纵向原生拖动但保留 pinch zoom。
- 模板移除了底部前后页按钮。同步更新 discovery 架构、页面状态矩阵、ITER-004、公告台账，并新建 `article-reader-controls-20261022.md`。
- Validation: JS syntax、diff check、CSS/JS build exit `0`；Labs article page 读回版本 `article-reader-controls-20261022a`、页码且无前后按钮；service `active/running`、health `200`；CSS/JS 本地与公网 hash 分别一致为 `8718e904…74da9c4f` / `5f22b729…b997e92610`。
- User preference: 未启动浏览器，触控动作与分页观感交由用户实机验收。无生产操作、服务重启、migration 或 Git 写操作。

## 2026-10-21（手机版文章阅读模式）

- 用户指定文章右侧点赞操作栏内增加手机版专用阅读入口；阅读模式需有小说阅读器式多种阅读方式。
- 在 `article:detail` 增加移动端 dock 按钮和原生 dialog 阅读器：连续滚动、CSS 多列左右翻页、按屏高度吸附的上下翻页、目录跳转、进度、字号和站点三主题。阅读偏好在浏览器 localStorage；打开时复用原正文 DOM，关闭时恢复节点和原窗口滚动位置。
- 新增 `static/src/article-reader-mode.js` 并接入 app 初始化/清理；更新文章、操作栏样式与静态缓存版本。同步 post-P12 ITER-004、发现阅读模块/前端契约/页面矩阵和下一轮公告台账；无 API、迁移或服务器数据副作用。
- Validation: `node --check` 和 `git diff --check` exit `0`；`npm run build:css`、`npm run build:js` exit `0`。Labs article page 读回入口/模式控件与最终版本 `article-reader-mode-20261021c`，`kaj-labs.service=active/running`、`/health/live=200`；本地/公网 CSS `94716682…173a4f75`、JS `ef032076…a9e2600c` hash 一致。
- User preference: 不启动浏览器；手机触控、阅读排版和视觉体验留用户实机验收。未执行 production migration/deploy/restart、Git 写操作、真实邮件、招聘采集或 Provider/AGENT。

## 2026-10-21（修正工具栏胶囊挤压按钮）

- Report: 用户确认首次增加按钮 padding 后视觉没有变化。
- Root cause: `.article-reading-tools__capsule` 的 `max-width:12rem` 小于两个完整按钮所需宽度，`overflow:hidden` 又裁切溢出内容；按钮受 flex shrink 被挤压。
- Changed: 桌面 capsule max-width 增至 `22rem`、窄屏按 `calc(100vw - 4.5rem)` 限定；按钮设 `flex:0 0 auto`，padding 为桌面 `1.5rem`、窄屏 `0.75rem`；CSS cache key 改为 `article-reading-toolbar-fit-20261021i`。新建 correction 文档并更正前一条公告和 ITER-003 记录。
- Validation: `npm run build:css` exit `0`；本地/公网 CSS SHA-256 均为 `72a614c68a55c316160b79a8c5bc7532d833eb18d9a05b6ee056173bee1a87e6`；Labs `active/running`，health `200`。
- User direction/boundary: 用户明确自行测试，本次没有浏览器验收。一次启动的 browser navigation 超过 60 秒后已关闭，`blog-playwright-cli list` 确认无残留；未生成截图或测试产物。无生产、migration、服务重启、外部副作用或 Git 写操作。

## 2026-10-21（专注模式光晕收窄与返回焦点自动恢复）

- Report: 用户表示边缘光晕内部范围过大，且焦点回到页面后效果不消失，要求返回界面后自动恢复计时与正常效果。
- Root cause: blur/visibility hidden/pointerout 会进入 `auto-paused`，但 focus/visible 只处理待播消息，从未开启新计时段；DOM 状态持续为 warning。CSS 上下渐变高度 `62%`、侧边 `76%`，模糊最大 `34px`、内阴影 `144px`，覆盖范围过宽。
- Changed: 将离开类暂停标记为 return-resumable；focus/visible/pointerover 时恢复活动计时并清除边缘态。无操作、手动暂停、退出全屏仍需人工恢复。渐变收至上下 `22%`、侧边 `24%`，模糊最大 `18px`、内阴影 `56px`；模板资源版本 `article-focus-return-20261021g`。
- Validation: JS syntax、CSS/JS build 通过；实际 Labs bundle 读回 blur/focus、pointerout/pointerover 自动恢复，手动暂停不被解除、结束态清光效；CSS geometry 读回。CSS/JS hash 与公网一致、health `200`、服务保持 `active/running`。没有截图级验证。
- Boundary: 浏览器为匿名 Labs 页面临时 DOM 夹具，没有真实认证账户、操作系统焦点或全屏成功路径。无 migration、服务重启、生产操作、邮件、招聘采集、Provider/AGENT 或 Git 写操作。

## 2026-10-21（专注模式全屏边缘灼烧光晕补强）

- Report: 用户指出初版流光短暂且不明显，要求像游戏受伤画面一样由页面边缘向内扩散、柔和虚影、反复播放，避免细线绕屏。
- Changed: `static/src/discovery.css` 改成四向和四角宽幅渐变、24/72/144px 内阴影、14–34px blur 与 2.4 秒循环脉冲；移除醒目的边框线。更新 `templates/base.html` cache version 为 `article-focus-edge-burn-20261021e`；新建独立记录并更新 announcement、P12、handoff。
- Validation: 最终 `npm run build:css` exit `0`；Labs 首页 HTML 引用版本 `...20261021f`，本地/公网 CSS hash 均为 `521417e20bbd4b9daa5071e4e96a8a8f66edb84a33e61bc7f156649771985a3d`，health `/health/live=200`。前一版 `...21e` 在 Labs 页面成功读回暂停态 computed style；最终移除 1px 描边后没有重新打开浏览器。截图 1280×720 和 768×432 均被 5 秒字体等待限时中断，没有图像或像素级视觉证明。
- Boundary: 浏览器会话及空截图目录已清理；没有数据库、账户或文章数据副作用。无 migration、生产部署/重启、Provider/AGENT、招聘采集、真实邮件或 Git 写操作。全屏成功路径和增强后主观光效仍待用户实测。

## 2026-10-17（账户配额覆盖弹窗统一留言输入样式）

- Report: 用户管理中的“配额覆盖”弹窗沿用基础确认框，标题区、关闭按钮区和内容间距未完整呈现，与之前留言输入窗口的站内样式不一致。
- Changed: 在 `feedback.css` 增加共享 `confirm-dialog-panel` 外壳；留言输入弹窗和 `learning_question_banks.html` 的账户配额覆盖弹窗统一使用该外壳。移除留言弹窗中重复的外壳 CSS，保留留言字段/计数专属样式；更新 CSS cache version。
- Validation: `npm run build:css`、Django check、`git diff --check` 通过；Labs service `active/running`、`/health/live=200`、HTML 引用 `quota-dialog-panel-20261017`。真实 Labs 页面加载 CSS 后，临时配额弹窗结构 desktop `512×300`、顶部线 `4px`、标题区 `72px`、表单内边距 `20px`；390px 下宽 `358px`、内边距 `16px`、配额字段单列、无横向溢出。临时 DOM 已移除，浏览器已关闭。
- Boundary: 没有可授权管理员 session，未打开真实用户管理入口、未保存配额、未修改数据库、未重启服务、未触碰生产或执行 Git 写操作。

## 2026-10-16（全局通知与顶部栏悬浮层级修复）

- Report: 右上角全局通知出现时盖住顶部栏的悬浮菜单，菜单选项无法正常选择。
- Root cause: `global-feedback` 使用 `z-index: 80`，高于 `site-header` 的 `z-index: 30`；顶部栏内的通知浮窗虽为 `z-index: 50`，仍受 header stacking context 限制。
- Changed: 将 `static/src/feedback.css` 的全局通知层降为 `z-index: 25`，更新 `templates/base.html` 的 CSS cache version，并重新生成 `static/dist/styles.css`。
- Validation: `npm run build:css` 退出 `0`；生成 CSS 含 `.global-feedback{z-index:25`；Labs service `active/running`、公网 `/health/live=200`、HTML 引用 `feedback-header-layer-20261016`。真实匿名页面 computed 层级为 header `30` / feedback `25`；合成通知与顶部栏浮窗重叠点命中顶部栏浮窗。浏览器已关闭。
- Boundary: 未修改通知数据、账户、数据库、服务进程或生产；无登录态，通知中心真实数据和个人菜单内容未验收。

## 2026-10-16（管理员重置链接 CSRF 403 修复）

- Report: 重置页能打开，但提交新密码返回 Django 403 CSRF 验证失败。
- Root cause: Labs 日志为 `Origin checking failed - null does not match any trusted origins`；页面响应同时设置 `Referrer-Policy: no-referrer`。CSRF cookie 和隐藏 token 均存在，问题发生在 Origin 检查阶段。
- Changed: `apps/accounts/presentation/admin_password_reset.py` 的成功/失败响应和模板 meta 改为 `same-origin`；保留 Django CSRF 中间件、表单 token、fragment 令牌和服务端一次性校验。创建独立公告 `admin-password-reset-csrf-20261016.md`，并更新本轮 announcement。
- Validation: compileall、Django check、git diff check 通过；Labs header 为 `same-origin`。同一 cookie/token 对比：`Origin:null -> 403`，同站 Origin -> `422`，同站 Referer -> `422`；服务日志确认后两者进入应用层校验。浏览器修复后 GET 两次遇到 Nginx 504，按规则恢复一次后停止，无真实账户或邮件副作用。
- Boundary: 未运行 migration、未重启服务、未发送邮件、未触碰生产、未运行 Provider/AGENT/招聘采集、未执行 Git 写操作。下一步仅需稳定 Labs 后真实浏览器复测或隔离环境回归。

## 2026-10-16（授权应用管理员重置 migration）

- Authorization: 用户明确授权仅对 Labs `kaj_test_production_clone` 应用 `accounts.0011_admin_password_reset`；不包含生产 migration、邮件发送、服务重启或 Git 操作。
- Plan/application: 使用 `kaj-labs.service` 当前进程环境读取计划，唯一操作为 `Create model AdminPasswordReset`；`migrate accounts 0011_admin_password_reset --noinput --database default` 返回 `Applying ... OK`，退出 `0`。
- Readback: PostgreSQL 中表存在，字段为 `account_id, token_digest, created_at, expires_at, consumed_at`；确认账户主键/外键、token digest 唯一、`account_admin_pw_reset_positive_lifetime` 检查约束及 migration 记录。迁移后 plan 为空。
- Runtime: Labs Web PID `3372370` 与启动时间不变，仍为 `active/running`；公网 `/health/live=200`、`/health/ready=200`。没有重启服务。
- Boundary: 未发送邮件、未执行生产操作；没有可授权管理员 session，未验证按钮 POST 或邮件链接兑换。隔离测试环境仍缺少四项 `KAJ_TEST_*` 值。

## 2026-10-16（管理员重置邮件暂不可用故障定位）

- Report: 用户管理点击“发送重置邮件”显示“管理员密码重置功能暂不可用”。
- Root cause: 管理服务捕获 `AdminPasswordReset.objects.get_or_create()` 的数据库 `ProgrammingError` 并返回该安全提示；通过当前 `kaj-labs.service` 进程环境只读核实，Labs PostgreSQL migration 到 `accounts.0010` 为已应用、`accounts.0011_admin_password_reset` 未应用，`account_admin_password_reset` 表不存在。
- Validation: 服务保持 `active/running` 且工作目录正确。用服务进程环境运行 `showmigrations accounts` 与 Django 表 introspection 均退出 `0`；迁移状态为 `[ ] 0011`，`reset_table_exists=False`。本机默认 `config.settings.development` 下的全未应用结果不是 Labs 数据库证据。
- Boundary: 此次故障定位阶段未运行 migration、测试邮件或真实邮件，未触碰生产、未重启服务、未运行招聘采集/Provider/AGENT、未执行 Git 写操作。随后已按用户单独授权应用 migration，结果见本日志上节。

## 2026-10-16（管理员邮件密码重置）

- Objective: 在用户管理中增加确认发送邮件重置链接；用户在 30 分钟内设置并确认新密码，成功后撤销全部现有会话。
- Changed: `accounts` 增加一次性重置状态模型/服务与 `0011_admin_password_reset` migration；令牌只存 HMAC，摘要绑定 password hash/email，重发和凭据变化使旧链接失效；新增 fragment 兑换页、no-store/same-origin、停用 analytics、密码确认；管理用户行添加确认弹窗，写 operations 审计与脱敏 SecurityEvent。新增隔离用例和独立 Labs 迭代公告。
- Static validation: 目标 Ruff check、JS `node --check`、Django system check、migration autodetector、`git diff --check` 和最终 `npm run build:js` 均退出 `0`；`makemigrations --check --dry-run` 输出 `No changes detected`。app bundle 为 1.1 MB，本地/公网 SHA-256 均为 `acb443131eaab3efbcb8634e6207d87ac818ef40c3ee8b736177d119d721e443`。
- RED: 实现前 `test_admin_password_reset_link_route_is_registered` 因路由不存在失败，`1 failed in 3.03s`，符合预期。最终 PostgreSQL/Redis/Mailpit pytest 未运行：当前 shell 缺少 4 个 `KAJ_TEST_*` 值；没有连接共享 Labs 数据库/Mailpit。
- Browser/Labs: `kaj-labs.service` 工作目录正确且 `active/running`，公网 live/重置页 GET `200`。Playwright 最终读到密码重置页，伪造 fragment 已从 URL 清除、表单可见并聚焦；390px document/body 宽 375、无横向溢出，Tab 到 `confirm_password`，console errors/warnings `0`。两个初始导航等待超时后页面才读回；截图/主题交互超时，未重试；没有提交密码。
- Boundary at initial feature validation, before the later authorized Labs migration: `accounts.0011_admin_password_reset` 未应用；无真实邮件、管理员/用户账号操作、生产 migration/deploy/restart、招聘采集、Provider/AGENT 或 Git 写入。隔离回归和认证态验收仍待完成。

## 2026-10-16（Labs 管理员通知未到达修复）

- Report: 用户在 Labs 测试注册及作者权限申请后，管理员均未收到站内通知。
- Root cause: Celery Worker PID `3375824` 于 `2026-10-13 18:15:32 CST` 启动；事件路由和 account notification consumer 于 `2026-10-16` 更新。Web 热重载不更新 Worker 已导入模块，故新事件一直 pending、没有 consumer/通知记录。
- Recovery: 只执行 `systemctl restart kaj-labs-worker.service`，退出 `0`；新 Worker PID `399934` 于 `2026-10-16 13:35:04 CST` active/running。Beat 维持原调度；Web、Beat、PostgreSQL、Redis、Outbox timer 未重启。
- Readback: 注册和作者申请事件各 1 条转为 `published`，相应 consumer 各 1 条 `processed`；启用管理员各有 1 条 `NotificationReceipt`，且均未读。公网 `/health/live=200`。两个旧每周备份失败事件仍 pending、无 consumer 记录，保留给 B-027。
- Validation/boundary: 没有管理员浏览器 session，通知中心 UI 未浏览器验收；没有触发真实邮件，Worker/outbox 环境 `KAJ_LABS_SMTP_ENABLED=false`。未运行招聘采集、Provider/AGENT、生产操作或 Git 写操作。资源门禁黄色，单一重启操作完成，重启后 MemAvailable/SwapFree 均上升。

## 2026-10-16（授权后的 Labs schema migration 收尾）

- Authorization: 用户明确允许在 Labs `kaj_test_production_clone` 执行账号字段 migration；范围不包含生产、Outbox、真实邮件、账号创建或 Git 交付。
- Migration: 只读计划精确列出 `accounts.0010_account_author_permission_requested_at`；`migrate accounts 0010 --noinput` 返回 `Applying ... OK`。读回 `django_migrations`、`public.account.author_permission_requested_at`（nullable `timestamp with time zone`，无默认值）和迁移后空计划；现有 2 个账户值为 `NULL`。
- Runtime: `kaj-labs.service` 仍为 `active/running`，工作目录未漂移；公网 live/ready 为 `200`，匿名 `/author/articles/` 为登录跳转 `302`。
- Boundary: 没有可授权普通用户/管理员 session，未执行认证态浏览器流；Outbox service/timer 仍为 `failed/failed`、`inactive/dead`，未启动或改写；未执行生产 migration、部署、重启、Provider/AGENT、真实邮件或 Git 写操作。

## 2026-10-16（注册管理员通知与一次性作者权限申请）

- Objective: 注册成功后通知管理员；让所有已登录用户访问“我的文章”，普通用户可申请一次作者权限，已授权作者保留原工作台。
- Changed: accounts 增加一次性申请时间戳、行锁服务、注册/申请 Outbox 事件和 migration `0010`；notifications 增加管理员通知 consumer/模板、幂等投递和账户 UUID 目标；作者入口常显并按角色渲染申请页/原工作台；用户管理支持 UUID 精确搜索。同步更新 Q323、ITER-001、架构契约、页面状态和 Labs 独立公告。
- Validation: 初始 RED 复现首页缺少“我的文章”入口。最终入口逻辑复核后的隔离回归 `12 passed in 247.51s`；目标 Ruff check/format、Django check、CSS 构建通过。`makemigrations --check --dry-run` 无 model drift，但因基准测试库未创建产生连接 warning；pytest 在独立临时 PostgreSQL 测试库应用 migration。
- Initial Labs readback before migration: 服务 `active/running`；live 和首页 `200`，匿名作者入口按预期跳登录 `302`；本地/公网 CSS SHA-256 均为 `ca118a4f8f2a2b8b588d656ccd796f71194d20d88aeb426072498c79574ec509`。当时 Labs 共享库尚未应用 `accounts.0010`，且无认证用户/管理员浏览器状态；最终迁移结果见上节。
- Blockers/boundary: Outbox service `failed/failed`、timer `inactive/dead`，因此新通知尚不能在 Labs 实际消费；本轮未处理 Outbox、未跑认证态浏览器。无生产操作、服务重启、Provider/AGENT、真实邮件或 Git 写操作。

## 2026-10-15（留言板尺寸稳定与滚轮归属）

- Objective: 修复真实发布后留言板缩小，以及留言列表滚轮带动整个主页的问题。
- Root cause: 前一版只把宽高保存在会被 HTMX `outerHTML` 替换的面板上；用户实测确认真实发布仍会缩小。另一个主页级 wheel handler 仅排除了左侧导航，主动接管了留言板内滚轮。
- Changed: 将面板宽高/中心变量移至稳定的 `[data-home-page]`；主页吸附 wheel handler 忽略留言板；app bundle cache version 更新。前一版独立说明已补充“合成事件验证不代表真实发布”的更正。
- Validation: JS 语法检查和 `npm run build:js` 通过；新 bundle 本地/公网 SHA-256 一致，Labs health `200`。访客页面上的 `beforeRequest → outerHTML → afterSwap` 桌面尺寸前后均为 `634×468px`；1440×900 真实鼠标滚轮把留言列表滚到 `scrollTop=23px`，window `scrollY=0`；390×844 面板 `355×465.4px`，上下边界分别与页眉和 Hero 内容边界重合，控制台/page error 为 `0`。
- Boundary: 没有可授权 Labs 登录态，因此未执行真实留言 POST；无 migration、生产操作、服务重启、Provider/AGENT、真实邮件或 Git 写操作。

## 2026-10-14（富文本图片内容列宽度）

- Objective: 让图片 100% 与 25/50/75% 一样按当前内容列展示宽度计算，不使用原图自然尺寸或固定像素。
- Root cause: `tiptap_schema` 将默认 width=100 规范化为省略字段；原 CSS 仅对带 `data-width` 的图片设 `width:100%`，无属性时由浏览器采用固有尺寸。
- Changed: `static/src/editor-image.css` 对编辑器和公开文章图片统一设置基础宽度 100%，显式 25/50/75 继续覆盖；`templates/base.html` 更新 CSS 查询版本。新增独立说明并追加到 Labs 公告台账。
- Validation: `npm run build:css`、`git diff --check`、本地与 Labs CSS SHA-256 对照、Labs health 200。Playwright 文章页导航 60 秒超时、快照 30 秒超时；作者态四档点击未验收，浏览器已关闭。
- Boundary: 无 schema/数据/migration、生产、服务重启、招聘采集、Provider/AGENT、邮件或 Git 写操作。

## 2026-10-14（留言板展示与管理页调整）

- Objective: 留言板放大时保持正文字号，新增手动收起，后台留言页使用站内视觉和统一分页。
- Changed: 独立宽高限制留言板尺寸，由留言列表吸收额外空间；加入有焦点恢复的收起/展开控制；后台新增概览/状态徽标/审核卡片，分页复用全站组件并保留单页状态。静态版本号同步更新。
- Validation: 留言板 JS syntax、首页与管理模板解析、CSS/JS build、`git diff --check` 通过；Labs 服务 `active/running`、health `200`、CSS/JS 哈希一致。已有 1440px 读回：面板 `634×468px`、字号 `13.76px`、页眉和 Hero 边界内、z-index `20<30`。
- Limitation: 最新浏览器多次超时，窄屏、点击收起/展开及管理员态尚未验收；没有管理员会话可用。产品变更和验证限制写入独立公告文档。
- Boundary: 无 migration、生产操作、服务重启、Provider/AGENT、真实留言或 Git 写操作。

## 2026-10-14（留言板居中与输入浮窗布局）

- Objective: 将首页留言板放到 Hero 上下中心，修复留言输入浮窗标题栏、关闭按钮、输入区和底部按钮的布局错位。
- Changed: `home-guestbook` 使用页眉以下 Hero 可视区域中心定位；模板增加浮窗结构 class；CSS 补齐 header/form/actions、图标对齐和窄屏换行；更新静态资源版本。
- Validation: 成员态结构回归 `1 passed in 6.72s`；目标 Ruff/format、Django check、diff check 通过；`npm run build:css` 成功。Labs CSS 哈希 `fe65a2fd…` 本地/公网一致、health `200`。
- Browser: 桌面面板中心与 Hero 中心均为 `400.5px`；390px 下均为 `516.5px`，`scrollWidth=375`，控制台 0 error/0 warning。用当前 CSS 结构化读回标题栏 flex、桌面操作区横向、390px 弹窗宽 `358px` 和纵向操作区；匿名态没有输入浮窗，结构由成员态模板回归覆盖；浏览器已关闭。
- Boundary: 未执行生产 migration、部署、重启、招聘采集、Provider/AGENT、真实邮件或 Git 交付。

## 2026-10-13（首页匿名留言板）

- Objective: 在首页大图右侧提供匿名展示留言板，注册用户可发布纯文字留言，按 2/20 日配额限制，最新 10 条 keyset 加载，并在后台管理隐藏、删除和阅否毕标记。
- Changed: 扩展 `apps/comments` 的 `Comment` 字段/迁移、严格首页发布 service、公开查询、管理员 moderation/query/view/form；新增独立 `guestbook/board/comments/` 路由，保留旧 `/guestbook/` 的匿名、图片和缓冲兼容；加入 `home-guestbook.js`、首页模板/CSS、测试和公告文档。
- Performance: 公开列表单次 `LIMIT 11` 返回 10 条前瞻，不 count、不作者/媒体 N+1；日配额检查在锁定 guestbook thread 的事务内完成，查询索引随 migration 创建。
- Validation: 新留言板 `4 passed`；旧 CMT007 `5 passed`，合并回归 `8 passed`；Django check/migration drift、Ruff、compile、JS syntax、CSS/JS build、diff check 通过。Labs `comments.0006_guestbook_board` 经授权应用到 `kaj_test_production_clone`，字段/索引/迁移记录读回；公网首页/health `200`。
- Browser: Labs 首页真实读回初始展开、文章区滚动收起、右侧入口重开、390px 无横向溢出和深色主题；未登录只看到“登录后留言”，未执行登录或真实发布；浏览器会话已关闭。
- Boundary: 未执行生产 migration、部署、重启、招聘采集、Provider/AGENT、真实邮件或 Git 交付；Outbox 既有失败状态未改写。

## 2026-10-13（答题选项标签与刷题最终提交）

- Objective: 隐藏存储 option ID，按当前显示顺序提供大写 `A/B/C/D`；刷题模式最后一题揭晓后切换整卷提交。
- Changed: presentation 层增加 `display_options`；答题/解析模板统一使用展示标签；练习按钮复用独立整卷 form，JS 在全部 response 揭晓后切换 action/form/文案。
- Validation: 临时 HTTP RED/GREEN `1 passed`；答题模式/顺序 `11 passed`，最终入口 `1 passed`；Django check、Ruff、JS syntax、`npm run build:js`、diff check 通过；Labs `app.js` hash 与公网一致、live `200`。
- Boundary: 临时测试文件和数据库已清理；未运行浏览器登录流，因为 Labs 公开题库保持 `ADMIN_HIDDEN/security_review`；未改变题库可见性、生产或 Outbox 状态。

## 2026-10-13（完整重启 Labs 及资源）

- Action: 依次重启 P12 PostgreSQL/Redis/Mailpit 和 Labs Web/Worker/Beat，未触碰生产服务、数据卷或源码。
- Readback: Web 首次启动因 Django autoreloader 子进程处于 swap 等待而短暂无监听；停止 Worker/Beat 后 Web health 恢复 `200`，再按依赖顺序启动 Worker/Beat，最终三项均 `active/running`。
- Final: 公网及带代理头的本地 `/health/live` 均 `200`；PostgreSQL accepting、Redis `PONG`、Mailpit `200/healthy`。
- Boundary: Outbox service/timer 继续保持 `failed/timeout`、`inactive/dead`，两条历史事件未改写；详见 `docs/releases/2026-10-13-next-iteration/runtime-restart.md`。

## 2026-10-13（恢复 Labs 与下一轮迭代基线）

- Objective: 整理分支/worktree，确认 Labs 对齐当前正式运行代码，建立下一轮公告台账并重启 Labs 及资源服务。
- Baseline: 生产运行 revision 为 `d06af75`；远端 `main=9a0a6c8`；`d06af75..origin/main` 在 `apps/config/docker/static/templates` 无差异。Labs 已切换到 `codex/labs-next-20261013`，起点为 `9a0a6c8`。
- Runtime: P12 PostgreSQL 已接受连接，Redis `PONG`，Mailpit healthy；Web/Worker/Beat active/running；公网 `/health/live=200`。本地直连 health 需 `X-Kaj-Client-IP`，符合 Labs 受信代理配置。
- Outbox: timer/service 两次启动均在 30 秒内超时；日志显示 2 条历史 `task.final_failed.v1` transport failure，未 SQL 清理或改写，timer 已停止，待独立调查。
- Documentation: 新建 `docs/releases/2026-10-13-next-iteration/announcement.md`，后续每个产品切片追加 owner、验证、数据副作用和正式发布准备记录。
- Resource gate: 启动阶段处于黄色区间，MemAvailable 约 545-709 MiB、SwapFree 约 2.09-2.80 GiB；只串行启动必要服务，未启动浏览器或测试套件。

## 2026-10-12（README 当前状态整理）

- Objective: 更新项目 README，使其反映当前产品能力、正式运行版本、可核验数据和开发入口。
- Changes: 重写 `README.md`；同步更正架构、运维入口和实施清单中的“尚未部署”旧状态。记录生产业务快照（2026-10-09）、招聘来源状态（2026-10-11）和 HTTP 健康读回日期（2026-10-12），不把快照写成实时 SLO。
- Evidence: README 编辑基线 `main=91b88e7`，生产代码 revision `d06af75`；正式执行记录确认 `learning.0014/0015` 和 129 个启用来源终态；项目清单记录 13 阶段/102 任务、322 项需求、42 个路由及 P12 `405 passed`。
- Validation: `git diff --check` 通过；README 14 个唯一内部文档链接目标均存在；检查了生产、招聘、测试和 P0 状态数据来源。没有运行测试或启动 Labs 服务（本次仅更新文档，Labs 按要求保持关闭）。
- Git: 用户在后续当前回合明确要求提交推送；具体提交与集成状态以最终 Git 历史和远端读回为准。

## 2026-10-11（正式增量发布与状态修复）

- Objective: 提交推送本轮答题/导航/招聘修复，增量更新正式环境，按真实终态修复 35 条来源状态，并关闭 Labs 测试服务。
- Changes: 最终有效提交已 fast-forward 到远端 `main=d06af75`。答题迁移 `0014/0015` 已应用；Web/Worker/Beat 使用 `kaj-blog-web:d06af75a9c31`；独立 browser sandbox 更新到版本化 `d06af75` release，Feishu allowlist 与应用契约一致；Nginx marker 已移除、Caddy 保持 `2cbead0`。
- Validation: Quiz/记录回归 `15 passed`；adapter/Worker `35 passed`；增量镜像合同 `1 passed`；browser runner 合同 `19 passed`。Django check、migration drift、生产 plan、Ruff、JS 语法、`npm run build` 和 Caddy profile 验证通过。
- Production: `learning.0014/0015`、模式约束和 DB `EXAM` default 读回；Web/Worker/Beat healthy/running、restart 0；Worker socket 与宿主 inode一致。35 条最新来源检查为 30 healthy、1 degraded/truncated、4 stale（Qcraft timeout、2 Hotjob parser、1 Meituan parser）；无活动检查/每日全量任务/Provider/AGENT。
- Safety: PostgreSQL dump、媒体归档、Compose 快照均为 `0600` 并校验。来源状态只经现有 service 更新。生产 PostgreSQL backend 两次 exit-code 2 后自动 WAL recovery；容器无 restart/OOM，当前 healthy，根因需后续调查。
- Labs: Web 与 P12 PostgreSQL/Redis/Mailpit 已 stop 并读回 inactive/exited；数据卷保留。
- Next: 独立调查 PostgreSQL backend exit 根因；在 Labs 修复三条仍 `adapter_response_invalid` 来源和 Qcraft timeout，再定向复查。外部 P0 性能复测与生产 knowledge-review capability check 仍是独立运维待办。

## 2026-10-10（Labs 招聘来源适配器验证与修复）

- Objective: 在 Labs 先验证每日招聘来源失败并修复稳定的 parser 根因；验证通过后进入正式更新准备。
- Changes: Dahua 列表响应上限采用项目允许的 384 KiB；Beisen 对截断页执行最多 3 次有界降页重试；Getui 不再把分类路由号当作岗位 ID；Hotjob 接受合法空列表的 `total=0/pageSize=0`；Worker healthcheck 在配置浏览器 socket 时要求路径为 Unix socket。
- Live Labs probes: 使用安全客户端、robots 检查和 2 秒请求间隔；Dahua 144 条完整、Getui 5 条完整。Beisen 3 页 60 条、Hotjob 2 页 30 条、Meituan 5 页 25 条均按探针页数上限正常返回并标记 truncated；不输出或保存岗位正文，不写 Labs/生产数据库。
- Validation: 五个 adapter 文件 + 容器 contract 共 `35 passed in 1.17s`；目标 Ruff check、format、`git diff --check` 退出码 `0`；Labs service `active/running`、live `200`。`uv` 不在 shell PATH，使用现有 `.venv` 工具，没有安装依赖。
- Boundary: 没有运行定时采集、Provider/AGENT、生产 migration 或生产任务；Labs 未部署 Worker/浏览器沙箱，socket 运行态仅有 Compose contract 证据。正式更新尚未执行。
- Next: 正式发布需只包含岗位修复的可追溯候选；当前 Git commit/push 授权待用户明确确认。候选通过后重建 Worker 并验证 socket/健康状态，不触发生产招聘采集。

## 2026-10-10（生产招聘定时失败诊断）

- Objective: 判断每天 18:00 批量招聘检查的大量来源失败是否由整批超时中断造成。
- Evidence: 只读检查生产 `kaj-production-worker-1` 和 PostgreSQL；最新批次 129 个来源全部有终态（93 成功、35 失败、1 截断、0 未执行），TaskRun `succeeded`/attempt 1、耗时 1810 秒。运行时 Celery `task_time_limit=None`、`task_soft_time_limit=None`；来源单独 `max_duration_seconds=600`。
- Failure categories: 当天 26 个 `opportunities.adapter_browser_unavailable.v1`、8 个 `opportunities.adapter_response_invalid.v1`、1 个 `opportunities.request_timeout.v1`。近 30 天分别累计 509/20 runs、176/28 runs、23/16 runs；`opportunities.collection_timeout.v1` 仅 1/1 run。
- Separate incident: 2026-09-20 有一次 TaskRun attempt 3 以 `operations.task_lease_expired.v1` 终结，批次耗时 88,837 秒；这是租约/heartbeat 类异常，不是 Celery 全局硬时限，也不符合最近每日失败分布。
- Boundary: 所有生产数据库操作均在 `BEGIN READ ONLY`、5 秒 statement timeout 下执行；未运行招聘采集、Provider/AGENT、生产写入、migration、部署或重启，也未执行 Git 写操作。

## 2026-10-10（定位重复招聘来源失败根因）

- Deterministic browser failure: 最新 7 个定时批次内，21 个 `feishu-career-v1` 来源以及 Alibaba、ByteDance、Hikvision、Xiaomi 浏览器来源均连续 7/7 返回 `adapter_browser_unavailable`。生产 Worker 已配置 `/run/kaj-opportunity-browser/browser.sock`，但容器内挂载目录 inode 为 `26:10264108` 且 socket 不存在；宿主当前 socket 位于 inode `26:13168080`，权限 `0660`、UID 999/GID 10001。Worker 创建时间为 2026-09-20 10:41 UTC，浏览器 systemd 服务启动于 2026-09-25 22:59 UTC。
- Root cause: Worker 容器创建早于浏览器 socket 就绪；宿主 `/run/kaj-opportunity-browser` 的目录 inode 此后变化，而 Worker 的只读 bind mount 仍固定在旧 inode。浏览器服务 `active/running` 并不代表容器可见 socket。修复需在 socket 已就绪时重建 Worker 容器，让挂载重新绑定当前目录。
- Other stable failures: 最近 7 个批次中，Hotjob 3 个、Getui 2 个、Dahua/Meituan/Beisen 各 1 个来源连续返回 `adapter_response_invalid`。错误记录仅保留 `FILTERS`/错误码，不保存 HTTP 响应体；没有当前响应证据，不能安全放宽 parser。
- Boundary: 未重建生产 Worker；此前用户边界明确禁止生产重启/部署，当前尚未明确解除。未访问招聘来源或调用 Provider/AGENT；等待用户决定 worker recreate 和后续来源诊断授权。

## 2026-10-10（首页导航定位文章列表顶部）

- Objective: 从主页大图手动打开侧边导航后，点击任一文章分区链接，无论当前滚动位置都平滑定位到文章列表顶部。
- Changed: `static/src/home-navigation.js` 在侧边导航 HTMX 请求成功后调用现有 `snapTo(articles)`，等待列表替换完成再计算目标；`templates/base.html` 更新 JS/CSS 缓存版本。
- Validation: `npm run build:js`、`node --check static/src/home-navigation.js`、`git diff --check` 均退出码 `0`；Labs 公网 `app.js` SHA-256 与本地一致；Web `active/running`、health `200`。
- Browser: Labs 首页真实点击分区导航，390/768/1440 视口和桌面底部滚动位置下文章区顶端均与站点头部下沿一致；横向溢出 `0`，console errors/warnings `0`；浏览器已关闭。
- Resource gate: `yellow`; browser/build concurrency `1`; 任务期间 Swap 余量保持约 `2.2 GiB`，主机有响应，构建与单一浏览器会话均完成。

## 2026-10-10（修复 Labs 答题 500）

- Root cause: Labs 应用已读写 `QuizAttempt.mode`，测试库仍停在 `learning.0013_generation_batches` 且 `learning_quiz_attempt` 缺少 `mode` 字段；因此考试与刷题模式都在创建答题记录时返回 500。
- Fix: 仅在 Labs 测试库运行 `manage.py migrate learning --noinput`；`learning.0014_quizattempt_mode_and_more` 应用成功，没有修改题库 `ADMIN_HIDDEN/security_review` 状态。
- Validation: 字段、约束、migration 记录读回；Django check、learning migration drift check、health 均通过。未运行浏览器矩阵或全量回归，用户可重新开始答题验证。

## 2026-10-10（统一答题提交入口与解析栏）

- Changed: `quiz_attempt.html` 移除题目内刷题提交按钮，底部原主提交位置按模式绑定整卷或当前题；`_attempt_context` 只在已有揭晓题目时让解析栏进入布局。
- Interaction: `quiz.js` 在切题时更新底部按钮的 form/formaction，并按当前题的揭晓状态同步解析栏布局、`aria-hidden` 和 `inert`；已揭晓题目禁用提交。解析面板恢复为工作区外层第三栏，外层网格轨道随状态展开/收起；窄屏时放在答题区下方。`templates/base.html` 更新静态缓存版本。
- Validation: 本轮 `npm run build:css`、`git diff --check` 均退出 `0`；Labs CSS 公网 SHA-256 与本地构建产物一致，服务 `active/running`、live `200`。Playwright 打开正确答题入口后被重定向到登录（`302`），无登录态，未能查看答题页布局。

## 2026-10-10（Labs 资源显示诊断收口）

- User feedback: 启动后头像、知识文档、图片和题库没有正确出现；随后明确不需要继续测试。
- Evidence: Labs Web 保持 `active/running`，公网 live 为 `200`；11 个非删除媒体文件已按数据库 storage key 从旧 Labs 归档恢复，文件大小/SHA-256 与数据库一致，头像、Hero、封面、正文图片和附件 URL 均返回 `200`。
- Root cause split: 知识文档媒体匿名读取被访问控制返回 `404`；当前数据库文档记录为 `APPROVED=1`、`DELETED=1`。公开题库为空是因为 3 个题库卷均为 `ADMIN_HIDDEN/security_review`，不是模板或媒体路由缺陷。刷题模式依赖的 `learning.0014_quizattempt_mode_and_more` 也尚未应用。
- Boundary: 本轮停止浏览器和回归测试；没有应用 migration、修改题库可见性、生产写入、服务重启或 Git 交付。后续必须先得到对应 Labs 共享数据动作的明确授权。

## 2026-10-09（启动 Labs Web）

- User request: 启动 Labs 服务进行答题模式测试。
- Result: `kaj-labs.service` 已 `active/running`，WorkingDirectory 为当前 Labs worktree；公网 `/health/live=200`，未登录 `/knowledge/quiz/` 为 `302`。仅启动 Web，Worker/Beat 未启动。
- Runtime fix: systemd 首次启动因 unit 声明的 `var/media`、`var/backups` 目录缺失而 `226/NAMESPACE`；按现有 unit 只创建两个 `0750`、`kaj-labs:kaj-labs` runtime 目录，未改源码/数据库。
- Limitation: 服务日志提示 Labs 数据库有 1 个未应用 migration，即本轮 `learning.0014_quizattempt_mode_and_more`；本轮没有执行 migration。登录后的刷题模式公网流需要下一步单独授权 Labs migration。

## 2026-10-09（复核 Labs 依赖资源）

- Readback: `kaj-p12-postgres`、`kaj-p12-redis` 已 running，`kaj-p12-mailpit` running/healthy；`kaj_test_production_clone` 可用、Redis PONG、Mailpit API 200，相关端口均监听。
- Action: 未重复启动或重启容器；Labs Web 继续保持 active/running。剩余阻塞是 `learning.0014` 尚未授权/执行。

## 2026-10-09（答题考试/刷题模式）

- Objective: 保留考试模式既有整套揭晓行为，新增每题提交即揭晓的刷题模式。
- Changed: `QuizAttempt.mode` + migration `learning.0014`（默认 `EXAM`）；`submit_quiz_response` 在事务内判客观题、更新错题本并锁定已揭晓 response；query 按单题提交状态隐藏/揭晓答案；配置页、回答页、短答自评、模式结果标签、静态缓存版本及 planning/architecture/release 文档同步。
- RED/GREEN: 初始聚焦 RED 明确落在缺少模式选项；真实浏览器又发现重入 `requestSubmit` 被忽略，改为下一事件循环任务再提交后成功。
- Validation: 隔离 PostgreSQL/Redis/Mailpit 上模式、答题顺序和记录回归 `14 passed in 91.79s`；Django check、migration drift、目标 Ruff/format、JS 语法、完整静态构建和 `git diff --check` 通过。
- Browser/data: 本地隔离站点登录并真实选择 PRACTICE、逐题提交、刷新和最终提交；DB 读回 `PRACTICE/SUBMITTED`、2/2 responses、objective `1/2`、错题计数只增一次、题库完成数 `+1`。390/768/1440 × 三主题无横向溢出，Enter 导航有效，控制台 0 error/0 warning。
- Runtime/boundary: 临时 `kaj_test_quizmode_ui_20261009` 数据库和 `/tmp` 媒体目录已删除；Labs 源码目标与当前 worktree 相同，但服务仍 `inactive/dead`、公网 live `502`，未启动/重启；未执行生产 migration/部署/Provider/AGENT/Git 写操作。
- Next: 等 Labs 服务由运维恢复后再做公网 Labs 只读页面读回；生产发布需另行授权。

## 2026-10-09（恢复 Labs 正式基线）

- Objective: 盘点分支/worktree，并让新 Labs 迭代从当前正式源码基线开始；建立独立公告台账。
- Evidence: 正式 Web/Worker/Beat image revision 均为 `42adeb4ceb74ec5823df70a66144b21b80b0f275`；最新 `origin/main=631253f` 在其后只有 handoff/发布文档差异，`apps/ config/ templates/ static/` 完全一致。
- Worktree: 旧 Labs detached `a06a94f`（包含未提交应用代码、handoff、测试及公告）完整移动到 `labs-test-environment-archive-20261009`；原服务工作目录建立干净分支 `codex/labs-next-20261009`，跟踪 `origin/main`。旧分支保留，未提交/推送。
- Docs: 新增 `docs/releases/2026-10-09-next-iteration/announcement.md`，作为逐切片公告台账；补齐新分支 handoff 状态。
- Planning: 复核实施清单与 readiness；计划文档称原定 P0-P12 的 102 项已完成，没有新的产品 Todo。外部 P0 复测和生产知识审核能力核对仍是独立运维待办，不擅自选为新产品功能。
- Runtime: Labs 服务仍 `inactive/dead`，`/health/live=502`；只完成源码基线确认，没有启动或重启服务，也没有执行产品测试或生产操作。
- Next: 等待明确下一产品切片；服务运行时验收须待 Labs 获明确授权恢复后进行。

## 2026-09-17

- Objective: 按 Labs-first 规则提交并推送 handoff。
- Changed files: `AGENT_HANDOFF.md`、`AGENT_SESSION_PROMPTS.md`、`.agent-handoff/*.md`、`AGENTS.md` 的 handoff protocol。
- Result: handoff 初始内容和状态收口均由 Labs 任务分支推送并 fast-forward 到远端 `main`；临时分支已删除；Labs 保留在集成后的 detached 快照。
- Remaining risks: 主工作区仍为 `e5adc20`、落后远端 23 个提交且保留原有脏改动，未执行同步或覆盖。

## 2026-09-20

- Objective: 按 P0 `03-backend-performance.md` 定位 Kajspace 公开岗位性能，先形成 SQL/模板/响应传输证据，再做最小优化和聚焦回归。
- Evidence: 正式公网三个岗位 GET 均 `200`；未压缩响应 `394–420 KB`，Nginx gzip 后 `60–62 KB`。隔离 PostgreSQL 探针显示筛选选项 owner SQL `5→3`，完整岗位请求 `17→14`；岗位查询本身保持 count/page/prefetch 三条，无模板 N+1。
- Changed files: `apps/opportunities/queries/public.py`、`apps/opportunities/views.py`；临时回归文件仅用于本轮验证，已清理。
- Result: 合并筛选选项查询、复用来源计数、HTMX 跳过未使用摘要；聚焦测试 `6 passed`，既有岗位回归 `9 passed`，合并 `15 passed`；Ruff/format/Django check/diff check 通过。
- Labs: 三个已完成文件已定向同步并 `cmp` 验证；Labs 服务仍 `inactive/dead`，`health/live=502`，未启动/重启；本任务未执行 Git add/commit/push、生产 migration、部署或 P0 外部复测。

## 2026-09-20（正式增量发布）

- Objective: 将岗位性能优化提交 `42adeb4` 增量更新到正式环境。
- Preflight: 构建 `kaj-blog-web:42adeb4ceb74` 成功；候选 `check --deploy`、migration drift 和正式 `migrate --plan` 通过且无待执行 migration。
- Safety: 新鲜 PostgreSQL dump、媒体归档和 Compose 快照均为 `0600` 并完成 SHA-256/TOC/成员校验；未执行 migration、招聘采集、Provider/AGENT、恢复或 Outbox 补偿。
- Result: Web/Worker/Beat 按顺序切换，均为候选镜像、healthy/running、RestartCount 0；健康、岗位默认/搜索/筛选/分页及 JS/CSS 均 HTTP 200。
- Remaining: Labs 仍 inactive/dead；外部 P0 并发复测仍待执行；发布记录已由 `6f59ed8` 推送并 fast-forward 到远端 `main`。

## 2026-09-16

- Objective: 为 `/home/code/personal-blog` 建立完整的 repository-local multi-document handoff。
- Changed files:
  - `AGENT_HANDOFF.md`: 保留索引和恢复顺序。
  - `.agent-handoff/*.md`: 写入当前快照、工作区地图、决策、验证、backlog、风险和归档入口。
  - `AGENT_SESSION_PROMPTS.md`: 写入新窗口、继续、收口和质量复核提示词。
  - `AGENTS.md`: 追加标记的多文档 handoff protocol，保留既有项目规则。
- Result: handoff 已按当前主工作区、Labs、正式快照、Git 和服务状态填充；未创建 `.claude/CLAUDE.md`，因为项目当前没有 Claude Code 项目规则文件。
- Remaining risks: 主工作区脏且落后远端；handoff 文件当时尚未提交，后续已在 2026-09-17 完成交付。

## 2026-09-15

- Objective: 将性能测试任务文档从 Labs 提交并推送，保留当前正式快照，准备外部机器远程 P0。
- Changed files: `docs/operations/README.md`、`docs/operations/performance-testing/`（P0/P1/P2 任务及执行日志）。
- Result: Labs 任务提交 `0b700d4`，fast-forward 集成远端 `main`；临时分支已删除；未部署、未重启生产。
- Remaining risks: 外部 P0 尚未执行；执行日志仍为“未执行”。

## 2026-09-15（工作区审计）

- Objective: 核对 Labs-first 提交路径和主工作区漂移。
- Result: `origin/main`/Labs 为 `0b700d4`；主工作区 `e5adc20` 落后 21 个提交，存在 69 个 tracked 修改和 12 个 untracked 路径；未执行 reset、pull、merge 或覆盖。
- Remaining risks: 主工作区改动需要逐文件分类，不能整体迁移或丢弃。

## 2026-09-15（生产审核诊断）

- Objective: 诊断知识文档审核 `agents.profile_capability_unverified.v1`。
- Result: 生产只读读回显示知识审核 profile 需要 `knowledge-review.v1`；当前 Endpoint row version 为 8，但匹配的严格检查只有其他 schema，旧审核检查对应旧 row version。失败发生在 AGENT 外呼之前。
- Next action: 管理员对当前 Endpoint 选择知识文档审核 profile 执行严格 capability check，成功后重试审核。

## 2026-10-17（本轮正式增量更新收口）

- 用户授权本轮 Labs 全量提交推送、正式增量更新、生产 migration/备份/状态修正和关闭 Labs 测试服务。
- 代码与文档提交 `2c78cddf92acf6adf7f33f3c57affa32cada522e` 已推送任务分支并 fast-forward 到远端 `main`；测试文件按规则保留在 Labs worktree 未提交。
- 候选 `kaj-blog-web:2c78cddf92ac` 基于 `d06af75a9c31` 构建，增量 Dockerfile 已纳入 `config/`；候选 check/deploy、drift、migration plan、collectstatic 和 Compose config 通过。
- 正式维护窗口创建 DB/media/Compose 备份并校验；应用四项 migration，切换 Web/Worker/Beat，公网 live/ready/home 和岗位入口读回通过。
- 生产状态修正由恢复 owner 完成：终态父运行下孤儿来源从 `RUNNING` 收敛为 `FAILED/opportunities.check_run_orphaned.v1`，父汇总失败数 `30→31`；空 dispatcher 复核无派发。
- 收尾停止 Labs Web/Worker/Beat、Outbox service/timer 和临时测试容器，保留失败诊断与数据卷；生产机会浏览器服务未停止。
- 当前交付记录和 handoff 已提交；下一步仅清理已集成远端任务分支并保留外部 P0、认证态验收、知识审核、题库公开状态和 Outbox 独立调查待办。

## 2026-10-20（返回 Labs 并确认正式基线）

- Objective: 整理分支和 worktree，确认 Labs 从当前正式运行代码基线开始下一轮迭代，并建立新的公告台账。
- Baseline: 正式 Web/Worker/Beat 均为 `kaj-blog-web:2c78cddf92ac`，OCI revision 为 `2c78cddf92acf6adf7f33f3c57affa32cada522e`；Labs `codex/labs-next-20261020` 与 `origin/main=d0407d6` 对齐，生产 revision 是主线祖先，运行时代码目录无差异。
- Runtime: Labs Web、Worker、Beat 已恢复 `active/running`；公网 live/ready `200`；P12 PostgreSQL、Redis、Mailpit 分别通过 accepting/PONG/healthy+API 读回。Beat 仅清除自身历史 failed lock 后启动；Outbox 保持 failed/inactive，不做重置或数据改写。
- Worktree: 主工作区、留言板历史 worktree、旧 Labs 归档和正式快照均保留；Labs 的一个修改测试文件和四个新增测试文件未暂存。
- Documentation: 新建 `docs/releases/2026-10-20-next-iteration/announcement.md`，后续每个切片另建独立记录并追加本台账。
- Boundary: 未执行产品测试/build、生产 migration/deploy/restart、招聘采集、Provider/AGENT、真实邮件或 Git 提交/推送；下一项产品目标待用户指定。

## 2026-10-21（ITER-003 登录用户文章专注模式）

- Objective: 在现有登录用户公开文章阅读工具栏内实现专注模式，并按本轮规则写独立 Labs 记录。
- Changed/confirmed: `discovery` 拥有文章入口和页面状态，`navigation` 拥有 SiteConfiguration 规则，`administration` 提供管理配置；新增迁移 `navigation.0009_focus_mode_settings` 已在 Labs `kaj_test_production_clone` 应用。本次只读读回确认 migration 记录、列、3/3 默认值及 1–15 分钟/1–10 次约束。
- Validation: `.venv/bin/pytest --reuse-db -q apps/navigation/tests/test_nav005_focus_mode_settings.py apps/discovery/tests/test_article_focus_toolbar.py` 使用 `KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:57432/kaj_test_focus_mode_e2e`，`11 passed in 199.74s`；目标 Ruff check/format 13 文件、`node --check static/src/article-focus.js`、`npm run build:css`、`npm run build:js` 均退出 `0`。本地隔离 runserver 的 Django system check 为 `0 issues`。
- Browser: 固定 CLI 通过隔离管理员状态打开阅读设置页和公开文章，页面 GET 均 `200`。实际 3 分钟无操作后读回自动暂停和 `03:00`；三次手动暂停状态序列经 DOM 事件验证。390/768/1440 视口 document 均无横向溢出。CLI 的导航/定位/填入存在等待超时；`requestFullscreen` 在 headless 会话因缺用户手势被拒绝，真实浏览器全屏成功路径与管理员页浏览器保存未验证；配置保存由 Django 客户端回归覆盖。
- Labs: service 仍是正确 worktree 的 `active/running`，live/ready 均 `200`；CSS/JS 本地与公网 SHA-256 分别匹配 `615b20fc91c5405d08fe8c89b85fbab90036aeae87f8bf97f69e092d458df2ca`、`8e17c4e03a08df89b60ae0e7eabfafb5b25fe9dc1fba0d930900d1a37c081634`。
- Cleanup/boundary: 关闭 `focus-mode` 浏览器和本地 8766 服务；核对 owner/连接数后删除仅用于本切片的 `test_kaj_test_focus_mode_e2e`、`kaj_test_focus_mode_e2e` 与 `/tmp` 状态/seed 文件，保留 `kaj_test_production_clone`。未执行生产 migration/deploy/restart、真实邮件、招聘采集、Provider/AGENT 或 Git 写入。
- Documentation: 新建 `docs/releases/2026-10-20-next-iteration/focus-mode-20261021.md` 并更新本轮 announcement、P12 后任务状态和 handoff。

## 2026-10-21（专注模式左下计时区与边缘状态流光）

- Request: 工具栏只留专注开始/结束入口；计时、圆形暂停/继续图标和纯文本次数位于左下计时区并排；手动暂停黄边流光、自动警告红边流光、正常状态无流光。
- Changed: 将计时区 DOM 移出工具栏；小屏展开工具栏靠右避开左下区域；保留 SVG 图标属性显隐和按 `manual-paused`/`auto-paused` 切换边缘效果，active/off 清除效果。
- Validation: 真实 Labs bundle/CSS 和临时 DOM fixture 读回状态、键盘焦点样式、三主题颜色及 390/768/1440 几何；三种尺寸均无横溢/控件重叠。Django template compile/system check、JS syntax、CSS/JS build、`git diff --check` 通过。Labs service `active/running`、live `200`；本地/公网 CSS/JS hash 一致。
- Limitation: 两次全视口截图均被 CLI 5 秒门限终止，未完成像素级截图检查；未使用认证态或真实鼠标操作，全屏成功路径仍待用户正常登录浏览器确认。
- Boundary: 没有生产操作、服务重启、数据库写入或 Git 写入。
- Documentation: 更新 `focus-mode-ui-20261021.md`、本轮 announcement 和 P12 任务说明，准确记录左下计时区布局及截图限制。

## 2026-10-22（正式增量交付准备与生产状态审计）

- Request: 提交推送全部 Labs 改动，构建本轮正式候选，修复可证实的错误状态数据，执行 production increment，并在成功后关闭 Labs 测试服务。
- Git: 从 fresh `origin/main=d0407d6` 创建 `codex/production-increment-20261022`；尚未提交或推送。
- Validation: `npm run build` 通过；frontend `5 passed`；隔离 PostgreSQL/Redis/Mailpit 回归 `29 passed in 200.71s`；Ruff check/format、focus/reader JS syntax、`git diff --check` 通过。两个历史测试断言更新为现有 `same-origin` 和共享弹窗类契约。
- Data: 生产岗位状态只读审计终态父运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、running opportunity TaskRun `0`；没有调用 recovery service、adapter 或招聘采集。
- Build preflight: 发现 `.dockerignore` 排除 `static/dist/` 与 incremental Dockerfile 冲突，已精准放行该目录；尚待实际候选 build 证明。
- Release docs: 新建 `docs/releases/2026-10-22-production-increment/`，用于独立正式公告、计划、checklist 和部署读回，不混用 Labs 历史台账。
- Boundary: 除 remote main 读回和独立任务分支创建外，未修改生产文件/数据库/容器/服务；所有 production backup/migration/switch 和 Labs shutdown 尚待执行。

## 2026-10-22（手机版阅读模式分页设置浮层）

- Request: 左右和上下分页中，设置显示时浮在正文上层，不压缩正文；上下模式单击切换设置，滑动仍单次翻页。
- Root cause/fix: 控件原为 surface 的 flex 子项。新增控件 wrapper 并仅在两种分页模式绝对定位；JS 扩展上下模式点击显隐，任一分页手势后隐藏设置。连续滚动仍沿用纵向布局。
- Files: `apps/discovery/templates/discovery/article_detail.html`、`static/src/discovery.css`、`static/src/article-reader-mode.js`、阅读架构/ITER-004、`templates/base.html` 及新 Labs slice record/announcement。
- Validation: JS syntax、CSS/JS build、`git diff --check` 通过；Labs article `200` 读回控件层与版本 `article-reader-overlay-20261022c`，health `200`，service 正确 workdir 且 `active/running`，CSS/JS 公网哈希与本地产物匹配。用户要求自行验收，因此未启动浏览器。
- Resource gate: yellow；CSS 与 app bundle 分别串行构建，available 约 `595–624 MiB`、swap free `1.75–1.85 GiB`、持续但变化的 `si/so`，每个阶段均有进展且系统响应正常。
- Boundary: 无服务重启、生产写入、migration、Git 写入或外部副作用；待用户手机观感确认。

## Work Log Guidelines

- Keep only recent, still-operationally-useful work here.
- Move stale or long history to `archive.md` as a compressed summary.
- Prefer file paths and concrete outcomes over prose summaries.
