# 首页匿名留言板（2026-10-13）

## 用户可见行为

- 首页大图右侧新增留言板：页面位于大图区域时展开，滚动到文章列表后收起为右侧按钮；按钮可手动重新展开。
- 留言板只展示发布时间、正文和管理员标记。标记使用“阅”“否”“毕”，不展示发布者身份。
- 已注册且处于可用状态的账户可通过浮窗发布纯文字留言；每个账户每天最多 2 条，留言板每天最多接收 20 条。正文总长度最多 100 个字符，其中中文字符最多 50 个，不接受换行或不可打印字符。
- 首屏读取最新 10 条；继续滚动到留言板底部时，以签名 keyset cursor 请求下一批 10 条。隐藏留言不会进入公开列表。
- 后台“内容与互动”新增“留言板管理”：管理员可以隐藏/显示、删除和设置“阅/否/毕”标记。删除沿用评论删除事实和审计链路，隐藏只影响首页公开列表。

## 实现边界与 owner

- 领域 owner 仍为 `apps/comments`，没有创建第二套留言领域。
- 首页严格入口使用独立的 `public:guestbook-board-comment-create` POST 路由；旧 `public:guestbook-comment-create` 保留历史匿名、图片和 10 分钟缓冲兼容行为，不能通过省略客户端字段绕过首页规则。
- 留言正文由 `normalize_guestbook_body` 和 `GuestbookCommentForm` 双层校验；配额服务在锁定 `DiscussionThread` 的事务中检查，避免并发请求同时穿透全局或账户日配额。
- 公开查询使用 `guestbook_board_page`：`LIMIT 11` 取一条前瞻记录、返回 10 条、按 `created_at/id` 倒序 keyset 分页，不执行总数统计，也不做作者或图片 N+1 查询。
- 管理页通过 `guestbook_admin_page` 分页读取全部顶层留言；隐藏/标记由 `moderate_guestbook_comment` 记录审计，删除由既有 `delete_comment_as_admin` owner 处理。

## 变更文件与数据

- `apps/comments/models/comment.py`、`apps/comments/migrations/0006_guestbook_board.py`：新增隐藏、标记、隐藏时间和操作者字段，以及公开列表和日配额索引。
- `apps/comments/services/posting.py`、`apps/comments/queries/threads.py`、`apps/comments/presentation/context.py`：首页发布规则、配额、公开分页和模板上下文。
- `apps/comments/guestbook_views.py`、`apps/discovery/urls.py`、`apps/discovery/templates/discovery/partials/home_guestbook*.html`：首页读写入口和弹窗。
- `apps/comments/services/guestbook_moderation.py`、`apps/comments/queries/guestbook_admin.py`、`apps/administration/views/guestbook.py`：管理操作和页面。
- `static/src/home-guestbook.js`、`static/src/discovery-home.css`、`static/src/app.js`：开合、弹窗、无限加载和响应式样式。

## 验证与运行边界

- 旧留言回归：`apps/comments/tests/test_cmt007.py apps/comments/tests/test_cmt007_http.py`，`5 passed`。
- 首页留言板新增回归：`apps/comments/tests/test_guestbook_board.py`，覆盖登录、纯文字、即时公开、2/20 日配额、10 条 keyset 分页、隐藏/标记/删除，`4 passed`。
- `manage.py check`、`makemigrations --check --dry-run comments`、目标 Ruff/format、Python 编译、JS 语法检查和 `git diff --check` 已通过；CSS/JS 构建成功。
- Labs Web、Worker、Beat 为 `active/running`，health 为 `200`，CSS/JS 本地与 Labs 公网静态响应 SHA-256 一致。
- Labs 首页首次真实读回曾因数据库停在 `comments.0005` 返回 500；经当前回合授权，已将 `comments.0006_guestbook_board` 应用到 `kaj_test_production_clone`，字段、索引和迁移记录读回正常，首页随后返回 200。生产数据库没有应用迁移。
- 本轮未执行生产 migration、部署、生产重启、招聘采集、Provider/AGENT 调用、真实邮件或 Git 交付。
