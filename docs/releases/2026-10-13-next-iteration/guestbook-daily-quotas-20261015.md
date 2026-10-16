# 留言板每日配额可配置（2026-10-15）

## 用户行为

管理员在“内容与互动 → 留言板管理”的每日额度区域修改首页留言板两项限制：每位注册用户每日可成功留言数、全站每日可接收留言数。保存后首页提示、管理页当前值和服务端发布拦截均使用相同配置。默认仍为 `2/20`；允许范围为每人 `1..100`、全站 `1..1000`。若要停止留言，继续使用已有留言开关，配额不允许设为零；旧 `/guestbook/` 的访客留言限流不变。

每日按上海时区自然日计算。成功创建后即计入额度；之后隐藏或删除留言不返还额度。每人上限和全站上限分别生效，先达到哪一个就由哪一个拒绝后续留言。

## 实现与数据边界

- 唯一数据 owner 是 `apps/comments` 的 GUESTBOOK `DiscussionThread`，扩展每日配额、配额版本和数据库范围约束，不复用部署环境变量或导航配置。
- 发布与配置更新锁定同一留言板线程。发布事务在锁内按配置计数并写入，保证配额更新与并发发布有序；全站自然日计数使用 top-level `(thread, created_at)` 部分索引。
- 管理配置使用版本号防止旧表单覆盖新值，变更写入独立 `comments.guestbook.quota_update` 审计事件。现有开关/登录要求表单不改变每日配额。
- 管理输入限制为正整数并在数据库与 service 双重校验；无权、越界和版本冲突都有明确失败路径，意外数据库错误继续经站点统一安全错误处理。

## 验证与 Labs 状态

- `./scripts/test apps/comments/tests/test_guestbook_board.py apps/comments/tests/test_cmt007.py apps/comments/tests/test_cmt007_http.py -q`：`12 passed in 158.95s`。测试覆盖管理页默认值、管理员保存和审计读回、首页动态提示、每人/全站额度执行、范围拒绝、版本冲突及旧访客留言兼容；使用独立 test database 与 Redis DB 15，未发送邮件。
- `manage.py check` 无问题；目标 Ruff check/format 和 `git diff --check` 通过；`npm run build:css` 成功，隔离构建产物 SHA-256 为 `c2d167c4a04b850aca44567f8036606800c04d2ebbccae96a1d488c3c740a0a6`。
- `manage.py makemigrations comments --check --dry-run` 输出 `No changes detected`；Django 对未创建的 base test DB 给出 migration-history 连接 warning。聚焦 pytest 已通过 migration runner 在独立临时 test DB 应用该 migration。
- 代码和 CSS 产物位于隔离 worktree `/home/code/.codex-worktrees/personal-blog/guestbook-quota-20261015`。用户授权后，`comments.0007_guestbook_daily_quotas` 已应用到 Labs 测试库 `kaj_test_production_clone`；迁移记录、三列、三条范围约束及 `comment_top_daily_idx` 均已读回。
- 迁移计划仅包含 `comments.0007_guestbook_daily_quotas`。迁移前 PostgreSQL 统计约为 4 条评论（表及索引 253,952 bytes）、7 条讨论线程（57,344 bytes），目标表无等待锁。
- 配额运行时代码、模板、迁移和 CSS 已定向同步到 Labs worktree；所有同步文件与隔离 worktree 逐文件 `cmp` 一致。Labs 保持 `active/running`，`/health/live` 与首页均返回 `200`；首页读回“每日上限 20 条”，CSS 公网 SHA-256 与构建产物一致：`c2d167c4a04b850aca44567f8036606800c04d2ebbccae96a1d488c3c740a0a6`。
- 当前没有可用的管理员浏览器 session；未登录的留言板管理路由返回 `403`，因此管理员态保存流程及桌面/窄屏视觉验收仍未运行。隔离 PostgreSQL-backed Django client 回归已覆盖管理员保存和读回。未触碰生产、未重启 Labs 服务、未提交或推送。
