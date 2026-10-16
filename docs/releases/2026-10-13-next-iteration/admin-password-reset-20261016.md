# 管理员邮件密码重置（2026-10-16）

## 用户可见行为

管理员在用户管理中点击“重置密码”，确认后，系统向该账户绑定邮箱发送 30 分钟有效的链接。用户点击链接后输入并确认新密码；成功后被带回登录页，账户原有设备会话全部撤销。

## 实现边界

- `apps.accounts` 拥有令牌、密码更新、一次性消费和会话撤销；管理 View 通过 accounts 公共服务签发链接。
- 每个账户最多保留一条重置状态。数据库只存 HMAC 摘要，且摘要绑定当前密码哈希和规范邮箱；重发、改密或改邮箱后旧链接均不可兑换。
- 邮件中的随机令牌只放在 URL fragment。浏览器读取后立即移除 fragment；重置响应设置 no-store/same-origin 并关闭分析脚本。fragment 不会进入 Referer。
- 表单复用现有密码强度规则并要求两次密码一致。成功后消费令牌、清除 `must_change_password` 并撤销全部现有会话，不自动登录。
- 每次管理员请求写入 operations 永久审计和脱敏 SecurityEvent；审计和日志不保存令牌、密码或邮件正文。
- 新 migration `accounts.0011_admin_password_reset` 只建立独立一对一表。迁移未应用时，页面返回安全的不可用错误；不得通过修改旧账户数据绕过 schema 门禁。

## 涉及文件

- Accounts 模型、公开服务、邮件模板、独立兑换 View/Form/模板和 `static/src/admin-password-reset-link.js`。
- Administration 用户确认表单、用户管理 View/模板与 Operations 审计 schema。
- Accounts migration `0011_admin_password_reset`。
- 账户服务/流程/数据/授权架构、页面状态矩阵、P12 后迭代清单和本公告台账。

## 验证与限制

- RED 测试 `apps/accounts/tests/test_admin_password_reset.py::test_admin_password_reset_link_route_is_registered` 在实现前按预期失败：路由尚未注册，`1 failed in 3.03s`。
- GREEN 静态检查：目标 Ruff check 退出 `0`；`node --check static/src/admin-password-reset-link.js` 退出 `0`；`manage.py check --settings=config.settings.test` 退出 `0`；`makemigrations accounts --check --dry-run --settings=config.settings.test` 退出 `0`，`No changes detected`；`git diff --check` 退出 `0`。最终 `npm run build:js` 退出 `0`，输出 1.1 MB bundle，耗时 `2515ms`。
- Labs 读回：服务工作目录仍是当前 Labs worktree，`active/running`；公网 `/health/live` 与重置页 GET 均返回 `200`。本地/公网 `static/dist/app.js` SHA-256 相同：`acb443131eaab3efbcb8634e6207d87ac818ef40c3ee8b736177d119d721e443`。真实浏览器页显示密码和确认字段，URL fragment 已移除；390px 下 document/body 宽度为 `375px`，视口 `390px`，无横向溢出；Tab 从新密码移动到确认密码；控制台 errors/warnings 均为 `0`。
- 两次首次浏览器导航等待超时，期间一次快照为 Nginx 504；随后公开路由恢复为 `200`，浏览器快照读到页面。截图命令和主题按钮交互各自超时，未重试；768px 与 1440px 视觉截图未验收。
- 聚焦 PostgreSQL/Redis/Mailpit 回归未运行：当前 shell 缺少 `KAJ_TEST_DATABASE_URL`、`KAJ_TEST_REDIS_URL`、`KAJ_TEST_MAILPIT_SMTP_URL`、`KAJ_TEST_MAILPIT_API_URL`。没有改用共享 Labs 数据库或 Mailpit。
- 测试浏览器只使用伪造的 URL fragment 检查前端读取/清除行为，未提交密码；没有可授权普通用户/管理员 session，因此没有声称完成真实管理员操作或邮件兑换浏览器流。
- 初次读回时 Labs 尚未应用 `accounts.0011_admin_password_reset`；用户复测后确认 `account_admin_password_reset` 表不存在，这是管理服务捕获 `ProgrammingError` 并返回“管理员密码重置功能暂不可用”的直接原因。
- 用户明确授权后，仅对 Labs `kaj_test_production_clone` 应用 `accounts.0011_admin_password_reset`。PostgreSQL 读回字段 `account_id, token_digest, created_at, expires_at, consumed_at`；确认账户主键/外键、摘要唯一约束、`account_admin_pw_reset_positive_lifetime` 检查约束和 `django_migrations` 记录；迁移后计划为空。Labs Web 保持原 PID/启动时间，`health/live=200`、`health/ready=200`。当前缺少可授权管理员 session 和隔离 Mailpit，因此没有验证按钮点击、邮件投递或链接兑换。
- 未发送邮件；未执行生产 migration/部署/重启、招聘采集、Provider/AGENT 调用或 Git 写操作。

## 下一步与发布准备

- 在专用隔离 PostgreSQL、Redis 和 Mailpit 中完成服务与用户流回归。
- 认证管理员/用户浏览器状态可用后完成确认发送、Mailpit 测试邮件链接兑换和密码登录读回；不创建或借用账户。
- 正式发布需要单独准备数据库备份与回退评估、应用 migration 和代码的顺序、真实邮件配置核验及独立正式公告；本记录不是生产发布授权。
