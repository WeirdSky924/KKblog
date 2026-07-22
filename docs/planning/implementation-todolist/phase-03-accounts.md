# P3 账号、安全与基础通知审计（12）

退出门禁：账户、会话、安全限制、角色生命周期、通知基础和管理员审计基础由唯一服务闭环。

### ACC-001 建立账户、角色、会话与唯一管理员数据骨架
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：建立不可复用 UUID 账户、大小写不敏感邮箱、昵称原展示值及 Unicode `casefold` 规范值唯一约束、角色、会话摘要及恰好一个管理员且兼任作者的初始化门禁；首次登录必须改密。development/test 管理员 fixture 为 `admin@kaj.test`；production 必须使用另行提供的真实邮箱并关闭失败。
- 来源：访谈 Q016-Q035、Q190、Q204-Q208、Q285-Q286、Q295；`data/02-identity-content-fields.md` §Account/Role/LoginSession；`flows/01-account-access-state-machine.md`。
- 依赖：前置 `FND-003`、`FND-006`、`DEC-002`、`DEC-003`；后续 `OBS-004`、`OBS-001`、`ACC-002`、`ACC-003`、`ACC-005`、`ACC-011`、`MED-001`、`ACC-007`、`CNT-001`、`CMT-001`、`OBS-003`、`EXC-007`、`ADM-001`、`QA-001`、`QA-006`。
- 文件：`apps/accounts/models/`、首批 migrations、bootstrap command/service、测试工厂。
- 边界：不使用 Django 默认 username 作为登录标识；不保存明文密码/token；不创建第二管理员或固定初始密码。
- 影响：数据：账户/角色/会话约束；权限：唯一管理员；审计：初始化记录；缓存/异步/媒体/通知：无。
- 测试/验收：先 RED 邮箱/昵称规范值/角色部分唯一、casefold 并发冲突、管理员不可撤销作者/自删、一次性初始密码、production 缺真实管理员邮箱和测试邮箱泄入生产；`uv run pytest apps/accounts/tests -q` + migration 读回。
- 风险/停止：migration 约束无法并发兜底、bootstrap secret 可复用或日志泄密即停止；只在隔离库回滚。
- 授权：建模/隔离测试 `否`；真实初始化管理员和迁移生产 `是`。

### OBS-004 建立管理员写操作事务审计与安全查询
- 元数据：状态 `待处理`；阶段 P3；owner `operations`；优先级 P0。
- 目标/行为：所有管理员状态/权限写与业务事务同成败，永久记录actor/目标/action/trace/完整IP/safe before-after；支持关键字/类型/目标/时间查询和详情。
- 来源：访谈 Q192-Q198、Q294；`contracts/04-events-errors.md` §审计schema；`data/03-interaction-operations-fields.md` §AuditEntry。
- 依赖：前置 `FND-004`、`ACC-001`；后续 `ACC-002`、`ACC-009`、`ACC-010`、`ACC-011`、`CNT-010`、`CNT-011`、`CNT-008`、`CMT-006`、`CMT-007`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-005`、`OBS-003`、`EXC-004`、`ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-001`、`QA-006`。
- 文件：audit model/schema registry/service/query/admin templates/tests。
- 边界：只读页面不审计；管理员查看他人文章走通知事件；正文/媒体只记revision/asset ID；未知字段默认拒绝。
- 影响：数据：永久AuditEntry；权限：admin详情/IP；审计核心；缓存无；异步无；媒体只ID；通知无。
- 测试/验收：RED 审计写失败回滚业务、秘密字段拒绝、列表IP掩码/详情完整、正文不复制；跨域事务读回。
- 风险/停止：审计可异步丢失、自动序列化ORM或秘密/原文件进入记录即停止所有管理员写交付。
- 授权：`否`。

### OBS-001 建立站内通知、回执与去重数据基础
- 元数据：状态 `待处理`；阶段 P3；owner `notifications`；优先级 P0。
- 目标/行为：建立 Notification、Receipt、接收者状态和 dedupe 约束，提供仅接受已注册模板键和稳定对象 ID 的投递端口；业务通知永久保留到管理员隐藏或删除。
- 来源：访谈 Q061-Q068、Q289、Q305-Q309；`modules/09-notifications-observability.md` §通知模型/事件；`contracts/04-events-errors.md` §通知模板安全。
- 依赖：前置 `FND-005`、`FND-006`、`ACC-001`；后续 `CMT-003`、`OBS-008`、`OBS-002`、`OBS-003`、`EXC-005`、`QA-001`、`QA-006`。
- 文件：notification/receipt models、基础 schema registry、delivery port、recipient queries、tests。
- 边界：本任务不注册尚未存在的领域模板，不消费具体业务事件；payload 无任意 HTML/URL、正文、reporter、秘密、原始 IP 或路径；用户不能删除个人通知。
- 影响：数据：Notification/Receipt/dedupe；权限：recipient；审计由 OBS-004；缓存无；异步只定义投递端口；媒体无；通知基础事实。
- 测试/验收：RED receipt 唯一、他人读取、重复 dedupe key、未知模板键和危险 payload；migration 与真实 DB 读回。
- 风险/停止：通知表允许任意 payload、接收者越权或业务模块绕过投递端口直接写通知即停止。
- 授权：`否`。

### ACC-002 实现邀请码生成、状态、撤销与并发兑换
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：管理员可一次生成 1..1000 个 16 位 Crockford Base32 单次码，选择 1/3/7/30 天，原码仅展示一次；可筛选、单/批量撤销并查看使用者。
- 来源：访谈 Q003-Q005、Q126-Q129、Q249-Q251；`modules/02-accounts-access.md` §数据与不变量；`data/04-indexes-constraints.md` §兑换锁。
- 依赖：前置 `ACC-001`、`OBS-004`；后续 `ACC-003`、`ACC-004`、`ADM-003`、`QA-003`、`QA-006`。
- 文件：invite model/service/query/forms、migration、管理 partial、tests。
- 边界：数据库只存带密钥摘要/尾号；未成功创建账户前不消费；无备注字段；不能撤销已用码。
- 影响：数据：InviteCode；权限：管理员生成/撤销；审计：所有写动作；缓存：无；异步：过期派生；媒体/通知：无。
- 测试/验收：RED 同码双并发仅一成功、过期边界、批量 1001 拒绝、原码不可回读；pytest 数据读回与管理 UI 流。
- 风险/停止：原码进入日志/历史、行锁缺失或状态重复保存漂移即停止。
- 授权：`否`；不使用真实用户邮箱。

### ACC-003 实现用途隔离的验证码与开发邮件投递
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：注册、验证码登录、重置、新邮箱分别发送 6 位码；10 分钟有效、1 分钟重发、新码覆盖旧码、第五次错误失效，开发邮件可在 Mailpit 读回。
- 来源：访谈 Q016-Q023、Q155-Q157、Q228-Q230；`flows/01-account-access-state-machine.md` §验证码；`data/05-storage-lifecycle.md` §Redis 键。
- 依赖：前置 `RUN-002`、`ACC-001`、`ACC-002`；后续 `ACC-004`、`ACC-005`、`ACC-006`、`ACC-009`、`QA-003`、`QA-006`。
- 文件：verification services/cache/mail ports、邮件模板、Redis adapter、forms/tests。
- 边界：验证码只存摘要且按用途/邮箱绑定；Redis 丢失允许 challenge 失效；首版业务通知不走邮件。
- 影响：数据：永久 SecurityEvent 仅摘要；权限：注册/敏感动作 challenge；缓存：Redis；异步：邮件提交后；通知：Mailpit/未来 Resend；审计/媒体无。
- 测试/验收：RED 10 分钟、重发覆盖、5 次、用途串用、Redis flush、Mailpit 捕获；`pytest` + 隔离邮件读回。
- 风险/停止：邮件中泄露内部状态、枚举已注册邮箱、真实外发或验证码写日志时停止。
- 授权：Mailpit `否`；Resend/真实邮箱 `是`。

### ACC-004 实现直接/邀请码注册与成功自动登录
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：直接注册默认关闭；关闭时仍可邀请码注册，开放时两种路径并存；先验邀请码再发码，最终成功才消费并创建 12h/30d 会话后回首页。
- 来源：访谈 Q003、Q016、Q205、Q249-Q252、Q317；`flows/01-account-access-state-machine.md` §注册时序；`contracts/03-frontend-contract-map.md` §身份页面。
- 依赖：前置 `ACC-002`、`ACC-003`、`FND-004`；后续 `ACC-005`、`QA-003`、`QA-006`。
- 文件：registration service/policy/forms/views/templates/HTMX partials/tests。
- 边界：不人工审批、不免密码注册、不在半完成流程占用邀请码；IP Block/容量/限流服务端重判。
- 影响：数据：Account/Invite/Session/SecurityEvent；权限：注册开关/IP；审计：管理员开关另由设置；缓存：Redis challenge；通知：验证码；异步/媒体无。
- 测试/验收：RED 开关组合、邀请绑定邮箱、DB 唯一冲突仍保留邀请码、重复提交；Playwright 访客注册→自动登录→首页。
- 风险/停止：账户和邀请码非同事务、成功 UI 先于 commit 或可绕过注册关闭即停止。
- 授权：`否`；真实生产注册开关上线随部署授权。

### ACC-005 实现密码/邮箱码双登录与会话认证
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：同页 tabs 支持密码和邮箱码；两者都有 30 天选项，默认 12 小时；Cookie 只含随机 token，数据库只存摘要并更新最后活动。
- 来源：访谈 Q017、Q026-Q027、Q134、Q190、Q226-Q227、Q252；`data/02-identity-content-fields.md` §LoginSession；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `ACC-001`、`ACC-003`、`ACC-004`；后续 `ACC-006`、`ACC-008`、`ACC-009`、`ACC-010`、`ACC-011`、`CNT-005`、`DSC-006`、`CMT-003`、`CMT-008`、`QA-003`、`QA-006`。
- 文件：authentication/session services、middleware/backend、login views/templates、tests。
- 边界：无第三方登录/公共认证 API/2FA；禁用账户只显示通用禁用文案；remember 不跨浏览器复制。
- 影响：数据：LoginSession/SecurityEvent；权限：全站 actor；缓存：登录计数；审计：安全事件；通知：登录码；异步/媒体无。
- 测试/验收：RED 12h/30d 到期、摘要不可反推、Cookie Secure/HttpOnly/SameSite、禁用/过期；Playwright 双 tab/回跳。
- 风险/停止：原 token 落库/日志、会话固定攻击、不同入口授权顺序漂移即停止。
- 授权：`否`。

### ACC-006 实现密码重置、登录态改密与新邮箱验证
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：忘记密码用邮箱码并撤销全部会话；登录态改密需当前密码、保留并旋转当前会话且撤销其他；改邮箱只需新邮箱码并旋转当前凭证。
- 来源：访谈 Q024-Q032；`flows/01-account-access-state-machine.md` §会话/邮箱与密码修改；`contracts/01-application-services.md` accounts 表。
- 依赖：前置 `ACC-003`、`ACC-005`；后续 `ACC-008`、`QA-003`、`QA-006`。
- 文件：credentials services/forms/views/templates、session rotation tests。
- 边界：改邮箱不要求旧邮箱/当前密码；改密不要求邮箱码；重置后不保留当前会话。
- 影响：数据：Account/Session/SecurityEvent；权限：凭证轮换；审计：安全事件；缓存：challenge/限制；通知：验证码；异步/媒体无。
- 测试/验收：RED 三种流程的会话矩阵、邮箱并发唯一、当前 token 变化；Playwright 多浏览器会话读回。
- 风险/停止：旧 token 仍有效、事务部分撤销或错误暴露邮箱存在性即停止。
- 授权：`否`；真实邮件 `是`。

### ACC-008 实现设备会话列表、定向退出与退出所有设备
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P1。
- 目标/行为：本人查看设备/浏览器、登录时间、最后活动、掩码 IP；可退出指定含当前会话；“退出所有设备”二次确认并包含当前会话。
- 来源：访谈 Q244-Q246；`flows/01-account-access-state-machine.md` §会话状态；`contracts/03-frontend-contract-map.md` §sessions。
- 依赖：前置 `ACC-005`、`ACC-006`；后续 `QA-003`、`QA-006`。
- 文件：session queries/revoke services、views/templates/HTMX、tests。
- 边界：用户不能看/撤销他人会话；列表不显示 token 或完整 IP；不存在“仅退出其他设备”主动作。
- 影响：数据：Session revoked_at；权限：本人；审计：SecurityEvent；缓存/异步/媒体/通知无。
- 测试/验收：RED ownership、重复撤销幂等、当前会话响应后失效；Playwright 两浏览器+确认焦点/取消/成功。
- 风险/停止：确认前退出、目标 ID 越权或当前 Cookie 在全部退出后仍有效即停止。
- 授权：`否`。

### ACC-009 实现登录/验证码临时限制与安全事件
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：密码连续5错限制1小时并阻止密码/码登录与重置；验证码每邮箱/IP每日20次、上海00:00重置；管理员可清账户/IP限制。
- 来源：访谈 Q021-Q022、Q226-Q229、Q294；`modules/02-accounts-access.md` §关键流程；`data/05-storage-lifecycle.md` §Redis 键。
- 依赖：前置 `ACC-003`、`ACC-005`、`OBS-004`；后续 `ACC-010`、`ADM-003`、`QA-003`、`QA-006`。
- 文件：restrictions services/cache keys、SecurityEvent model/query、admin commands/tests。
- 边界：无 CAPTCHA、无匿名日评论上限；Redis 重启可清临时状态；限制消息不暴露计数键/账户存在性。
- 影响：数据：永久 SecurityEvent/IP；权限：临时拒绝；审计：管理员清除；缓存：Redis；通知/异步/媒体无。
- 测试/验收：冻结 Clock 测 5次/1h/00:00/20次、Redis flush、管理员清除；直接请求不能绕过。
- 风险/停止：时区日界错误、明文邮箱/IP进入 Redis key 或清除范围过宽即停止。
- 授权：`否`。

### ACC-010 实现永久 IP 封禁与请求级网络策略
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：管理员永久封禁/解除 IP、可写备注；被封 IP 仅能作为访客浏览大众内容，即使带有效会话也拒绝其他动作并显示通用文案。
- 来源：访谈 Q292-Q294；`flows/01-account-access-state-machine.md` §服务端判定顺序；`contracts/02-authorization-matrix.md` §策略组合。
- 依赖：前置 `ACC-005`、`ACC-009`、`RUN-003`、`OBS-004`；后续 `CMT-002`、`ADM-003`、`QA-002`、`QA-003`、`QA-006`。
- 文件：IpBlock model/service/policy/middleware/query、proxy IP parsing、tests。
- 边界：不自动过期、不删除账户；列表掩码、详情才显示完整 IP；备注永不展示给被封用户。
- 影响：数据：IpBlock/SecurityEvent；权限：网络最高优先级；审计：封/解；缓存：不得缓存授权；其余无。
- 测试/验收：RED 代理头信任、IPv4/IPv6规范化、已登录降为访客、公开阅读仍可；Playwright/直接 POST 双证据。
- 风险/停止：客户端可伪造 IP、Caddy 信任链不清或封禁误伤服务器管理连接时停止部署。
- 授权：代码 `否`；对真实 IP 执行封禁 `是`。

### ACC-011 实现作者角色、账号禁用/启用/删除生命周期
- 元数据：状态 `待处理`；阶段 P3；owner `accounts`；优先级 P0。
- 目标/行为：唯一管理员授予/撤销作者并通知；禁用立即撤销会话且不通知；启用恢复登录；管理员可删除非管理员账户并按规则匿名化/清理。
- 来源：访谈 Q033-Q035、Q131-Q134、Q284-Q301；`flows/01-account-access-state-machine.md` §账户/角色；`contracts/04-events-errors.md` §事件注册表。
- 依赖：前置 `ACC-001`、`ACC-005`、`FND-005`、`OBS-004`；后续 `CNT-009`、`CMT-011`、`OBS-008`、`AUT-001`、`ADM-002`、`QA-002`、`QA-003`、`QA-006`。
- 文件：roles/account lifecycle services/policies/events、deletion disposition DTO、tests。
- 边界：不能自助注销、管理员自删、第二管理员或文章转移；accounts 不直接写 content/comments/media 私表。
- 影响：数据：Account/Role/Session及删除记录；权限：角色/禁用；审计：全部管理员写；异步：outbox；媒体/通知由消费者；缓存后续失效。
- 测试/验收：RED 唯一管理员保护、撤销作者保留文章归属、禁用会话、删除释放邮箱昵称/新 UUID；跨域事件重复幂等。
- 风险/停止：跨域部分清理、历史评论绑定新身份或删除作者未处理文章即停止；删除只在隔离数据演练。
- 授权：代码/隔离测试 `否`；生产账户禁用/删除 `是`。

[返回总索引](../implementation-todolist.md)
