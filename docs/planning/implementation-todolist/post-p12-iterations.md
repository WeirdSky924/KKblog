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

- 元数据：状态 `进行中`；阶段 `post-P12`；owner `accounts`；优先级 `P1`。
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
