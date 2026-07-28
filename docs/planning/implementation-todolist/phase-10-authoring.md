# P10 作者工作台（6）

退出门禁：作者工作台所有编辑、草稿、冲突、审查、版本、评论和导入流均可操作。

### AUT-001 实现作者工作台入口、文章状态列表与权限能力
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P1。
- 目标/行为：作者从个人菜单进入“我的文章”，查看已发布/草稿/定时/删除冷静期及空态；只显示本人可执行动作，撤销作者后既有文章可读但不能继续作者命令。
- 来源：访谈 Q002、Q104、Q233-Q235、Q285；`modules/07-authoring-workbench.md` §UI状态；原型 authorlist/editor。
- 依赖：前置 `CNT-002`、`CNT-004`、`CNT-008`、`ACC-011`、`DSC-006`；后续 `AUT-002`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：authoring article workspace query/presenter/views/templates/nav/tests。
- 边界：authoring不建Article/Draft表；capability来自content/account policy，提交时重判；无空管理员仪表盘。
- 影响：数据：只读文章/角色；权限：作者/本人；审计无；缓存无；异步状态只读；媒体封面；通知入口。
- 测试/验收：Playwright普通用户直接URL拒绝、作者四tabs/空态、撤销角色后按钮与伪造POST；1440/390。
- 风险/停止：UI隐藏代替服务授权、列表漏冷静期或作者入口拥有第二套状态判断即停止。
- 授权：`否`。
- 证据：聚焦 RED `pytest apps/authoring/tests/test_aut001.py -q` 首次退出 2，准确报告 content 的作者列表公开契约缺失；content owner 随后新增本人四状态分页、计数和 capability DTO，authoring 只做展示编排，个人菜单与 view/content query 双重重判角色。聚焦 GREEN 退出 0、`4 passed`；AUT-001、CNT-002/004/008、ACC-011 与架构联合回归退出 0、`36 passed`，Ruff lint/format、Django check、migration drift、npm build 与 `git diff --check` 均退出 0。隔离 PostgreSQL 读回本人已发布/草稿/定时/冷静期各 1、他人文章 0，撤销作者角色后公开文章仍可读而同一浏览器会话工作台立即 403。`blog-playwright-cli` 由 `blog-browser` 运行，读回访客登录回跳、普通用户 403、作者四 tabs 的真实 HTMX URL/内容、空态与角色撤销；390px 浅色/深色/护眼和 1440px 护眼原尺寸截图位于 `output/playwright/p10-aut001/`，390px 页面宽度读回 `390/390`，首个 Tab 聚焦跳转主要内容。未执行生产 migration、生产服务、提交、推送、部署或真实邮件。

### AUT-002 集成 Markdown/TipTap 编辑器与安全实时预览
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P0。
- 目标/行为：新建先选不可变格式；桌面编辑/预览并列，手机分段切换；共用标题/摘要/封面/可见性/分区/标签/评论设置/媒体；预览使用发布同一sanitizer。
- 来源：访谈 Q036-Q037、Q219-Q222、Q263、Q316；`modules/07-authoring-workbench.md` §编辑器；`03-frontend-design-system.md` §编辑器。
- 依赖：前置 `AUT-001`、`MED-005`、`MED-007`、`CNT-002`；后续 `AUT-003`、`AUT-004`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：editor views/templates、TipTap bridge、Markdown input/preview、shared controls、JS/tests。
- 边界：不混合格式、不执行原HTML、不建立SPA；手机键盘不遮保存/发布；正文计数不含图片。
- 影响：数据：snapshot DTO；权限：author；审计无；缓存：预览不复用不安全缓存；异步无；媒体：picker；通知无。
- 测试/验收：组件RED两格式序列化/预览等价/XSS；Playwright桌面/手机输入、媒体、长文、错误、键盘/焦点。
- 风险/停止：预览与发布规则分叉、编辑器状态丢失或手机隐藏预览后不可切回即停止。
- 授权：`否`。
- 证据：组件 RED `pytest apps/authoring/tests/test_aut002.py -q` 首次退出 2，准确报告 content 缺少 `preview_article_body` 公开契约；实现后聚焦 GREEN 退出 0、`5 passed`，AUT-002、CNT-002/007、MED-003/004/005 与架构联合回归退出 0、`36 passed`。content preview DTO 对 Markdown/TipTap 调用发布同一 renderer/sanitizer，组件读回 HTML 与发布 renderer 完全一致、脚本/事件/危险 scheme 消失，图片 1 张但正文计数不含图片；新建格式写入首修订，普通编辑由 form 与 content 双重拒绝切换。隔离 PostgreSQL 读回 Markdown `row_version=2/sequence=2`、同一正文图片分别绑定两个不可变修订，TipTap 保存为 JSON object、文本“富文本正文”及 `bold` mark。`blog-playwright-cli` 由 `blog-browser` 运行，完成 Markdown/TipTap 输入、工具栏、正文图片上传插入、实时预览、创建/二次保存、2 MiB 长文 422、390 编辑/预览双向切换、三主题和 768/1440 截图；390 读回 `viewportWidth=390/scrollWidth=390`，正文聚焦时保存栏 `sticky` 且 `bottom=709 < visualViewportHeight=844`，未聚焦不遮挡页面。截图位于 `output/playwright/p10-aut002/`。Ruff lint/format、Django check、migration drift、npm build、秘密模式和 `git diff --check` 均退出 0；未执行生产 migration、生产服务、提交、推送、部署或真实邮件。

### AUT-003 实现浏览器本地自动保存、显式云草稿与恢复
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P0。
- 目标/行为：内容变化debounce写本地键(user/article/base/format)；仅点击保存写云Revision；恢复先本地否则自动云稿；发布、删云稿、清浏览器数据时按规则清本地。
- 来源：访谈 Q262、Q297；`modules/07-authoring-workbench.md` §本地与云草稿；`contracts/03-frontend-contract-map.md` §本地键。
- 依赖：前置 `AUT-002`、`CNT-002`；后续 `AUT-004`、`AUT-005`、`QA-003`、`QA-006`。
- 文件：local draft JS/storage contract、cloud save HTMX、status presenter/tests。
- 边界：不把本地稿同步账户/服务器；请求失败/崩溃不得删；管理员查看他人工作修订不取得本地稿。
- 影响：数据：浏览器草稿/云Revision；权限：user/article隔离；审计无；缓存：localStorage/IndexedDB；异步：debounce仅本地；媒体：未绑定暂存；通知无。
- 测试/验收：Playwright模拟断网/崩溃/多账户/同文章多基线、本地优先/云回退、成功发布清理；DB读回显式保存。
- 风险/停止：键过粗串稿、保存失败删除本地或UI虚报已云保存即停止。
- 授权：`否`。
- 证据：初始 RED `pytest apps/authoring/tests/test_aut003.py -q` 收集期退出 2，准确报告云草稿删除契约缺失；实现本地键 `user/article/base revision/format`、500ms debounce、本地优先/云 working revision 回退、显式云保存 pending/失败保留，以及 content owner 下的无冷静期云草稿删除。聚焦 GREEN `5 passed`，AUT-003、CNT-002/003/006/008 与架构联合回归 `32 passed`；首发前删除事务内物理清理 Article/全部 Revision/评论/媒体引用，已发布文章仅把 working pointer 恢复到 published pointer并保留完整历史，错误作者、禁用作者、遮罩、排期、未解冲突和 stale row version 均关闭失败。隔离浏览器完成断网/崩溃、跨账户、同文章多基线、本地优先/云回退、云保存失败保留、确认取消/焦点恢复和手动删云稿；PostgreSQL 与浏览器读回删除后 Article/Revision 为 `0|0`、文章全部本地基线键和 pending marker 均清空。收口审计先以真实创建/保存流 RED 读回显式云保存错误删除本地键，修复为只确认并清除 session pending marker 后，全新浏览器 GREEN 读回旧基线 localStorage 键仍存在、pending marker 已清；随后手动删云稿再次读回本地键为空、数据库 `0|0`。390/768/1440、三主题、成功态焦点和无横向溢出已验证；Ruff、format、Django check、migration drift、npm build 与 `git diff --check` 退出 0。成功发布由 AUT-005 的真实入口发出同一 `kaj:author-draft-clear` 事件；AUT-005 和 P10 最终审计必须重新读回发布后全部本地基线键清空，否则阶段不得完成。未执行生产 migration、生产数据/媒体、部署、真实邮件或本轮 Git 交付。

### AUT-004 实现 409 冲突冻结与版本基线选择界面
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P0。
- 目标/行为：保存冲突后禁止继续保存/发布，展示当前工作版、用户基线和历史元数据；作者选一版覆盖编辑画布并取得新令牌，未发布本地输入可明确保留/比较。
- 来源：访谈 Q296；`modules/07-authoring-workbench.md` §并发冲突；`contracts/03-frontend-contract-map.md` §HTMX 409。
- 依赖：前置 `CNT-006`、`AUT-002`、`AUT-003`；后续 `AUT-005`、`QA-003`、`QA-006`。
- 文件：conflict partial/modal/presenter/editor token bridge、tests。
- 边界：不静默合并/覆盖；冲突不改线上版本；409不得被全局toast吞；版本详情不泄露他人对象。
- 影响：数据：无写至确认/新令牌；权限：作者；审计无；缓存本地稿；异步/媒体/通知无。
- 测试/验收：两浏览器Playwright并发保存→一成功一409→选基线→继续；取消/刷新/已发布读者版稳定。
- 风险/停止：冲突后按钮仍可提交、选择版本丢本地稿无提示或published被覆盖即停止。
- 授权：`否`。
- 证据：临时聚焦 RED `pytest apps/authoring/tests/test_aut004.py -q` 在缺少 authoring 冲突恢复入口和展示契约时退出 1；实现 conflict grant 恢复、版本元数据 presenter、409 partial、编辑区冻结、明确的本地稿保留选择和基线令牌桥接后，AUT-004 四用例与 CNT-006 三用例组合 GREEN 退出 0，`7 passed`。本次新鲜复核中，CNT-006 聚焦退出 0，`3 passed`；CNT-002/003/004/006/007 相关回归退出 0，`29 passed`；目标 Ruff lint/format、Django check、migration drift、完整前端 build 与 `git diff --check` 均退出 0。隔离 PostgreSQL 读回修订数 4、`row_version=4`、working 版本 4、published 版本 1、未解决 conflict grant 为 0；选择版本 1 的 HTMX 响应显示“已选择版本 1”、画布加载“读者稳定版本”且保存恢复可用，刷新安全回到当前云 working revision。真实文章页继续读回“读者稳定版本”，证明选择基线未移动发布指针。`blog-playwright-cli` 由 `blog-browser` 运行，重新核验 390 护眼、768 深色、1440 浅色原尺寸截图无重叠、裁切或横向溢出，冲突区自动聚焦、编辑/保存冻结、键盘可达且 Lucide 图标完整；专用浏览器与 runserver 已关闭，回归数据库不存在、Redis DB 15 为 0。未执行生产 migration、生产数据、部署、真实邮件或本轮 Git 交付。

### AUT-005 实现终稿审查、立即/定时发布与版本时间线 UI
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P0。
- 目标/行为：完整文章审查可返回编辑；确认必选立即或定时；关闭未确认保留草稿；版本时间线可预览/恢复并再次审查；自动重发偏好仅用于已发布普通编辑。
- 来源：访谈 Q050-Q053、Q263-Q264、Q298；`modules/07-authoring-workbench.md` §发布审查；原型 editor/authorlist。
- 依赖：前置 `AUT-001`、`AUT-002`、`AUT-003`、`AUT-004`、`CNT-003`、`CNT-004`、`CNT-007`；后续 `QA-003`、`QA-006`。
- 文件：review/versions views/presenters/templates/forms、schedule picker/tests。
- 边界：实时预览不等于终稿审查；首次/恢复不能绕审查；失败保留输入；异步排期只显示真实状态。
- 影响：数据：发布/排期/恢复服务结果；权限：作者；审计版本元数据；缓存：发布失效；异步：排期；媒体：完整预览；通知无。
- 测试/验收：Playwright返回编辑/关闭/立即/排期/恢复/自动重发，读者并行验证旧版到确认前不变；390/1440。
- 风险/停止：审查令牌可重放、退出丢稿、排期时区错或UI在Job前显示发布完成即停止。
- 授权：`否`。
- 证据：真实浏览器 RED 先读回排期 422 被重置为“立即发布”、错误字段未聚焦，且 UTC `2099-07-30 01:30` 被列表/回执错误展示；修复后临时聚焦 `pytest apps/authoring/tests/test_aut005.py -q` 退出 0、`2 passed`，证明 422 保留定时选择、标记错误焦点及两个真实模板输出上海 `09:30/+08:00`，临时测试和 `__pycache__` 随后删除。CNT-003/004/007 与架构联合回归退出 0、`19 passed`；目标 Ruff lint/format、Django check、migration drift、npm build 与 `git diff --check` 均退出 0。`blog-playwright-cli` 由 `blog-browser` 完成返回编辑、未确认退出、立即发布、读者旧版稳定、版本元数据延迟加载、历史恢复创建新修订并再次审查、排期/取消和自动重发；恢复确认前读者仍见第三版，恢复发布后读者见第一版，自动重发后数据库为 `PUBLISHED|published_revision_id=working_revision_id|sequence=5` 且读者正文为“自动重发读者正文”。排期列表与成功回执显示 `2099-07-30 09:30/+08:00`，PostgreSQL 仍保存 UTC `01:30`，取消后状态回到 DRAFT 且排期字段为空。立即/自动发布均清除目标文章全部本地基线键和 pending marker，同时保留另一文章控制键。390 深色审查、768 护眼版本、1440 浅色创作偏好原尺寸截图位于 `output/playwright/p10-aut005/`；三视口页面宽度等于视口、Lucide 残留 0、跳到主内容焦点正确、控制台 0 error/0 warning。全仓 Ruff 仍准确报告基线已有的 `apps/comments/tests/test_cmt004.py` 导入顺序问题，该文件无本轮差异且按测试文件交付规则未修改；AUT-005 隔离 PostgreSQL 两库已定向删除，专用 Redis DB 15 从 3 键清至 0。未执行生产 migration、生产服务、部署、真实邮件或本轮 Git 交付。

### AUT-006 实现作者评论管理与导入编排页面
- 元数据：状态 `完成`；阶段 P10；owner `authoring`；优先级 P1。
- 目标/行为：评论管理首版只有“10分钟缓冲卡片”和“按文章”两tabs，可关闭评论/删除；导入页面完成上传、逐项预览/选择/映射/结果编排。
- 来源：访谈 Q105-Q106、Q262、Q275-Q280；`modules/07-authoring-workbench.md` §作者评论/导入；原型 authorops。
- 依赖：前置 `CMT-004`、`CMT-005`、`CMT-006`、`EXC-001`、`EXC-002`、`EXC-003`；后续 `QA-003`、`QA-006`。
- 文件：comment workspace queries/views/templates、import views/presenters/partials/tests。
- 边界：不显示空的未来tab；authoring不写评论/ImportJob/Article私表；所有命令委托owner。
- 影响：数据：只读/委托；权限：本人文章/导入作者；审计：导入结果owner负责；缓存无；异步：ImportJob；媒体：导入包；通知：结果状态。
- 测试/验收：Playwright缓冲倒计时/按文章/删除确认/关闭；混合导入预览→部分成功结果，桌面/手机。
- 风险/停止：管理页复制领域逻辑、导入预览直接写文章或响应假完成即停止。
- 授权：`否`。
- 证据：初始聚焦 RED `pytest apps/authoring/tests/test_aut006.py -q` 为 `2 failed, 2 passed`，准确报告评论管理 URL 缺失和导入表单错误读取分区 DTO；实现 comments owner 的本人文章工作区、发布修订级评论设置同步和 article/comment 双目标删除后，authoring 仅编排公开 query/service，评论页只保留“10 分钟缓冲/按文章”两 tabs，并闭合真实倒计时、评论树、顶层/回复游标分页、关闭开关、删除确认与占位。导入页只调用 `config.exchange_integrations`，上传 `.md/.zip` 后预览不写 Article/Tag/正式媒体，逐项支持 include、SKIP/UPDATE/CREATE、分区、已有标签和新标签映射；确认后先显示真实 `PROCESSING`，再由 `apps.exchange.process_import_job` 进入 `COMPLETED/PARTIAL/FAILED`。聚焦 GREEN 与最终复核均为 `7 passed`；浏览器发现预览总计误显示 0 和安全失败原因过于笼统后，新增 RED 准确失败，修复 Django filter 链及 `content.snapshot_invalid.v1` 文案后为 `1 passed`。相关回归：comments 全模块 `24 passed`、content 全模块 `68 passed`、架构/Outbox/任务入口 `20 passed`、TaskRun `11 passed`；目标 Ruff lint、format、Django check、migration drift、npm build 和 `git diff --check` 均退出 0。隔离 PostgreSQL 读回关闭评论后既有树与缓冲项不变，真实 `dispatch_due_comments -> publish_due_comment` 两级 Celery 任务均 `succeeded/attempt=1` 且缓冲评论最终为 `VISIBLE`；混合 ZIP 确认前作者 Article 数仍为 1，任务后为 `PARTIAL`、`success=1/skipped=1/failed=1`，成功文章关联“浏览器验收”分区、“已有标签”和“新增标签”，正式媒体目录为空，导入 TaskRun 同样 `succeeded/attempt=1`。`blog-playwright-cli` 由 `blog-browser` 运行，验证访客登录回跳、普通用户 403、他人文章/Job 隐私 404、倒计时递减、删除取消焦点恢复、两类 HTMX 加载更多、关闭后无新评论入口但缓冲到期公开、422 错误聚焦与有效上传恢复、真实 PROCESSING 和 PARTIAL 逐项结果；390 深色、768 护眼、1440 浅色页面宽度等于视口，skip link、switch 键盘操作、Lucide 未替换节点 0、成功路径控制台 0 error/0 warning。原尺寸截图位于 `output/playwright/p10-aut006/`。专用浏览器/服务/worker 已关闭，隔离数据库已删除，Redis DB 15 读回 0，临时目录已移入回收站，一次性测试和浏览器 settings 已删除。未执行生产 migration、生产服务、部署、真实邮件或本轮 Git 交付。

[返回总索引](../implementation-todolist.md)
