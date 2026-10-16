# 注册管理员通知与作者权限申请（2026-10-16）

## 用户可见行为

- 注册成功时，accounts 在注册事务中写入 `account.registered.v1`；notifications 通过既有 Outbox 向当前启用的管理员创建站内通知。
- 所有已登录账户都能从顶部“我的文章”入口进入。作者仍看到原文章工作台；普通用户只看到作者权限提示和一次性申请按钮。
- 首次申请将 `Account.author_permission_requested_at` 与 `account.author_permission_requested.v1` 在同一事务提交。重复或并发请求不会写入第二个事件；刷新后显示“已通知管理员申请作者权限”。
- 管理员通知不含邮箱、昵称或自由文本，目标按账户 UUID 筛选既有用户管理页面；管理员仍需通过现有确认流程授予作者角色。

## Owner 与数据边界

- 账户状态、一次性服务、注册事件和 migration 归 `apps/accounts`。
- Notification/Receipt、管理员通知模板和事件消费归 `apps/notifications`；事件由 `config/outbox_transport.py` 路由。
- `/author/articles/` 只编排登录用户状态；创建、编辑等其他路由继续保留作者权限门禁。
- 管理员用户搜索支持精确账户 UUID，以便通知链接定位对应账户。
- migration：`accounts.0010_account_author_permission_requested_at`，仅新增 nullable timestamp，可逆；隔离 pytest 数据库已实际应用。用户明确授权后，Labs `kaj_test_production_clone` 已应用；生产数据库未应用该 migration。

## 验证结果

- 聚焦 PostgreSQL/Redis/Mailpit 回归：最终代码状态 `12 passed in 247.51s`，退出 0。覆盖普通用户入口、提交后持久化状态、重复 POST、作者工作台兼容、注册事件、管理员通知 target/幂等消费和已有通知/角色回归。
- 对本轮 Python 文件运行 Ruff lint：退出 0；20 个 Python 文件 format check 与 `git diff --check`：通过。
- `DJANGO_SETTINGS_MODULE=config.settings.test ... manage.py check`：退出 0，`System check identified no issues`。
- `makemigrations --check --dry-run`：退出 0，`No changes detected`。Django 对未创建的基准库 `kaj_test_author_request` 发出连接 warning；聚焦 pytest 已在临时测试库中创建并应用 migration。
- `npm run build:css`：退出 0。Labs 服务 `active/running`，`/health/live=200`，首页 `200`，未登录 `/author/articles/` 按预期 `302` 到登录页。
- 生成 CSS SHA-256 `ca118a4f8f2a2b8b588d656ccd796f71194d20d88aeb426072498c79574ec509`，与 Labs 公网 `/static/dist/styles.css` 读回一致。
- 未取得可授权的普通用户/管理员浏览器 session；虽然 Labs schema 已就绪，仍没有访问登录后的新申请页面，也没有执行桌面/手机视觉验收。

## Labs migration 与运行态读回（2026-10-16，用户授权后）

- `migrate --plan accounts 0010` 只列出 `accounts.0010_account_author_permission_requested_at`；`migrate accounts 0010 --noinput` 退出 0，返回 `Applying ... OK`。
- `django_migrations` 已记录该 migration；`public.account.author_permission_requested_at` 为可空 `timestamp with time zone`、无默认值，现有 2 个账户值为 `NULL`；迁移后 `migrate --plan accounts 0010` 返回 `No planned migration operations`。
- `kaj-labs.service` 工作目录仍为 Labs worktree 且 `active/running`；公网 `/health/live`、`/health/ready` 均为 `200`，匿名 `/author/articles/` 为 `302` 登录跳转。
- 在该次迁移读回时没有创建或借用账户，也没有执行认证态浏览器验收；Outbox service/timer 当时为 `failed/failed`、`inactive/dead`，通知尚未消费。随后发现 Worker 旧进程并完成恢复，见下方记录。

> 后续用户实测确认通知未到达；实际根因为 Labs Celery Worker 仍运行 2026-10-13 启动时加载的旧代码。只重启 Worker 后，两类账户事件均由当前 consumer 成功处理，数据库分别读回 1 条发给启用管理员的未读通知回执。完整运行态证据见 [`author-notification-worker-runtime-20261016.md`](./author-notification-worker-runtime-20261016.md)。

## 尚未完成的 Labs 运行验证

- 登录后普通用户申请页、管理员通知页的真实浏览器流仍未验证，因为没有可授权 session。
- 在本节记录时，`kaj-labs-outbox.service` 为 `failed/failed`，`kaj-labs-outbox.timer` 为 `inactive/dead`；此状态没有导致后来账户通知继续阻塞，Celery Worker 热重载修复见 [`author-notification-worker-runtime-20261016.md`](./author-notification-worker-runtime-20261016.md)。旧每周备份失败事件仍待独立调查。
- 生产 migration、部署、服务重启、招聘采集、Provider/AGENT、真实邮件及 Git 写操作均未执行。
