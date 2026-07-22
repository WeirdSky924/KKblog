# P7 评论、留言、举报与申诉（11）

退出门禁：评论、留言板、缓冲、树、删除、举报、申诉和案件状态均委托唯一领域服务。

### CMT-001 建立文章/留言板共用讨论线程与评论树 schema
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P0。
- 目标/行为：每篇文章一个线程、全站一个留言板线程；Comment 保存 parent/root/depth、author kind、BUFFERED/VISIBLE/DELETED、visible_at、reply_count、受限 IP。
- 来源：访谈 Q006-Q015、Q107-Q110、Q240；`data/03-interaction-operations-fields.md` §DiscussionThread/Comment；`flows/03-comment-moderation-state-machine.md`。
- 依赖：前置 `CNT-005`、`ACC-001`、`FND-006`；后续 `CMT-002`、`CMT-003`、`CMT-005`、`CMT-006`、`CMT-007`、`QA-001`、`QA-006`。
- 文件：`apps/comments/models/`、target registry、migrations、queries/services skeleton/tests。
- 边界：target 仅ARTICLE/GUESTBOOK；parent同线程、depth≥0；账户删除改DELETED_ACCOUNT而非删正文；不建第二套留言模型。
- 影响：数据：Thread/Comment约束；权限：owner/target策略；审计后续；缓存无；异步/媒体/通知后续。
- 测试/验收：RED 目标唯一、跨线程parent拒绝、author kind、账户SET NULL；migration和真实DB读回。
- 风险/停止：任意target字符串、树级联错误或账户删除物理删历史评论即停止。
- 授权：schema/隔离 migration `否`；生产 migration `是`。

### CMT-002 实现顶层评论、权限、冷却、缓冲与图片
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P0。
- 目标/行为：文章/留言允许时，访客无需身份可发顶层且显示“访客”，登录用户可发；正文≤100字、最多3图；访客5分钟、用户1分钟；所有评论缓冲10分钟。
- 来源：访谈 Q008-Q010、Q111-Q116、Q119、Q191、Q230、Q292；`flows/03-comment-moderation-state-machine.md` §评论提交/创建权限。
- 依赖：前置 `CMT-001`、`ACC-010`、`MED-003`；后续 `CMT-004`、`CMT-006`、`CMT-007`、`CMT-008`、`QA-003`、`QA-006`。
- 文件：posting service/policy/forms/views、comment media binding、Redis cooldown/tests。
- 边界：被封IP只读公开内容；无CAPTCHA/日配额；回复不走本入口；管理员兼作者走标准登录用户/作者规则，不获得额外评论特权；缓冲完成前除本人/owner/admin外不可见。
- 影响：数据：BUFFERED评论/IP；权限：线程设置/IP；审计：安全事件；缓存：冷却Redis；异步：到期扫描；媒体：≤3；通知无。
- 测试/验收：RED 访客/用户权限、100字、0..3/4图、5m/1m、10m、重复提交；Playwright提交后本人状态/他人不可见。
- 风险/停止：冷却只在前端、缓冲评论提前公开、图片绑定失败仍建评论或IP泄露列表即停止。
- 授权：`否`。

### CMT-003 实现登录回复、无限深度与深层一次告警
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P0。
- 目标/行为：仅登录用户可回复非删除节点，回复无图；计算root/depth并原子增加顶层reply_count；depth>100向文章作者/留言板管理员只通知一次。
- 来源：访谈 Q011-Q012、Q108、Q119、Q191、Q259-Q260、Q313；`modules/06-interactions-moderation.md` §评论聚合/排序。
- 依赖：前置 `CMT-001`、`ACC-005`、`FND-005`、`OBS-001`；后续 `CMT-005`、`CMT-007`、`QA-003`、`QA-006`。
- 文件：reply service/locks/deep-thread event、profile link presenter/tests。
- 边界：不限制业务深度、不允许访客回复/回复删除节点/回复带图；提醒按线程阈值只一次。
- 影响：数据：parent/root/depth/reply_count；权限：登录/目标；审计无；缓存无；异步：outbox；媒体禁止；通知：深层告警。
- 测试/验收：RED 并发回复计数、100→101阈值、重复事件、删除parent、账户主页链接；DB锁读回。
- 风险/停止：递归查询栈溢出、计数漂移或每级重复通知即停止。
- 授权：`否`。

### CMT-004 实现缓冲公开任务与评论关闭语义
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P0。
- 目标/行为：每分钟小批量领取到期 BUFFERED 并条件更新为VISIBLE；作者关闭评论只阻止新建，已缓冲仍按时公开，删除状态永不公开。
- 来源：访谈 Q009-Q013、Q224；`contracts/05-background-tasks.md` §评论公开扫描；`flows/03-comment-moderation-state-machine.md`。
- 依赖：前置 `CMT-002`、`RUN-002`、`OBS-006`；后续 `CMT-007`、`AUT-006`、`QA-003`、`QA-004`、`QA-006`。
- 文件：publication service/task/Beat schedule、thread settings bridge、TaskRun tests。
- 边界：不依赖每条ETA；任务不复制ORM规则；关闭不隐藏既有评论；失败不能提前公开。
- 影响：数据：条件状态转换；权限：owner配置；审计：设置变更按owner语义；缓存无；异步：Celery；媒体无；通知：终败后。
- 测试/验收：RED 双Worker、关闭后到期、缓冲期删除、漏tick补偿；真实 Worker/DB/TaskRun 读回，三次失败事实事件由 `OBS-009` 回归。
- 风险/停止：重复公开、副作用先于状态或关闭误删/隐藏历史即停止。
- 授权：代码/隔离worker `否`；运行真实Beat `是`。

### CMT-005 实现评论排序、游标加载与回复分批展开
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P1。
- 目标/行为：顶层/回复默认最早；可选最新、最热门按reply_count；顶层先20触底再20，回复链先10再10；排序偏好仅当前浏览器。
- 来源：访谈 Q259-Q261；`data/04-indexes-constraints.md` §评论索引；`contracts/03-frontend-contract-map.md` §article detail。
- 依赖：前置 `CMT-001`、`CMT-003`；后续 `CMT-007`、`AUT-006`、`QA-003`、`QA-006`。
- 文件：public thread queries/cursors/HTMX partials/browser preference JS/tests。
- 边界：游标用稳定二级键；不把排序偏好同步账户；删除占位保持树位置；无限加载不可重复/漏项。
- 影响：数据：索引/只读投影；权限：评论可见设置；缓存：浏览器偏好；审计/异步/媒体/通知无。
- 测试/验收：RED 20/40、10/20、并发插入游标、热门并列、删除节点；Playwright滚动/展开/切排序/移动端。
- 风险/停止：OFFSET导致重复漏项、深树一次全加载或偏好串用户即停止。
- 授权：`否`。

### CMT-006 实现自删、作者管理删与管理员直接删除
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P0。
- 目标/行为：用户可删自己、文章作者可删自己文章任意评论、管理员可直接删全站/留言板；全部保留占位和子回复、立即删图；管理员可填原因且终局无申诉并通知相关注册用户去重。
- 来源：访谈 Q009、Q107-Q110、Q116、Q308-Q310；`modules/06-interactions-moderation.md` §管理员直接删除。
- 依赖：前置 `CMT-001`、`CMT-002`、`MED-006`、`FND-005`、`OBS-004`、`OBS-006`；后续 `CMT-009`、`AUT-006`、`ADM-004`、`QA-003`、`QA-006`。
- 文件：deletion services/policies/events、placeholder presenter、media cleanup port/tests。
- 边界：评论永不编辑；删除节点不可新回复；访客无自删入口；管理员删除不走举报申诉；审计不复制全文。
- 影响：数据：DELETED/清空body/原因；权限：self/owner/admin；审计：admin写；缓存无；异步：媒体清理/outbox；媒体：立即解绑；通知：作者/评论者去重。
- 测试/验收：RED 各角色伪造删除、子回复保留、图片缺失重试、接收者集合去重；Playwright 确认/原因/无申诉，最终 Receipt 由 `OBS-008` 回归。
- 风险/停止：删除物理移除节点、正文进入审计、访客被尝试通知或媒体先删后回滚即停止。
- 授权：`否`；生产管理员删除具体内容 `是`。

### CMT-007 实现管理员拥有的留言板与全部评论规则复用
- 元数据：状态 `待处理`；阶段 P7；owner `comments`；优先级 P1。
- 目标/行为：公开留言板默认开启且访客可顶层留言；管理员控制开启/登录要求、管理评论并接收深层提醒；回复、图片、排序、举报、占位全部复用。
- 来源：访谈 Q237、Q240、Q312-Q313；`modules/06-interactions-moderation.md` §留言板；`contracts/03-frontend-contract-map.md` §public:guestbook。
- 依赖：前置 `CMT-001`、`CMT-002`、`CMT-003`、`CMT-004`、`CMT-005`、`OBS-004`；后续 `ADM-007`、`QA-003`、`QA-006`。
- 文件：guestbook target adapter/settings bridge/page templates/queries/tests。
- 边界：不建GuestbookComment；无独立作者；关闭只阻止新建；访客规则与文章完全一致。
- 影响：数据：单Thread/设置投影；权限：admin owner/访客；审计：设置；缓存无；异步：缓冲；媒体：评论图；通知：深层/审核。
- 测试/验收：RED 默认/关闭/登录要求、管理员owner、完整举报复用；Playwright访客留言→10m→用户回复/举报。
- 风险/停止：出现第二套模型/审核逻辑或留言板无owner导致任务/通知丢失即停止。
- 授权：`否`。

### CMT-008 实现举报提交、理由、证据与隐私边界
- 元数据：状态 `待处理`；阶段 P7；owner `moderation`；优先级 P0。
- 目标/行为：登录用户每目标仅一次举报，必选六类理由，可选200字和≤3张2MiB证据；访客禁止；被举报方任何表面不见举报人身份。
- 来源：访谈 Q117-Q125；`data/03-interaction-operations-fields.md` §Report；`contracts/02-authorization-matrix.md` §举报。
- 依赖：前置 `CMT-002`、`MED-003`、`ACC-005`；后续 `CMT-009`、`CMT-010`、`ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：`apps/moderation/models/report.py`、report service/policy/forms/private evidence query/tests。
- 边界：理由用注册枚举，不允许任意HTML；证据严格私有；撤回不能绕过唯一举报；普通列表掩码IP/身份。
- 影响：数据：Report/证据绑定；权限：登录/一次/私有；审计：admin裁决后；缓存无；异步无；媒体：私有证据；通知后续。
- 测试/验收：RED 重复举报、访客、200/3边界、他人证据URL、payload泄露；Playwright举报弹窗/字段错误/成功。
- 风险/停止：举报人ID进入通知/页面/导出、证据公开或唯一只靠表单即停止。
- 授权：`否`。

### CMT-009 实现举报初审、对外删除与可恢复私有快照
- 元数据：状态 `待处理`；阶段 P7；owner `moderation`；优先级 P0。
- 目标/行为：管理员判成立则评论对外占位并通知双方，驳回只通知举报人；为一次申诉在审核域保存受限恢复快照，终局前可恢复。
- 来源：访谈 Q117-Q122；`flows/03-comment-moderation-state-machine.md` §举报初审/裁决；`reference/01-requirements-resolution.md` §评论申诉。
- 依赖：前置 `CMT-006`、`CMT-008`、`FND-005`、`OBS-004`；后续 `CMT-010`、`CMT-011`、`ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：review service/state machine/private snapshot/events/audit schema/tests。
- 边界：公开comments表只占位；快照不进审计/事件；成立通知不暴露reporter；非法状态不能重复裁决。
- 影响：数据：Report状态/私有快照/Comment占位；权限：admin；审计：裁决；缓存无；异步：outbox；媒体：证据保留；通知：双方/举报人。
- 测试/验收：RED 重复管理员请求仅一次、成立/驳回事实事件、快照访问、审计同事务回滚；DB/页面/Outbox 读回，通知 Receipt 由 `OBS-008` 回归。
- 风险/停止：初审即销毁无法申诉恢复、快照对外可读或通知泄露举报人即停止。
- 授权：`否`；生产裁决具体举报 `是`。

### CMT-010 实现一次申诉、终局复审与快照销毁/恢复
- 元数据：状态 `待处理`；阶段 P7；owner `moderation`；优先级 P0。
- 目标/行为：初审失败仅举报人可申诉一次，成立仅被举报账户可申诉一次；200字/3图；管理员复审终局，成立保持/执行删除，失败恢复可恢复内容并通知双方。
- 来源：访谈 Q120-Q125；`flows/03-comment-moderation-state-machine.md` §状态/副作用；`data/03-interaction-operations-fields.md` §ReportAppeal。
- 依赖：前置 `CMT-008`、`CMT-009`、`OBS-004`；后续 `ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：appeal model/service/policy/final review/private snapshot cleanup/tests。
- 边界：无二次申诉；产品未设截止期，首版不自动过期；恢复失败保留占位并写错误；案件元数据永久。
- 影响：数据：Appeal/终局状态；权限：结果对应一方/admin；审计：复审；异步：outbox/清理；媒体：申诉证据；通知：双方；缓存无。
- 测试/验收：RED eligibility、一次、无期限、终局重复、恢复/无法恢复；直接 URL 证据权限与事件 payload 隐私，最终通知由 `OBS-008` 回归。
- 风险/停止：状态可逆越过终局、错误方可申诉或快照终局成立后仍留正文即停止。
- 授权：`否`；生产复审 `是`。

### CMT-011 实现管理员文章案件/申诉及删除账户关联案件收敛
- 元数据：状态 `待处理`；阶段 P7；owner `moderation`；优先级 P0。
- 目标/行为：管理员隐藏/删除他人文章可填原因并通知/审计；作者一次200字/3图申诉，复审终局；准许恢复前状态。删除举报人/被举报人时按规则关闭并永久留管理员记录。
- 来源：访谈 Q284、Q287、Q302-Q307、Q311、Q315；`data/03-interaction-operations-fields.md` §ArticleCase/Appeal；`contracts/02-authorization-matrix.md`。
- 依赖：前置 `CNT-005`、`CNT-008`、`ACC-011`、`CMT-009`、`OBS-004`；后续 `OBS-008`、`EXC-004`、`ADM-004`、`QA-002`、`QA-003`、`QA-006`。
- 文件：article case/appeal services/policies/events、account deletion consumers、queries/tests。
- 边界：moderation 不直接改Article私有字段；管理员不能编辑/发布/转移；仅管理员主动恢复隐藏，申诉准许委托content；删除案件记录不级联。
- 影响：数据：Case/Appeal/身份快照；权限：admin/受影响作者；审计：永久；缓存：content事件失效；异步：outbox；媒体：证据；通知：动作/结果。
- 测试/验收：RED 隐藏仅已发布、一次申诉、前状态恢复、删除账户关闭报告、重复事件；四身份伪造POST+DB读回。
- 风险/停止：案件与文章状态分叉、管理员权限扩大或账户删除清除追踪身份即停止。
- 授权：`否`；生产隐藏/删除/裁决 `是`。

[返回总索引](../implementation-todolist.md)
