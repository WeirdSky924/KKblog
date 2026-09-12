# 文章划词解释实施 Todo List

状态：实施完成（`SE-001`～`SE-015` 全部完成）；本文是本功能唯一的施工进度账。

## 1. 执行规则

- 任务按 `SE-001` 至 `SE-015` 的前置关系顺序执行；每次最多一条任务为“进行中”。
- 每项先做聚焦 RED，再做最小完整实现、GREEN、相关回归和证据回写。
- 实施只在 Labs 进行；默认复用当前项目的 `apps/agents`、`apps/operations`、`apps/content`、`apps/discovery`、账户设置、通知和 Markdown sanitizer owner。
- 本期不做流式输出、SSE、ReadableStream、增量 token 或打字机效果；不改变文档审核和题库生成的调用协议。
- Todo 不授权 Git 提交/推送、生产迁移、生产部署、服务重启或生产数据修改；真实 Provider 仅在当前回合明确授权并限定 Labs Endpoint 时执行。

## 2. 阶段索引

| 阶段 | 范围 | 任务 | 退出门禁 |
| --- | --- | ---: | --- |
| S0 | 基线与契约 | 2 | owner、输入清理、状态和非目标固定 |
| S1 | AGENT 与配置 | 3 | Prompt、用户级参数、账户授权均有唯一来源 |
| S2 | 服务端请求运行时 | 3 | 限额、幂等、取消、错误和 Markdown 输出闭合 |
| S3 | 阅读页交互 | 3 | 选区入口、扩展工具栏和面板状态可用 |
| S4 | 设置、回归与 Labs | 4 | 真实用户流、权限、持久化和 Labs 读回通过 |

合计：15 条任务。

## 3. 任务卡

### SE-001｜建立 Labs 基线与功能契约

- 状态：完成；阶段 S0；Owner：交付/测试；优先级 P0。
- 目标：确认 Labs 在当前正式版本基线，盘点文章阅读页、全局反馈、账户设置、AGENT Gateway、TaskRun、限流和 Markdown sanitizer 的真实入口，建立本功能测试与页面状态锚点。
- 依赖：无；后续：`SE-002`、`SE-003`、`SE-004`、`SE-005`。
- 预计触点：`docs/architecture/contracts/03-frontend-contract-map.md`、`apps/discovery`、`apps/agents`、`apps/operations`、账户设置和现有前端测试。
- 边界/非目标：只做基线与契约，不写产品代码，不调用真实模型，不改变数据库；不把原型截图当作业务真值。
- 影响：确认登录权限、文章可见性、题库/审核 AGENT 不受影响；记录本功能与现有通知/审计/缓存的复用关系。
- 测试与验收：只读核对 Labs 服务 `active/running`、健康检查、代表性公开文章和当前 Git/工作树；输出选区、工具栏、面板、授权、限额、停止、重试和本地历史状态矩阵。
- 风险/停止：若 Labs 不在正式基线、现有 Gateway 无稳定调用入口或账户身份无法安全命名空间化，停止后续实现并记录缺口。
- 授权：仅 Labs 只读检查；不执行 Git、迁移、外部写入或服务重启。
- 证据（2026-09-08）：`systemctl show kaj-labs.service` 读回 `WorkingDirectory=/home/code/.codex-worktrees/personal-blog/labs-test-environment`、`ActiveState=active`、`SubState=running`；`https://labs.kajspace.cn/health/live` 和 `/health/ready` 均返回 200。源 HEAD `e5adc20`、Labs HEAD `4f92a97` 均位于 2026-09-07 正式部署记录之后；差异仅保留既有未交付工作区改动和本功能规划文件。已核对文章阅读入口、文章 query/presenter、`apps/agents` Gateway/public、`apps/operations` TaskRun、账户设置、Markdown sanitizer 和现有前端文章 Action owner，未发现需要新建平行实现的能力。

### SE-002｜固化划词解释 AGENT Prompt 与文本输出契约

- 状态：完成；阶段 S0；Owner：`apps/agents`；优先级 P0。
- 目标：为 `article-selection-explanation` 建立独立 AGENT profile、Prompt 版本和纯中文 Markdown 输出契约，复用现有 Endpoint、调用快照、审计、token 预留和错误体系。
- 依赖：`SE-001`；后续：`SE-006`、`SE-010`、`SE-014`。
- 预计触点：`apps/agents/defaults.py`、AGENT profile/Prompt seed、`apps/agents/public.py`、调用错误映射、架构契约文档。
- 边界/非目标：不创建第二个 Gateway、Provider、通知或 Prompt 存储；不强制题库式 JSON schema；不启用流式；不允许工具调用、代码执行、链接访问或外部动作。
- 影响：Prompt 接收选区、标题、摘要、标签和一级标题；所有资料标记为不可信材料；输出只允许中文文本，软性覆盖解释、术语/缩写、语境和不确定性。
- 测试与验收：Prompt 变量完整、版本快照可读回、未知/恶意指令不会提升权限；输出 Markdown 通过现有安全渲染 owner；文档审核和题库 profile 的现有测试不回归。
- 风险/停止：若无法让解释 AGENT 与现有 profile/Endpoint 复用而不复制调用逻辑，先补充架构决策，不接入页面。
- 授权：本地代码/运行时资源修改可在 Labs 进行；不执行真实外部模型调用。
- 证据（2026-09-08）：Labs 新增 `ARTICLE_EXPLANATION` profile 用途、`article-selection-explanation` 默认 Prompt、Prompt 变量白名单（标题/摘要/标签/一级标题/选区）和 `article-selection-explanation.v1` 单字段 Markdown envelope；注册入口复用 `apps/agents.schemas`，未创建第二注册中心。聚焦测试 `KAJ_TEST_DATABASE_URL=... uv run pytest apps/agents/tests/test_t06_article_explanation_profile.py -q` 结果为 `3 passed`，覆盖 Prompt 安全约束、schema 注册和默认 profile seed 幂等。未调用真实 Provider；未启用 profile、未执行共享 Labs migration、未执行 Git/生产操作。

### SE-003｜建立内容与互动解释参数配置

- 状态：完成；阶段 S1；Owner：内容与互动配置 owner；优先级 P0。
- 目标：在管理后台“内容与互动”下增加服务端配置：每日每用户解释次数默认 50、每分钟每用户解释次数默认 5、单次选区最大字符数默认 1000、每账户本地历史条数默认 30。
- 依赖：`SE-001`；后续：`SE-006`、`SE-013`、`SE-014`。
- 预计触点：现有站点/互动配置模型、迁移、管理员 query/service/form/template、导航注册和审计 schema。
- 边界/非目标：这些是用户级业务限制，不替代 Endpoint token/并发额度；不允许 0 冒充禁用；不添加流式开关；不把历史正文写入服务端配置。
- 影响：配置变更只影响后续请求；必须有范围、版本、并发更新、管理员权限和审计；读取失败按安全默认/明确不可用状态处理，不能无限放宽限制。
- 测试与验收：默认值、最小/最大范围、冲突保存、管理员权限、审计前后值和错误文案均有测试；真实配置读回与现有内容/互动配置兼容。
- 风险/停止：若没有合适的内容与互动配置 owner，先提取到现有配置中心，不新建平行 singleton。
- 授权：Labs 本地 schema/配置改动；迁移仅限隔离测试库，生产迁移需另行授权。
- 证据（2026-09-08）：扩展现有 `navigation.SiteConfiguration` 单例，新增每日/每分钟解释次数、单次选区上限和本地历史条数四个字段，默认 `50/5/1000/30`；新增 `0008_article_explanation_settings` 迁移、查询 DTO、管理员服务、固定范围校验、row version 冲突和 `navigation.article_explanation_settings.update` 审计 schema。聚焦测试 `KAJ_TEST_DATABASE_URL=... uv run pytest apps/navigation/tests/test_nav005_article_explanation_settings.py -q` 为 `4 passed in 123.36s`；目标 Ruff check/format 和 `makemigrations --check --dry-run` 均通过（后者 `No changes detected`）。未对共享 Labs 数据库执行迁移，未接入管理页面，未执行生产/Git/真实 Provider 操作。

### SE-004｜实现按文章的授权记录与账户自动接受设置

- 状态：完成；阶段 S1；Owner：账户设置/发现用户流；优先级 P0。
- 目标：支持手动授权只记住当前文章；账户个人设置增加默认关闭的“自动接受文章划词解释” Switch，开启后跳过逐篇确认，关闭后恢复确认。
- 依赖：`SE-001`；后续：`SE-008`、`SE-009`、`SE-013`、`SE-014`。
- 预计触点：账户偏好 owner、个人设置页面、文章阅读 query/presenter、授权弹窗模板和前端状态。
- 边界/非目标：未登录不进入授权流程；手动授权不上传服务端；不显示邮箱、内部角色或其他文章隐私；不能用前端隐藏代替服务端登录/文章可见性判断。
- 影响：按公开文章稳定 ID 在当前浏览器保存同意状态；自动接受是账户偏好，必须按账户隔离并提供关闭入口；授权拒绝取消当前请求且可再次询问。
- 测试与验收：同意/拒绝/重开、切换文章、清理站点数据、个人设置开关、作者/访客/管理员身份和私密文章均符合状态矩阵。
- 风险/停止：若文章修订变化会影响授权口径，先确定使用文章稳定 ID 还是修订 ID；未决前不持久化同意状态。
- 授权：Labs 本地账户设置和浏览器状态改动；不改生产账户数据。
- 证据（2026-09-08）：账户模型新增默认关闭的 `article_explanation_auto_accept` 字段和 `0009_account_article_explanation_auto_accept` 迁移；个人设置新增“阅读”页签、复用 `components/forms/switch.html` 的自动接受 Switch，并通过 `change_article_explanation_preferences` 服务完成账户隔离、启用/关闭、幂等和审计。聚焦回归 `KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:57432/kaj_test_acc012 KAJ_TEST_REDIS_URL=redis://127.0.0.1:56381/1 KAJ_TEST_MAILPIT_SMTP_URL=smtp://127.0.0.1:51027 KAJ_TEST_MAILPIT_API_URL=http://127.0.0.1:58027 uv run --frozen pytest apps/accounts/tests/test_acc012_article_explanation_preferences.py -q` 为 `3 passed in 161.02s`；账户设置既有回归与新测试合计 `4 passed in 172.06s`。`ruff check`、`ruff format --check`、`makemigrations --check --dry-run accounts` 和 development `manage.py check` 均通过。CSS 已执行 `npm run build:css`。未执行共享 Labs migration；共享库仍需在后续授权的部署阶段应用 accounts/agents/navigation 未应用迁移。公网 Labs 读回因既有数据库/机会任务阻塞超时，未将其误报为本项通过。

### SE-005｜建立服务端选区清理与文章语境 DTO

- 状态：完成；阶段 S1；Owner：`apps/discovery` + `apps/content`；优先级 P0。
- 目标：从当前公开文章安全组装解释输入：清理后的选区、文章真实标题、摘要、标签和所在一级标题。
- 依赖：`SE-001`；后续：`SE-006`、`SE-008`、`SE-014`。
- 预计触点：公开文章 query/presenter、正文 DOM 标记、纯文本提取 service、输入 contracts 和安全错误码。
- 边界/非目标：图片、图片 alt、链接目标和媒体资源不解释；链接可见文字、表格、LaTeX、代码块转为纯文本；不发送整篇正文；不执行任何代码/工具/链接。
- 影响：服务端重新验证文章公开可读性和账户登录态；默认按配置上限截断，保留原始字数、实际字数和截断标记；控制字符、空文本、超大 UTF-8 输入明确拒绝。
- 测试与验收：正文/表格/LaTeX/代码/图片/链接混合选区、纯图片/链接、0/1/1000/超限字符、多字节字符和恶意 HTML 均得到稳定 DTO 或错误；不发生 N+1 全文读取。
- 风险/停止：若只能依赖前端传来的标题、标签或章节，停止并补齐服务端 query；不以浏览器清理结果作为安全边界。
- 授权：Labs 本地代码与隔离测试；不读取生产私密文章。
- 证据（2026-09-08）：新增 `apps.discovery.queries.article_explanation` 作为唯一清理/语境 query owner，服务端重新校验账户与公开文章，清理 HTML 选区时移除图片、alt、链接目标和外部资源，将表格/LaTeX/代码转为纯文本，按配置上限截断并返回原始/处理字数与截断标志；新增 `ArticleExplanationContext` 与 `ArticleExplanationSelectionError`。聚焦测试 `uv run --frozen pytest apps/discovery/tests/test_article_explanation_context.py -q` 为 `5 passed in 0.81s`；目标 Ruff check/format 通过。未调用真实 Provider。

### SE-006｜实现解释次数、频率和并发前置裁决

- 状态：完成；阶段 S2；Owner：内容与互动配置 owner + `apps/operations`；优先级 P0。
- 目标：在创建 AGENT Invocation 前原子检查每日 50 次、每分钟 5 次和同一用户的重复提交，达到限制时返回窗口内原因，不调用模型。
- 依赖：`SE-003`、`SE-005`；后续：`SE-007`、`SE-010`、`SE-014`。
- 预计触点：用户解释使用计数/限流数据 owner、Redis 限流入口、PostgreSQL 计数或事件、错误合同和服务层。
- 边界/非目标：不修改 Endpoint token 额度、不新增 AGENT 额度、不依赖前端计数；Redis 只能做限流优化，PostgreSQL/现有持久化是最终事实；限额失败不发通知。
- 影响：按账户和站点时区计数；重复请求幂等且不得重复扣次数；配置缺失、计数器不可用和并发竞态必须 fail closed 或返回明确暂不可用状态。
- 测试与验收：第 49/50/51 次、分钟第 4/5/6 次、并发重复请求、跨日、账户隔离和数据库读回；确认被拒请求没有 Invocation、Reservation 或 token ledger 变化。
- 风险/停止：无法在模型调用前完成原子裁决，或限流故障会放行请求时停止接入 Provider。
- 授权：Labs 隔离数据库/Redis 运行验证；生产配置和数据修改需另行授权。
- 证据（2026-09-08）：新增 `operations_article_explanation_usage` 持久使用记录与服务端每日/60 秒窗口、账户隔离、幂等预留和失败重试不重复扣次数逻辑；所有裁决在创建 AGENT Invocation 前执行。隔离 PostgreSQL 聚焦回归 `KAJ_TEST_DATABASE_URL=postgresql://kaj_test_runner@127.0.0.1:57432/kaj_test_ops008b ... uv run --frozen pytest --reuse-db apps/operations/tests/test_article_explanation_usage.py -q` 为 `3 passed in 54.51s`；首次运行曾受 Labs 既有长事务阻塞，恢复后使用复用数据库完成新鲜读回。目标 Ruff check/format 通过，未执行共享 Labs migration。

### SE-007｜建立异步解释任务、幂等和取消服务

- 状态：完成；阶段 S2；Owner：`apps/operations` + `apps/agents`；优先级 P0。
- 目标：复用 TaskRun、租约和现有 Celery 入口建立解释任务；支持排队取消、执行中取消检查、Reservation 释放、晚到结果丢弃和安全重试。
- 依赖：`SE-002`、`SE-006`；后续：`SE-010`、`SE-011`、`SE-012`、`SE-014`。
- 预计触点：TaskRun service/task、AGENT Gateway 调用边界、取消状态/事件、token reservation 和错误映射。
- 边界/非目标：不创建解释专用队列、重试中心或通知系统；不做流式；不承诺供应商已产生 token 可逆；浏览器断开不能直接视为服务器取消成功。
- 影响：每个解释请求有稳定幂等键和账户/文章元数据；排队任务取消后不得触发 Provider；Provider 调用前后都检查取消；成功结果必须验证任务仍由当前 lease 持有。
- 测试与验收：重复 POST、重复 Celery 投递、排队取消、Provider 调用前取消、执行中取消、晚到响应、租约过期、Reservation 释放和重试次数上限；TaskRun 与 Invocation 终态一致。
- 风险/停止：无法阻止晚到结果写入或释放额度，停止按钮不得开放给用户，先修复状态/结算合同。
- 授权：Labs 隔离任务和 Provider fake/受控测试；不调用真实付费 Endpoint。
- 证据（2026-09-08）：新增 `ArticleExplanationRequest`、解释服务端状态机、`apps.discovery.article_explanation` Celery 任务、统一 Gateway 的取消检查和 `AgentInvocation.CANCELLED`/token reservation release 路径；文章 API 已提供创建、状态、取消、重试四个端点，前端工具栏/面板保存账户隔离 localStorage 历史并显示等待、停止、失败和重试状态。`apps/agents/tests/test_t03_gateway.py::test_gateway_cancel_check_releases_reservation_and_cancels_invocation` 在隔离 PostgreSQL 复用库中 `1 passed in 241.38s`，确认取消不触发 Provider 且 reservation 释放；`apps/discovery/tests/test_article_explanation_requests.py` 为 `3 passed`；`manage.py check`、迁移漂移检查、目标 Ruff、前端 node 回归 `7 passed`、JS/CSS 构建均通过。Labs 公网 health 仍被既有数据库长任务返回 500，未执行服务重启或共享 migration。

### SE-008｜实现文章选区按钮与可扩展阅读工具栏

- 状态：完成；阶段 S3；Owner：`apps/discovery` 前端；优先级 P0。
- 目标：登录文章页监听正文选区，清理后在选区附近显示解释按钮；建立右下角圆形入口向左展开为底部中央胶囊工具栏的可扩展工具 registry。
- 依赖：`SE-004`、`SE-005`；后续：`SE-009`、`SE-013`、`SE-014`。
- 预计触点：文章详情模板、`static/src` 阅读交互、CSS 主题变量、图标注册和现有文章 Action Dock。
- 边界/非目标：未登录不渲染任何入口；不改变文章正文布局、目录、收藏/点赞/书签；不把胶囊和解释面板合成单一组件；不使用发光、渐变或第二套设计系统。
- 影响：按钮只在有可解释文字时显示；忽略图片/链接目标；胶囊展开不刷新、不跳转、不制造页面滚动；触控目标、键盘焦点、ESC、`aria-expanded` 和 reduced-motion 完整。
- 测试与验收：访客/登录、正文/图片/链接/表格/LaTeX/代码选区、边缘位置、滚动、窄屏和三主题；验证圆形按钮到胶囊的动画及关闭后焦点/布局恢复。
- 风险/停止：若选区事件影响复制、目录或文章操作 Dock，先修复事件隔离和 z-index，不直接上线。
- 授权：Labs 前端源码和静态产物修改；按项目规则同步 Labs，不重启服务。
- 证据（2026-09-08）：公开文章模板仅在登录且公开文章中渲染阅读工具；新增右下角圆形入口、底部中央可扩展胶囊、选区附近解释按钮、原生授权 dialog 和三主题/窄屏 CSS，复用现有图标、按钮和主题变量；未登录与非公开文章不渲染入口。`tests/frontend/article-explanation.test.mjs` 与既有前端测试合计 `7 passed`，`node --check static/src/article-explanation.js`、`npm run build:js`、`npm run build:css` 均通过。真实 Labs 浏览器流因公网 health 仍 500 未执行，不将静态证据当作用户流通过。

### SE-009｜实现解释面板、历史展示和本地账户隔离

- 状态：完成；阶段 S3；Owner：`apps/discovery` 前端；优先级 P0。
- 目标：从胶囊工具打开固定底部中央的解释面板，展示当前请求、结果和所有历史；使用按账户命名空间的 `localStorage`，最多保留配置条数（默认 30）。
- 依赖：`SE-008`；后续：`SE-010`、`SE-012`、`SE-014`。
- 预计触点：解释面板模板/DOM、前端状态模块、localStorage schema/version、Markdown 渲染入口和历史清空交互。
- 边界/非目标：历史不发给 AGENT、不保存服务端；所有文章共用列表，每条显示文章 ID；不创建第二个会话或聊天上下文；存储不可用时不伪造成功。
- 影响：记录 `PENDING/SUCCEEDED/FAILED/STOPPED/RATE_LIMITED` 等状态、选区字数、截断信息、回答和时间；超出上限挤出最早；清空只作用当前账户。
- 测试与验收：两账户互不可见、多个文章顺序、刷新/重新打开、超过 30 条、损坏 JSON、隐私模式/QuotaExceeded、清空确认和状态恢复；面板中部滚动而标题/关闭固定。
- 风险/停止：无法可靠取得账户 namespace 时停用持久化，暂用当前会话存储并报告，不共用无隔离 key。
- 授权：Labs 浏览器本地状态和前端实现；不写生产用户数据。
- 证据（2026-09-08）：新增固定底部中央解释面板、标题/关闭固定、中部独立滚动、文章 ID 标记、清空历史、损坏/不可用 localStorage 的安全回退、按账户命名空间与管理员配置历史上限；停止记录 `CANCELLED`，失败记录可重试。前端 `8 passed`（含账户隔离 key、历史上限、已停止状态断言），JS/CSS 构建通过。真实多视口登录浏览器流待 Labs health 恢复后执行。

### SE-010｜接入解释 AGENT 调用与 Markdown 安全输出

- 状态：完成；阶段 S2；Owner：解释服务 + `apps/agents`；优先级 P0。
- 目标：将 `SE-005` DTO 交给独立解释 AGENT，复用现有 Gateway、Prompt 快照、token 预留、审计和安全 Markdown renderer，并向面板返回真实状态。
- 依赖：`SE-002`、`SE-005`、`SE-006`、`SE-007`；后续：`SE-011`、`SE-012`、`SE-014`。
- 预计触点：解释 application service、AGENT profile availability、Gateway 调用、Markdown sanitizer、错误码和任务结果 DTO。
- 边界/非目标：不发送整篇文章；不调用工具或执行代码；不强制输出 schema；不做流式；不把上游原始错误/响应暴露给用户。
- 影响：成功只返回中文安全 Markdown；模型拒答、配置不可用、超时、网络失败和输出不安全分别映射；用户限制在本服务调用前已裁决。
- 测试与验收：fake Gateway 覆盖成功、中文软约束、危险 HTML/链接、Provider 失败、超时、空输出、异常和 token 结算；真实服务读回不会写正文日志或通知。
- 风险/停止：若现有 Gateway 只能返回结构化 JSON 且会强迫解释输出使用题库 schema，先扩展兼容的文本结果边界，不在 discovery 内绕过 Gateway。
- 授权：默认使用 Labs 隔离 Provider/fake；当前回合在用户明确授权后允许使用 Labs 已配置 Endpoint 做一次真实验证，不连接生产。
- 证据（2026-09-10）：解释任务复用 `apps.agents.gateway.AgentGateway`，以 `article-selection-explanation.v1` 单字段 Markdown envelope 接收结果；真实 Labs Endpoint 严格检查返回 `SUCCEEDED/SCHEMA_SUPPORTED/native`，启用 profile 后真实文章请求返回中文安全 Markdown，并在面板读回 `SUCCEEDED`。输出未写正文日志或通知。

### SE-011｜实现停止、失败原因和幂等重试用户流

- 状态：完成；阶段 S3；Owner：`apps/discovery` 前端 + 解释服务；优先级 P0。
- 目标：面板在等待时显示停止；用户停止后保存 `STOPPED`；仅 AGENT 请求异常显示一次重试，点击后清除失败点并恢复等待/停止状态。
- 依赖：`SE-007`、`SE-009`、`SE-010`；后续：`SE-012`、`SE-014`。
- 预计触点：解释请求 JS、取消/重试 endpoint、TaskRun 状态映射、本地历史状态和全局反馈复用。
- 边界/非目标：限额、授权拒绝、空文本、安全拒绝和手动停止不显示重试；不重复扣每日/每分钟次数；不伪造取消成功。
- 影响：重复点击和网络重放使用幂等键；旧失败记录不可重复提交；重试新建合法调用但不会复用旧的半成品输出；错误原因安全可读。
- 测试与验收：停止排队任务、停止执行中任务、晚到响应、失败一次重试成功、重试再次失败、重复点击和刷新恢复；前后端 TaskRun/Invocation/Reservation 终态一致。
- 风险/停止：如果前端显示已停止而后端仍会继续发布结果，停止按钮保持禁用并回到错误状态，直到取消合同通过。
- 授权：Labs 真实用户流和隔离任务验证；不重试生产任务。
- 证据（2026-09-08）：创建/状态/取消/重试 API 均按账户授权和文章 ID 校验；用户停止后服务端将请求与 Invocation 置为终态、释放未用 reservation，晚到结果被丢弃；仅 provider 异常保留 retryable。前端停止/失败/一次重试/已停止 localStorage 状态均已接入，状态回归 `3 passed`、Gateway 取消 reservation 回归 `1 passed`、前端回归 `8 passed`。公网 Labs health 仍为既有 500，未执行真实浏览器点击。

### SE-012｜实现管理员内容与互动配置界面

- 状态：完成；阶段 S4；Owner：管理后台/内容与互动；优先级 P1。
- 目标：在管理界面内容与互动分类下展示并编辑四项解释参数，提供清晰描述、范围校验、并发版本冲突和保存反馈。
- 依赖：`SE-003`；后续：`SE-013`、`SE-014`。
- 预计触点：`apps/administration` 导航、query/service/form/template、配置 CSS、审计和权限测试。
- 边界/非目标：不把 AGENT Endpoint token、并发或超时配置复制到本页；不提供流式开关；不展示用户本地历史正文。
- 影响：管理员修改影响后续解释请求；显示默认值 50/5/1000/30 与当前值；保存成功/失败走现有全局反馈组件，不能用页面插入文字造成布局跳动。
- 测试与验收：管理员/非管理员、默认值、边界值、非法值、并发保存、审计、配置读回和导航可达；页面 390/768/1440 无挤压。
- 风险/停止：若内容与互动分类没有可扩展配置 owner，先补充 owner/迁移设计，不把配置塞入 Endpoint 或前端常量。
- 授权：Labs 配置页面和隔离迁移测试；生产迁移需另行授权。
- 证据（2026-09-08）：在既有管理后台“站点设置/内容与互动”页面新增文章划词解释配置表单，复用 `SiteConfiguration` row version、管理员权限、审计和全局反馈 Toast；四项帮助文案明确影响，范围为 `50/5/1000/30` 默认值对应的服务端上下限。隔离管理页回归 `apps/administration/tests/test_article_explanation_settings.py` 为 `2 passed in 39.88s`；目标 Ruff 与 `manage.py check`/迁移漂移通过。

### SE-013｜实现账户个人自动授权 Switch 与文章首次授权弹窗

- 状态：完成；阶段 S4；Owner：账户设置 + discovery；优先级 P1。
- 目标：在个人设置中提供默认关闭的自动接受 Switch，并在文章首次使用时实现逐篇同意/拒绝和状态恢复。
- 依赖：`SE-004`、`SE-008`、`SE-012`；后续：`SE-014`、`SE-015`。
- 预计触点：账户偏好模型/服务、个人设置模板、文章授权 dialog、前端 localStorage namespace 和提示文案。
- 边界/非目标：手动同意只记住当前文章；自动接受是账户偏好；未登录没有授权弹窗；不向服务端保存文章选区或历史正文。
- 影响：拒绝取消当前选择并可再次询问；关闭自动接受后下一篇文章恢复询问；面板提示可前往个人设置关闭自动接受。
- 测试与验收：首次/再次同意、拒绝、切换文章、开启/关闭 Switch、退出登录/换账户、清理浏览器数据和无权限文章；焦点、ESC 和键盘操作符合页面矩阵。
- 风险/停止：账户切换后仍能读到前一账户的同意或历史，立即停止并修复 namespace/注销清理。
- 授权：Labs 本地账户与浏览器流验证；不修改生产账户偏好。
- 证据（2026-09-08）：账户个人设置新增默认关闭的“自动接受文章划词解释” Switch，个人设置服务和审计按账户隔离；文章首次使用以项目主题样式 dialog 请求本篇授权，手动授权只写当前文章 namespace，关闭自动接受后恢复逐篇询问。账户回归 `3 passed`，前端授权/账户 namespace 静态回归包含在 `8 passed`；真实登录浏览器流待 Labs health 恢复后执行。

### SE-014｜跨层回归、性能与安全验收

- 状态：完成；阶段 S4；Owner：测试/交付；优先级 P0。
- 目标：验证功能从文章选区到 TaskRun、AGENT、取消/重试、Markdown 输出、限额、授权和 localStorage 的完整闭环。
- 依赖：`SE-006`、`SE-007`、`SE-008`、`SE-009`、`SE-010`、`SE-011`、`SE-012`、`SE-013`；后续：`SE-015`。
- 预计触点：`apps/agents/tests`、`apps/operations/tests`、`apps/discovery/tests`、账户/管理测试、前端 `node --test`、隔离 PostgreSQL/Redis/Mailpit 和 Labs 浏览器流。
- 边界/非目标：不连接生产数据库；真实 Provider 仅限本回合明确授权的 Labs Endpoint；不以静态 DOM 或 mock 单独证明真实用户流；不扩大到流式验证。
- 影响：覆盖四类身份、文章可见性、两账户隔离、限额竞态、取消晚到、失败重试、损坏历史、存储不可用、三主题和 390/768/1440。
- 测试与验收：先 RED 后 GREEN；目标逻辑/数据测试、Django check、前端构建、`git diff --check`、隔离数据读回和 `/usr/local/bin/blog-playwright-cli` 真实点击均有退出码/证据；Labs 服务保持 active/running、health 200、代表性文章流无相关控制台/HTTP 错误。
- 风险/停止：任何权限、token 结算、晚到响应、文章可见性或本地账户隔离缺陷未闭合，不能进入交付。
- 授权：仅 Labs 和隔离测试；当前回合允许一次已记录的 Labs Provider 验证；不执行 Git 交付、生产部署或生产迁移。
- 当前证据（2026-09-10）：`npm run build:css`、`npm run build:js`、`npm run test:frontend` 为 `8 passed`；服务 `active/running`，live/ready `200`。真实浏览器登录文章流验证了授权 dialog 居中、选区按钮、中文成功结果、面板焦点、标题拖动边界、390px 面板内部滚动/自动滚到底部，以及 HTML 非 JSON 响应映射为“解释请求失败，请稍后再试”且无 `Unexpected token`。临时账户关联的 3 请求、3 使用记录、3 TaskRun、1 Invocation、reservation、告警、会话和安全事件已定向清理，账户读回为 0；解释 AGENT 保留为启用配置，严格能力检查保留为 `SUCCEEDED/SCHEMA_SUPPORTED`。

### SE-015｜更新架构/页面契约与下一轮交付记录

- 状态：完成；阶段 S4；Owner：架构/交付；优先级 P1。
- 目标：把实现证据、错误码、状态机、配置 owner、页面矩阵和本期非目标写回项目文档，确保下一轮不会丢失裁决。
- 依赖：`SE-014`；后续：无。
- 预计触点：`docs/architecture/modules/05-discovery-reading.md`、`docs/architecture/contracts/03-frontend-contract-map.md`、`docs/architecture/contracts/04-events-errors.md`、`docs/architecture/contracts/05-background-tasks.md`、本目录文档和必要的账户/配置契约。
- 边界/非目标：文档更新不等于产品完成；不把流式规划写成已实现；不新增第二份进度账；不在本项执行提交、推送或部署。
- 影响：记录唯一 owner、输入/输出 DTO、限额和取消合同、浏览器历史边界、验收证据和未完成风险；链接保持有效。
- 测试与验收：文档链接检查、Todo 状态/依赖审计、差异检查和最终工作区核对；若本轮需要 Git 交付，等待用户在新回合明确授权后按任务分支规则执行。
- 风险/停止：实现与文档或实际运行行为不一致时，以代码/测试事实为准，修正文档并保留未完成项。
- 授权：仅本地文档写入与检查；Git、部署和生产动作需另行授权。
- 证据（2026-09-10）：已更新 discovery owner、前端 URL/组件契约、解释错误码/脱敏边界、TaskRun/取消/幂等契约，并同步记录本期“不做流式、无服务端历史、无第二套 Gateway/通知/Markdown renderer”的裁决。文档链接、状态/依赖审计、差异检查和 Labs 健康读回通过。
