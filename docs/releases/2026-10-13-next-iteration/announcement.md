# Kajspace 下一轮 Labs 迭代公告台账（2026-10-13）

状态：下一轮迭代准备中。本台账从当前正式运行版本建立，只记录本轮后续新增的产品、修复、验证和发布准备内容；已有发布内容以对应正式公告为准。

## 基线确认

- 正式生产运行代码 revision：`d06af75a9c315a9966d612a34a9ba27211629583`；Web、Worker、Beat 使用 `kaj-blog-web:d06af75a9c31`，Caddy 保持 `2cbead0`。
- 当前远端默认分支：`origin/main=9a0a6c886b87c63c96f90b3f3963f01508c9319f`。
- `d06af75..origin/main` 在 `apps/`、`config/`、`docker/`、`static/`、`templates/` 下无差异；主线新增内容属于 README、发布记录和 handoff 文档。因此 Labs 运行时代码与当前正式代码基线一致。
- Labs worktree：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`；本轮分支：`codex/labs-next-20261013`；起点为 `origin/main=9a0a6c8`。
- 2026-10-13 资源读回：P12 PostgreSQL 接受连接，Redis 返回 `PONG`，Mailpit 为 `healthy`；Labs Web、Worker、Beat 为 `active/running`。
- Labs Outbox timer/service 启动尝试两次均超时；timer 已停止，2 条历史 `task.final_failed.v1` 事件保持原状态，未执行 SQL 清理或状态伪造。详见本台账的运行记录和 handoff 风险。
- Labs 公网 `/health/live` 与正确代理头下的本地 `/health/live` 均返回 `200`；直接访问 `127.0.0.1:18082` 不带 `X-Kaj-Client-IP` 会触发受信代理校验错误，不作为用户入口。
- 本次完整重启和中间 502/恢复过程记录在 [`runtime-restart.md`](./runtime-restart.md)；最终 Web、Worker、Beat 和 P12 基础资源均已读回正常，Outbox 仍单独阻塞。

## 2026-10-13 运行资源重启

- 用户可观察结果：Labs 公网 health 恢复 `200`，Web、Worker、Beat 及 PostgreSQL、Redis、Mailpit 均完成重启并正常运行。
- 期间证据：Web 首次启动受主机 swap 读取影响，systemd 进程存活但端口未监听；停止 Worker/Beat 后 Web 完成监听，再按依赖顺序恢复 Worker/Beat。
- 未改变源码、数据库 schema、题库可见性或 Outbox 事实状态；Outbox service/timer 保持停止，待独立根因调查。
- 详细命令、退出状态和限制见 [`runtime-restart.md`](./runtime-restart.md)。

## 2026-10-13 答题界面与刷题最终提交

- 答题选项按当前渲染顺序显示大写 `A/B/C/D` 标签，保留存储 ID 作为提交和判题值；解析面板同步使用同一标签。
- 刷题模式全部题目揭晓后，底部按钮切换为“提交整张试卷”，复用既有整卷提交入口。
- 实现、回归、Labs 静态读回和浏览器验收边界见 [`quiz-ui-20261013.md`](./quiz-ui-20261013.md)。

## 2026-10-13 首页匿名留言板

- 首页大图右侧新增匿名展示留言板：最新留言优先，每批 10 条，底部自动以 keyset cursor 加载下一批；滚动到文章区后收起为右侧入口，管理员标记以“阅/否/毕”显示。
- 注册账户通过独立首页入口发布纯文字留言，每日账户上限 2 条、留言板上限 20 条；后台“内容与互动”新增留言板管理，可隐藏、删除和标记。
- 兼容边界、查询性能、字段迁移、回归证据和 Labs 真实页面读回见 [`guestbook-board-20261013.md`](./guestbook-board-20261013.md)。

## 2026-10-14 留言板居中与输入浮窗布局修正

- 留言板调整到首页大图 Hero 的上下中心位置；输入浮窗补齐标题栏、关闭按钮、表单和操作区布局，修复图标及按钮错位，并适配窄屏换行。
- 实现和验证记录见 [`guestbook-board-layout-20261014.md`](./guestbook-board-layout-20261014.md)。

## 2026-10-14 留言板尺寸、手动收起与管理页布局

- 留言板扩大显示区域时维持正文既有字号，扩大的空间用于留言列表；限制面板始终处于顶部栏和 Hero 黑幕之间。
- 增加手动收起按钮，保留滚动自动收起与侧边入口恢复；管理员页面增加状态概览与审核卡片，并切换为站点统一分页（单页仍显示）。
- 变更与验证记录见 [`guestbook-board-presentation-20261014.md`](./guestbook-board-presentation-20261014.md)。

## 2026-10-14 富文本图片内容列宽度

- 统一图片四档尺寸语义：100% 按当前编辑/阅读内容列铺满，25/50/75% 按同一列宽比例显示；不固定像素，也不改变原图。
- 默认宽度省略 `data-width` 时也应用 100% 列宽，继续保留显式的 25/50/75 覆盖。
- 根因、实现和验证记录见 [`editor-image-content-width-20261014.md`](./editor-image-content-width-20261014.md)。

## 2026-10-15 留言提交后保持大面板尺寸

- 修复留言提交后的 HTMX 整体替换导致留言板回落到基础尺寸的问题；提交前后的宽高状态会在同一视口中保留，并继续按当前安全边界校准。
- 后续用户复测真实发布仍会缩小，先前事件模拟未覆盖真实发布表现；该结论已由后续稳定状态修复替代，见 [`guestbook-board-post-submit-20261015.md`](./guestbook-board-post-submit-20261015.md) 和下一节。

## 2026-10-15 留言板尺寸稳定与滚轮归属

- 将留言板尺寸变量改由 HTMX 不替换的首页容器持有，整块 shell 替换后继续继承原尺寸；主页滚轮吸附监听跳过留言板，让留言列表接收滚轮并在边界内停止，不再带动页面。
- Labs 浏览器模拟真实替换前后均为 `634×468px`；留言区从顶部滚至 `scrollTop=23px` 时 `window.scrollY=0`。390px 下留言板为 `355×465.4px`，上/下边界分别与顶部栏和 Hero 内容边界重合；无控制台错误。
- 源码、浏览器路径、静态资源哈希和真实认证 POST 限制见 [`guestbook-board-scroll-stable-layout-20261015.md`](./guestbook-board-scroll-stable-layout-20261015.md)。

## 2026-10-15 首页留言板每日配额可配置

- 管理员可在“留言板管理”独立设置首页留言板每位用户每日留言上限和全站每日接收上限；默认保持 `2/20`，系统范围分别为 `1..100` 和 `1..1000`。旧 `/guestbook/` 的访客留言规则保持不变。
- 配额写入由 `apps/comments` 持有，服务端事务继续锁定留言板线程后校验/创建，配置更新带版本冲突保护和审计；首页提示和发布校验读取同一持久化值。
- 迁移为 `comments.0007_guestbook_daily_quotas`。用户授权后已应用到 Labs 测试库 `kaj_test_production_clone`，schema 读回完整；配额运行时代码、模板和 CSS 已同步到服务工作树。生产环境未迁移。
- 实现、聚焦回归、Labs 迁移边界和待完成项见 [`guestbook-daily-quotas-20261015.md`](./guestbook-daily-quotas-20261015.md)。

## 2026-10-16 新用户注册通知与一次性作者权限申请

- 注册成功后向管理员发送站内通知；普通登录用户顶部“我的文章”入口常显，未获作者权限时可提交一次申请，之后显示已通知状态。作者继续看到原工作台，其它作者命令仍做服务端权限校验。
- 申请状态写入账户时间戳，并与 Outbox 事件同事务提交；通知只含稳定账户 ID，目标筛选对应管理员用户记录并复用现有确认授予作者流程。
- 聚焦隔离回归 `12 passed in 247.51s`，Ruff、Django check、CSS 构建和公网哈希读回通过。用户明确授权后，Labs `kaj_test_production_clone` 已应用 `accounts.0010_account_author_permission_requested_at`；字段、迁移记录、迁移后空计划、live/ready 和匿名作者入口读回通过，登录态申请页面仍未做浏览器验收。
- 用户随后测试发现管理员没有收到注册/作者申请通知。根因是 Labs Celery Worker 在通知路由代码更新前启动、未热加载新代码；只重启 Worker 后，两类 Outbox 事件均发布成功，并各有一条发给启用管理员的未读通知回执。运行态证据见 [`author-notification-worker-runtime-20261016.md`](./author-notification-worker-runtime-20261016.md)。
- 功能根因、owners、migration 和隔离回归见 [`author-permission-request-20261016.md`](./author-permission-request-20261016.md)；登录态页面仍待可授权浏览器 session 验收。

## 2026-10-16 管理员邮件密码重置

- 管理员可在用户管理中确认发送密码重置邮件。用户通过邮件链接设置并确认新密码，链接 30 分钟后失效且只能使用一次；成功后撤销该账户的全部现有会话。
- 令牌只在邮件 URL fragment 中传递，页面读取后立即清除地址栏片段；数据库只存绑定当前密码哈希与邮箱的 HMAC 摘要。重发会使旧链接失效，用户修改密码或邮箱也会使已有链接失效。
- 新增 migration `accounts.0011_admin_password_reset`，只建账户一对一重置状态表。用户明确授权后已在 Labs `kaj_test_production_clone` 应用并完成表、约束、迁移记录和空计划读回；生产仍未迁移。真实邮件、生产操作、服务重启和 Git 交付均未执行。
- Ruff、JavaScript 语法、Django system check、migration autodetector、`git diff --check` 和 `npm run build:js` 均通过。Labs `/health/live` 与公开重置页 GET 返回 `200`；本地/公网 app bundle SHA-256 一致。浏览器确认 fragment 被清除、表单显示、390px 无横向溢出和 Tab 焦点顺序正常；无管理员/用户 session，未提交密码。
- 专用 PostgreSQL/Redis/Mailpit 回归未运行，因为当前没有四项隔离测试环境变量；不连接共享 Labs 数据库或清理共享 Mailpit。截图/主题按钮交互超时，768px 与 1440px 视觉验收待补。
- 实现边界、迁移结果和验证限制见 [`admin-password-reset-20261016.md`](./admin-password-reset-20261016.md)。

## 2026-10-16 管理员重置链接 CSRF 提交修复

- 用户提交新密码时出现 Django 403 CSRF 验证失败；服务日志确认请求 `Origin` 为 `null`，页面原先的 `Referrer-Policy: no-referrer` 触发了该浏览器行为。CSRF token cookie 和隐藏字段本身均存在。
- 重置页改用 `Referrer-Policy: same-origin` 及对应 meta；保留 Django CSRF 中间件和表单 token。URL fragment 不属于 Referer 内容，重置令牌不会随该头发送到外部站点。
- Labs 响应头读回 `Referrer-Policy: same-origin`；同一 cookie/token 下 `Origin: null` 仍为 `403`，同站 Origin 或同站 Referer 均进入应用层无效令牌校验并返回 `422`，证明 CSRF 校验已通过。浏览器复测期间 Labs 发生 504，已停止重复重试，真实有效令牌和邮件兑换仍未验证。
- 详细根因、改动和边界见 [`admin-password-reset-csrf-20261016.md`](./admin-password-reset-csrf-20261016.md)。

## 2026-10-16 右上角全局通知层级修复

- 修复右上角全局操作通知盖住顶部栏悬浮菜单的问题；顶部栏的搜索建议、通知浮窗和个人菜单现在整体保持在全局通知之上，菜单选项可正常选择。
- 根因是 `.global-feedback` 的 `z-index: 80` 高于 `.site-header: 30`；现调整为 `25`，不改变通知的位置、内容和自动消失逻辑。
- `npm run build:css` 通过；Labs `active/running`、`/health/live=200`、公网 HTML 已引用 `feedback-header-layer-20261016`。浏览器真实页面 computed 层级为 header `30` / feedback `25`，合成重叠点命中顶部栏浮窗；未使用认证态通知数据。
- 详细实现和验证边界见 [`feedback-header-layer-20261016.md`](./feedback-header-layer-20261016.md)。

## 2026-10-17 用户配额覆盖弹窗样式统一

- 修复用户管理中“配额覆盖”弹窗样式未完成的问题，使其与首页留言输入窗口使用同一款弹窗外壳：顶端强调线、标题区、关闭按钮、遮罩、内容间距、操作区和窄屏规则统一。
- 新增共享 `confirm-dialog-panel` 样式 owner；留言输入窗口和账户配额覆盖窗口共同复用，账户的五项配额字段在 390px 下自动单列。
- `npm run build:css`、Django check、`git diff --check` 通过；Labs health `200`，公网 HTML 已引用 `quota-dialog-panel-20261017`。浏览器临时账户弹窗读回 desktop `512px`、390px `358px`、顶部线 `4px`，无横向溢出；没有可授权管理员 session，未执行真实配额保存。
- 详细实现和验证边界见 [`quota-dialog-panel-20261017.md`](./quota-dialog-panel-20261017.md)。

## 当前交付状态

- 前序留言板配额仍已在 Labs 测试库应用 `comments.0007_guestbook_daily_quotas`；作者权限申请切片的 Python、模板及 CSS 已在活动 Labs worktree，隔离测试与静态产物公网哈希读回通过。
- 新功能 migration `accounts.0010_account_author_permission_requested_at` 已应用到 Labs 测试库并完成 schema 读回；已登录普通用户的动态申请页仍需可授权浏览器 session 验证。
- `kaj-labs-outbox.service` 仍为 `failed/timeout`，timer 为 `inactive/dead`；账户通知目前由活动的 Labs Celery Worker/Beat 路径消费。另有两条旧每周备份失败事件仍待按 `B-027` 调查，未改写状态。
- 留言板管理员态与认证发布、图片四档作者态浏览器路径仍需可用认证状态；本轮新申请 UI 也未做真实浏览器验收。
- 未执行生产 migration、部署、服务重启、招聘采集、Provider/AGENT 调用、真实留言/邮件或 Git 交付。

## 本轮迭代范围

当前新增切片包括注册管理员通知/一次性作者权限申请，以及管理员邮件密码重置；后续新切片仍须先记录在本台账及对应独立文档中。

### 变更记录

每完成一个切片，在本文件追加一节，至少记录：

- 日期、用户可见行为和触发入口；
- 唯一 owner、调用方、受影响文件和数据表；
- 聚焦回归命令、退出码、通过数和未执行项；
- Labs 页面或安全用户流的实际读回；
- migration、通知、Outbox、后台任务、外部服务和媒体副作用；
- 后续正式发布所需的迁移、配置、备份、回退和公告内容。

## 发布边界

- 本台账不是正式生产发布公告；Labs 验证结果不能直接写成生产能力。
- 未经当前回合明确授权，不执行生产 migration、生产备份、部署、服务重启、招聘采集、Provider/AGENT 调用或真实邮件发送。
- 测试数据库、Redis、Mailpit、媒体和缓存只属于 Labs；不复制生产数据，不删除现有测试卷或数据卷。
- 当前 Outbox 失败状态必须先有独立根因和安全验证，不能通过直接 SQL 改写事件状态消除失败。
