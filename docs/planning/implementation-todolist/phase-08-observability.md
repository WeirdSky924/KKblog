# P8 通知与可观测性集成（6）

退出门禁：领域通知、浮层/通知页、错误检索、任务最终失败和容量告警均真实读回。

### OBS-005 实现 RuntimeError、trace 聚合与管理员错误检索
- 元数据：状态 `完成`；阶段 P8；owner `operations`；优先级 P0。
- 目标/行为：未预期异常脱敏后永久保存并按fingerprint聚合次数/首末时间；用户见通用文案+trace，管理员按trace/错误码/关键字/时间查详情。
- 来源：访谈 Q199-Q203；`modules/09-notifications-observability.md` §运行错误；`contracts/04-events-errors.md` §Trace/脱敏。
- 依赖：前置 `FND-004`、`OBS-004`；后续 `OBS-009`、`ADM-008`、`QA-001`、`QA-003`、`QA-006`。
- 文件：RuntimeError model/service/redaction/fingerprint/query、handler sink/admin UI/tests。
- 边界：不得保存密码/码/token/Cookie/Authorization/.env/正文/原上传；记录失败仅向stderr写最小安全诊断。
- 影响：数据：永久错误记录；权限：admin；审计：查看不审计；缓存无；异步：任务错误关联；媒体无；通知仅终败。
- 测试/验收：注入全类秘密并验证页面/DB/stderr；相同fingerprint聚合、trace不存在诚实空态；Playwright用户/管理员两面。
- 风险/停止：任一sink泄密、错误记录递归崩溃或用户可读取堆栈即停止。
- 授权：`否`。
- 证据：RED `pytest apps/operations/tests/test_obs005.py -q` 在收集期因缺少 `RuntimeError` owner 退出 2。实现 `RuntimeError` fingerprint 聚合与可多错误关联同一 trace 的永久 occurrence、严格安全上下文 schema、无异常原文的脱敏堆栈、并发唯一约束和三次冲突重入；core 仅调用可配置 sink，operations 写库失败只向 stderr 输出静态标记、合法 trace 与安全异常类型。管理员 query/UI 支持 trace、错误码、关键字、上海日期和详情，普通用户仍只见通用 500 与 trace。最终聚焦退出 0，`6 passed`；operations、管理员 wiring 与 HTTP 安全回归退出 0，`40 passed`；Ruff/format（目标 53 文件）、Django check、migration drift 与 `git diff --check` 均退出 0。隔离 PostgreSQL 应用 `operations.0003_runtime_error` 后，含 password/code/token/Cookie/Authorization/连接串/正文/邮箱/IP/原路径的 HTTP 异常在页面、DB、日志与 stderr 均无原值，同 fingerprint 两次读回 count=2、两个不同 fingerprint 可关联同一 trace，未知 trace 返回诚实空态。`blog-playwright-cli` 以普通错误面和管理员身份验证 390/768/1440、light/dark/eye-care、键盘 Enter 查询、详情/空态和局部表格滚动；发现并修复 390 长 fingerprint/pre 页面溢出，最终三视口页面 scrollWidth 等于 viewport。全仓 Ruff 仍被基线 `apps/comments/tests/test_cmt004.py` 的既有 import 顺序阻断；原始架构 guard 仍因 P7 comments/moderation→operations 的既有九处公共端口调用与未提交本地映射漂移退出 1，按该已确认映射注入审计退出 0，OBS-005 未新增反向边。未执行生产 migration、生产数据/日志读取、提交、推送、部署或服务重启。

### OBS-008 完成领域事件模板、通知去重与集成回执
- 元数据：状态 `完成`；阶段 P8；owner `notifications`；优先级 P0。
- 目标/行为：在通知基础表和 Outbox 就绪后，为账户、内容、评论和审核事件注册版本化安全模板；同一事件按接收者和业务日去重，并可从事件到 Receipt 读回。
- 来源：`contracts/04-events-errors.md` §事件注册表/通知模板安全；`modules/09-notifications-observability.md` §通知事件；`reference/01-requirements-resolution.md` §通知口径。
- 依赖：前置 `OBS-001`、`FND-005`、`ACC-011`、`CNT-011`、`CMT-011`；后续 `OBS-002`、`OBS-003`、`OBS-009`、`EXC-003`、`EXC-005`、`QA-003`、`QA-004`、`QA-006`。
- 文件：`apps/notifications/templates/`、事件消费者注册表、dedupe/receipt 集成测试。
- 边界：不创建第二通知模型，不允许业务模块直接拼文案；payload 不含正文、举报人、秘密、原始 IP 或文件路径；P9 的导入导出模板必须复用本任务注册端口扩展，不在 P8 预实现 Exchange；不代替通知基础存储。
- 影响：数据：模板版本、Receipt、dedupe；权限：按接收者重判；审计：管理员通知动作沿用 OBS-004；缓存无；异步：Outbox 消费；媒体无；通知：领域通知真实投递。
- 测试/验收：RED 重复事件、兼任角色、同文章/上海日聚合、模板未知字段、账户删除收件；真实 Outbox 消费后 DB 通知与 Receipt 读回。
- 风险/停止：模板字段未注册、重复或泄露敏感 payload、消费成功但 Receipt 缺失时停止所有通知 UI 集成。
- 授权：`否`；生产群发和真实外发邮件仍按 OBS-003/OBS-009 授权。
- 证据：RED `pytest apps/notifications/tests/test_obs008.py tests/integration/test_obs008_outbox.py -q` 在收集期因缺少领域消费者与应用 transport 退出 2。实现 notifications 唯一 owner 下 12 个版本化 schema/纯文本 renderer、必填/枚举/日期/理由校验、接收者写前重判、兼任角色去重、Receipt 集合强读回，以及管理员查看按接收者+文章+上海日期聚合；合法的自删/作者删评论事件安全终结但不通知，未知事件与尚属 OBS-009 的 `task.final_failed.v1` 关闭失败。`config` 组合根复用现有 account/content/moderation/discovery consumer，26/27 个当前实际事件均已路由或明确终结，唯一延后项为 `task.final_failed.v1`；高频 Outbox Celery 入口直接复用 `publish_batch` 与 `execute_celery_entry`，未建立第二套重试。最终聚焦退出 0，`14 passed`；notifications、账户生命周期、内容/评论事件、Outbox 与 TaskRun 相关回归退出 0，`70 passed`；目标 Ruff/format（26 文件）、Django check、migration drift 与 `git diff --check` 均退出 0。隔离 PostgreSQL 应用全部 migration 后，经 Redis DB 14 与真实 Celery solo worker 投递 `tag.reviewed.v1`，读回 Outbox `published/attempts=1/lease cleared`、consumer `processed/attempts=1/lease cleared`、Notification/Receipt 各 1、TaskRun `succeeded/result_ref=outbox:1:1/lease cleared`；第二次 broker 调度读回 `outbox:0:0` 且通知/回执仍各 1。专用 worker、数据库与 Redis namespace 已清理，读回数据库不存在、Redis DB size=0、无遗留进程。本卡无用户页面，浏览器状态由 OBS-002/003 验收。原始架构 guard 仍被 P7 既有九处 comments/moderation→`operations.public` 映射漂移阻断；临时加入这两条已确认公共端口许可后全 app AST owner 审计违规为 0，本任务未新增反向边。未执行生产事件消费、生产 migration、真实群发/邮件、部署、服务重启、提交或推送。

### OBS-002 实现通知浮层、完整 overlay、通知页与已读
- 元数据：状态 `进行中`；阶段 P8；owner `notifications`；优先级 P1。
- 目标/行为：Header hover显示最新5条，点击打开完整浮层；查看全部到通知页；逐条/全部已读清除红点，用户无删除按钮；覆盖空/错误/隐藏态。
- 来源：访谈 Q063、Q066、Q242-Q243；`contracts/03-frontend-contract-map.md` §身份页面；原型 account/notifications。
- 依赖：前置 `OBS-001`、`OBS-008`、`DSC-001`；后续 `ADM-008`、`QA-003`、`QA-006`。
- 文件：popover/inbox queries、mark read services、partials/overlay/page、cursor/tests。
- 边界：只读本人Receipt；后台Job接受不显示完成；hover在触屏有等价点击入口；隐藏/删除通知查询排除。
- 影响：数据：read_at；权限：本人；审计无；缓存：不得整页串用户；异步无；媒体无；通知UI。
- 测试/验收：RED 并发mark-all、最新5/游标、他人通知；Playwright hover/触摸/键盘/focus/overlay/空态/1440/390。
- 风险/停止：打开即错误标已读、红点与DB不一致、浮层焦点逃逸或移动端无入口即停止。
- 授权：`否`。

### OBS-003 实现管理员群发、读回、隐藏/恢复/删除
- 元数据：状态 `待处理`；阶段 P8；owner `notifications`；优先级 P1。
- 目标/行为：唯一管理员群发固定给全部注册用户，可看每人已读；隐藏全体不可见且可恢复，删除全体不可见且产品不可恢复；所有写永久审计。
- 来源：访谈 Q063-Q067；`modules/09-notifications-observability.md` §通知模型；`contracts/02-authorization-matrix.md` §通知。
- 依赖：前置 `OBS-001`、`OBS-004`、`OBS-008`、`ACC-001`；后续 `ADM-008`、`QA-002`、`QA-003`、`QA-006`。
- 文件：broadcast services/queries/admin forms/templates、audit schema/tests。
- 边界：不允许自选受众；用户不能删除；删除可保留业务记录/审计但无恢复UI；发送不能漏注册用户或给已删除账户。
- 影响：数据：Notification+全体Receipt/hidden/deleted；权限：admin；审计：前后值；缓存无；异步：批量可服务内分批；媒体无；通知核心。
- 测试/验收：RED 并发注册/群发边界、全体回执、隐藏/恢复/删除、普通用户伪造；Playwright读回列表。
- 风险/停止：部分群发无明确终态、选择受众意外出现或删除可被普通入口恢复即停止。
- 授权：`否`；生产群发 `是`。

### OBS-009 实现任务最终失败通知与运维邮件集成
- 元数据：状态 `待处理`；阶段 P8；owner `operations`；优先级 P1。
- 目标/行为：TaskRun 达到三次失败后写 RuntimeError、生成一次站内通知；健康、磁盘、备份和运维类任务再按供应商配置发送管理员邮件，重复失败按小时去重。
- 来源：`contracts/05-background-tasks.md` §统一任务协议/任务测试；`modules/09-notifications-observability.md` §TaskRun 与告警；`contracts/04-events-errors.md` §task.final_failed；DEC-002。
- 依赖：前置 `OBS-006`、`OBS-005`、`OBS-008`、`FND-005`；后续 `OBS-010`、`EXC-005`、`EXC-006`、`EXC-007`、`QA-001`、`QA-003`、`QA-004`、`QA-006`。
- 文件：TaskRun final-failure consumer、告警 dedupe、Mailpit/Resend adapter、运维通知测试。
- 边界：不改变 TaskRun 重试裁决，不发送业务通知邮件，不在没有发件身份时假装外发成功；Mailpit 仅用于隔离测试。
- 影响：数据：TaskRun/RuntimeError/告警记录；权限：仅管理员；审计：任务结果沿用 owner；缓存：小时去重；异步：事件消费；媒体无；通知：站内和受控运维邮件。
- 测试/验收：RED 三次失败、重复 final_failed、持续故障小时边界、Mailpit 捕获、Resend 缺配置安全失败；DB/邮件读回一致。
- 风险/停止：业务事件外发邮件、重复告警风暴、真实凭据进入日志或测试时停止；生产 Resend 需要 DEC-002 和当前回合授权。
- 授权：隔离 Mailpit `否`；真实 Resend/生产告警 `是`。

### OBS-010 实现周期健康采样、容量告警与自动解除
- 元数据：状态 `待处理`；阶段 P8；owner `operations`；优先级 P0。
- 目标/行为：周期采样服务、备份、任务和媒体磁盘，按 10%/5%/2% 阈值生成告警和创建门禁；容量恢复后自动解除门禁，不发送恢复邮件。
- 来源：`data/05-storage-lifecycle.md` §磁盘保护；`modules/09-notifications-observability.md` §容量/告警；`architecture/04-operations-testing.md` §监控；DEC-002。
- 依赖：前置 `OBS-007`、`OBS-006`、`OBS-009`、`RUN-004`；后续 `EXC-006`、`QA-001`、`QA-003`、`QA-004`、`QA-006`。
- 文件：`apps/operations/capacity/`、周期任务、告警状态查询、阈值测试。
- 边界：不重新定义 CapacityPolicy，不阻止既有内容读取，不让前端按钮代替服务端门禁；生产邮件仍由 OBS-009 处理。
- 影响：数据：CapacityState/告警；权限：全写服务读取门禁；审计：阈值状态变化；缓存：小时去重；异步：周期采样；媒体：5%/2% 门禁；通知：站内告警和运维失败事件。
- 测试/验收：RED 10/5/2% 上下穿越、采样重复、服务失败/恢复、错误日志最低写通道；隔离 Worker 与 DB/通知读回。
- 风险/停止：采样错误路径、告警阻断审计/错误、容量恢复需人工解锁时停止部署准备。
- 授权：代码/模拟 `否`；真实告警邮件和生产门禁 `是`。

[返回总索引](../implementation-todolist.md)
