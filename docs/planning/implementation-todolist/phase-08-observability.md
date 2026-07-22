# P8 通知与可观测性集成（6）

退出门禁：领域通知、浮层/通知页、错误检索、任务最终失败和容量告警均真实读回。

### OBS-005 实现 RuntimeError、trace 聚合与管理员错误检索
- 元数据：状态 `待处理`；阶段 P8；owner `operations`；优先级 P0。
- 目标/行为：未预期异常脱敏后永久保存并按fingerprint聚合次数/首末时间；用户见通用文案+trace，管理员按trace/错误码/关键字/时间查详情。
- 来源：访谈 Q199-Q203；`modules/09-notifications-observability.md` §运行错误；`contracts/04-events-errors.md` §Trace/脱敏。
- 依赖：前置 `FND-004`、`OBS-004`；后续 `OBS-009`、`ADM-008`、`QA-001`、`QA-003`、`QA-006`。
- 文件：RuntimeError model/service/redaction/fingerprint/query、handler sink/admin UI/tests。
- 边界：不得保存密码/码/token/Cookie/Authorization/.env/正文/原上传；记录失败仅向stderr写最小安全诊断。
- 影响：数据：永久错误记录；权限：admin；审计：查看不审计；缓存无；异步：任务错误关联；媒体无；通知仅终败。
- 测试/验收：注入全类秘密并验证页面/DB/stderr；相同fingerprint聚合、trace不存在诚实空态；Playwright用户/管理员两面。
- 风险/停止：任一sink泄密、错误记录递归崩溃或用户可读取堆栈即停止。
- 授权：`否`。

### OBS-008 完成领域事件模板、通知去重与集成回执
- 元数据：状态 `待处理`；阶段 P8；owner `notifications`；优先级 P0。
- 目标/行为：在通知基础表和 Outbox 就绪后，为账户、内容、评论和审核事件注册版本化安全模板；同一事件按接收者和业务日去重，并可从事件到 Receipt 读回。
- 来源：`contracts/04-events-errors.md` §事件注册表/通知模板安全；`modules/09-notifications-observability.md` §通知事件；`reference/01-requirements-resolution.md` §通知口径。
- 依赖：前置 `OBS-001`、`FND-005`、`ACC-011`、`CNT-011`、`CMT-011`；后续 `OBS-002`、`OBS-003`、`OBS-009`、`EXC-003`、`EXC-005`、`QA-003`、`QA-004`、`QA-006`。
- 文件：`apps/notifications/templates/`、事件消费者注册表、dedupe/receipt 集成测试。
- 边界：不创建第二通知模型，不允许业务模块直接拼文案；payload 不含正文、举报人、秘密、原始 IP 或文件路径；P9 的导入导出模板必须复用本任务注册端口扩展，不在 P8 预实现 Exchange；不代替通知基础存储。
- 影响：数据：模板版本、Receipt、dedupe；权限：按接收者重判；审计：管理员通知动作沿用 OBS-004；缓存无；异步：Outbox 消费；媒体无；通知：领域通知真实投递。
- 测试/验收：RED 重复事件、兼任角色、同文章/上海日聚合、模板未知字段、账户删除收件；真实 Outbox 消费后 DB 通知与 Receipt 读回。
- 风险/停止：模板字段未注册、重复或泄露敏感 payload、消费成功但 Receipt 缺失时停止所有通知 UI 集成。
- 授权：`否`；生产群发和真实外发邮件仍按 OBS-003/OBS-009 授权。

### OBS-002 实现通知浮层、完整 overlay、通知页与已读
- 元数据：状态 `待处理`；阶段 P8；owner `notifications`；优先级 P1。
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
