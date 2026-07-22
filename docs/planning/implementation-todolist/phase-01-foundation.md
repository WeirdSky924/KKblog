# P1 项目与质量骨架（6）

退出门禁：仓库治理、Django 入口、配置、错误、Outbox、测试和架构守卫可在隔离环境运行。

### FND-001 建立仓库治理入口与根说明
- 元数据：状态 `完成`；阶段 P1；owner `project-governance`；优先级 P0。
- 目标/行为：按 `DEC-001` 先读回 GitHub 远端历史与实际默认分支；有历史时从实际默认分支建 `codex/<task>`，空仓时以 `main` 初始化后再建任务分支。随后新增根 `AGENTS.md`、`README.md`、环境/贡献/部署入口，使后续开发者从唯一入口找到本清单和架构真值。
- 来源：访谈 Q174-Q179；`project-plan.md` §1/§8；`architecture/README.md` §实施门禁。
- 依赖：前置 `DEC-001`；后续 `FND-002`、`QA-006`。
- 文件：`.git/`、`AGENTS.md`、`README.md`、`CONTRIBUTING.md`、`docs/operations/README.md`（按最终治理选择）。
- 边界：不创建业务代码；不提交/推送/部署；不复制 47 份文档为平行真值。
- 影响：七类业务影响均无；治理链接需可追踪。
- 测试/验收：`git status --short --branch`、链接检查、UTF-8 检查；根 README 明示未实现状态与禁止自动部署。
- 风险/停止：远端历史或实际默认分支无法读回、默认分支分叉、上游不符、工作区不干净或根文件已被用户修改即停止并保留现场。
- 证据：2026-07-21 使用仓库专用 SSH key 只读执行 `git ls-remote --symref ... HEAD` 退出 0 且无引用，用户同时确认目标为空仓；随后以 `main` 初始化并在首次项目文件写入前切换到 `codex/p1-foundation`。RED 文件守卫退出 1，准确列出缺少 `AGENTS.md`、`README.md`、`CONTRIBUTING.md`、`docs/operations/README.md` 和 `.gitignore`；新增唯一治理入口后，文件/关键声明守卫、4 份入口 UTF-8/本地链接检查、可跟踪检查和分支/远端读回均退出 0。仓库级回归读取 81 份 UTF-8 Markdown、检查 63 个本地链接且缺失 0，秘密模式探针和 `git diff --check` 均退出 0。未执行容器、数据库、浏览器、邮件、备份、部署、提交或推送；治理文件仍是未提交工作区改动，实际运行入口由后续 FND 任务建立。残余风险是远端尚无提交，后续交付仍须用户明确授权。
- 授权：`是`；Git 初始化/远端/分支需当前授权，文档创建随实施授权。

### FND-002 脚手架化 Django 模块化单体与依赖锁
- 元数据：状态 `完成`；阶段 P1；owner `config`；优先级 P0。
- 目标/行为：建立 Python 3.12、Django、`uv` 与前端构建清单；按稳定 owner 创建最小可运行 app，不批量生成空 service/models 包。
- 来源：访谈 Q211-Q223、Q322；`01-system-directory.md` §建议目录/领域结构；ADR-001、ADR-003。
- 依赖：前置 `FND-001`；后续 `FND-003`、`FND-006`、`RUN-001`、`QA-006`。
- 文件：`pyproject.toml`、`uv.lock`、`manage.py`、`config/`、`apps/`、`templates/`、`static/`、`package.json` 及锁文件。
- 边界：只建真实入口和已知 app；首版不建公共 API、移动 App API、第三方登录、SPA、万能 repository/EventBus 或空洞目录。
- 影响：数据/权限/审计/缓存/异步/媒体/通知暂无线；建立模块 import 边界。
- 测试/验收：先写 import/owner 失败守卫；`uv run python manage.py check`、模块边界测试、锁文件可重建。
- 风险/停止：Python/Django/TipTap/Tailwind 版本不兼容或依赖许可/维护状态不合格时停止选型。
- 证据：RED import/owner 守卫退出 1，准确列出 8 个缺失入口与 `django` import。最小实现只创建真实 `apps.core` owner、Django/ASGI/WSGI/URL 入口和 Tailwind/esbuild 前端入口；未提前生成其他 13 个领域 app 或空 service/model。`uv lock` 解析 17 包，最终锁使用官方 PyPI 且离线 `uv sync --locked` 退出 0；`npm ci` 安装 85 包、全量安装审计 0 漏洞。GREEN `uv run python manage.py check`、`npm run build`、12 文件/owner/import 守卫、`uv lock --check` 与生产依赖 `npm audit --omit=dev --audit-level=high` 均退出 0。回归 `ruff check .`、Python compileall、直接依赖树与源/派生产物跟踪守卫均退出 0。读回 Django 5.2.16 LTS、psycopg 3.3.4、Gunicorn 26、pytest 9.1.1、pytest-django 4.12、Ruff 0.15.22，以及 TipTap 3.28、Tailwind 4.3.3、Alpine 3.15.12、HTMX 2.0.10、esbuild 0.28.1；许可证分别为 BSD-3-Clause/LGPL-3.0/MIT/0BSD，未发现不合格项。未执行 PostgreSQL、Redis、容器、浏览器、邮件、迁移、提交或推送；当前 bootstrap settings 仅供脚手架 check，严格环境分层由 `FND-003` 替换。
- 授权：`否`（项目文件）；联网安装依赖只在未来实施回合允许时执行。

### FND-003 实现 settings 分层、环境 schema、时钟与稳定 ID
- 元数据：状态 `完成`；阶段 P1；owner `core`；优先级 P0。
- 目标/行为：development/test/production 配置严格分层；前两者只使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit；production 缺真实域名、管理员邮箱、Resend 发件身份/密钥或其他必需秘密时安全失败；统一 UTC 存储、上海业务日、UUID/ULID 与可注入 Clock。
- 来源：`modules/01-platform-foundation.md`；`01-system-directory.md` §配置目录；`data/02-identity-content-fields.md`；访谈 Q187、Q213、Q265。
- 依赖：前置 `FND-002`、`DEC-002`；后续 `FND-004`、`FND-005`、`RUN-002`、`OBS-007`、`ACC-001`、`CNT-001`、`QA-006`。
- 文件：`config/settings/{base,development,test,production}.py`、`apps/core/time/`、`apps/core/ids.py`、`.env.example`。
- 边界：网页 SiteConfiguration 不得替代 `.env`；不写真实秘密或弱默认值。
- 影响：数据：时间/ID 基础；权限：秘密边界；其余无业务副作用。
- 测试/验收：RED 每个生产必需值的缺失/非法、测试身份泄入生产与上海 00:00 边界；`manage.py check --deploy`（安全配置环境）和 ID 属性测试。
- 风险/停止：任何秘密进入输出/diff、时区混用或测试读取生产 `.env` 时立即停止。
- 证据：RED 21 场景退出 1，其中 9 个生产变量的缺失/非法共 18 项均因严格 settings package 尚不存在而产生错误失败，Clock/上海转换/ID 三模块也不存在。实现 `base/development/test/production` 四层、9 项无默认生产 schema、进程内开发/测试密钥、localhost/Mailpit 身份、Resend SMTP 配置、可注入 UTC Clock、上海业务日边界、UUIDv4 与 `python-ulid` 4.0.1（MIT）适配；生产环境对象和 URL 解析错误均不回显秘密。首次 GREEN 定位并修复小写 Crockford ULID 规范化适配；最终 18 个缺失/非法生产场景均安全拒绝且值泄漏 0，随机安全配置下 `manage.py check --deploy` 退出 0，development/test 两层 `manage.py check` 均退出 0。读回开发/测试固定身份与 Mailpit 2 层、上海 00:00 前后/UTC 日界 4 项、UUIDv4 5,000 个与 ULID 5,000 个唯一性/格式/回读均通过。Django safe-settings 与环境对象 repr 秘密泄漏探针为 0，`.env.example` 含 9 个空生产键且可跟踪。独立 `ruff check`、`ruff format --check`（18 文件）、compileall、`uv lock --check`、秘密模式探针和 `git diff --check` 均退出 0。未配置或输出真实生产域名、邮箱、Resend 身份/密钥、数据库/Redis URL、媒体目录或初始密码；未连接服务、发信、迁移、提交或推送。残余风险是外部 Resend 身份认证与实际服务连通性只能在后续获授权运行环境读回，当前 production 对缺值保持关闭失败。
- 授权：`否`；填入生产秘密另行授权。

### FND-004 建立统一错误码、trace 与脱敏链
- 元数据：状态 `完成`；阶段 P1；owner `core`；优先级 P0。
- 目标/行为：所有 HTML/HTMX 请求获得 trace；422/401/403/404/409/429/503/500 稳定映射，用户只见安全中文提示和 trace code。
- 来源：访谈 Q199-Q203；`contracts/04-events-errors.md` §错误分类/Trace/脱敏；`modules/01-platform-foundation.md` §错误链。
- 依赖：前置 `FND-003`；后续 `FND-006`、`RUN-005`、`OBS-007`、`OBS-004`、`ACC-004`、`OBS-005`、`ADM-001`、`QA-006`。
- 文件：`apps/core/errors/`、`apps/core/observability/`、中间件、`templates/errors/`。
- 边界：不把异常消息当 UI 文案；不暴露 endpoint、SQL、堆栈、模型名、Cookie 或正文。
- 影响：数据：未来 RuntimeError 引用；权限：隐私 404；审计/缓存/异步/媒体/通知无。
- 测试/验收：故意注入密码、验证码、Cookie、连接串、正文；各 sink 无泄露，500 页面显示可检索 trace。
- 风险/停止：任一敏感值出现在日志、页面、测试快照或事件 payload 即停止交付并清理证据。
- 证据：RED 错误契约探针在实现前退出 1，缺少稳定错误目录、trace 中间件、统一模板和脱敏 owner；最小实现新增 8 个带 `.v1` 的稳定错误码、HTML/HTMX 双模板、每请求 ULID trace、`X-Trace-Code`/`no-store`/`Vary`/`Retry-After` 语义，以及递归结构化脱敏和日志过滤。GREEN 隔离 Django Client 集成探针退出 0，读回 401/403/404/409/422/429/500/503 共 8 个状态、HTMX partial 1 项、隐私 404 1 项、header/body/log trace 一致 8 项；密码、验证码、Cookie、PostgreSQL URL、正文与路径 6 类 sentinel 在页面、日志和结构化输出中的泄露为 0。使用 `/usr/local/bin/blog-playwright-cli` 由 `blog-browser` 在 `127.0.0.1:8765` 验收 404/500：390/768/1440 三档、light/dark/eye-care 三主题均无横向溢出或遮挡，中文字体正常，按钮 `114x50px`，Tab 获得 3px 可见焦点且 Enter 返回来源页；重启静态服务后样式、脚本及页面实际请求的 8 个 Noto Sans SC 字体分片均读回 200，`document.fonts.check` 为 true，控制台仅有预期的主文档 404/500。回归 `ruff check .`、`ruff format --check .`（26 文件）、development/test `manage.py check`、compileall、`uv lock --check`、`npm run build`、生产依赖 `npm audit --omit=dev --audit-level=high`、秘密模式扫描和 `git diff --check` 均退出 0；全项目尾随空白扫描仅命中总索引 3 个既有 Markdown 硬换行，源码/配置范围无命中。浏览器与临时服务已停止；未连接数据库/Redis、发送邮件、迁移、提交、推送或部署。残余风险是当前仅建立通用错误契约，后续业务域必须复用同一映射与脱敏 owner，并由 FND-006 将临时集成探针固化为测试套件。
- 授权：`否`。

### FND-005 建立版本化事件与事务 Outbox 基础
- 元数据：状态 `完成`；阶段 P1；owner `core`；优先级 P0。
- 目标/行为：业务事务可原子写事件；发布器至少一次投递，消费者按 `event_id + consumer` 去重并保留可观测状态。
- 来源：ADR-004；`contracts/04-events-errors.md` §事件信封/Outbox；`data/01-er-model.md` §聚合写边界。
- 依赖：前置 `FND-003`；后续 `OBS-006`、`OBS-001`、`ACC-011`、`MED-006`、`CNT-011`、`CNT-003`、`CNT-005`、`CNT-008`、`CNT-009`、`CMT-003`、`CMT-006`、`CMT-009`、`OBS-008`、`OBS-009`、`QA-004`、`QA-006`。
- 文件：`apps/core/events/`、outbox/consumer migrations、publisher management command/task、`tests/contracts/`。
- 边界：事件不承载正文、原 IP、密码/码/token/路径；Outbox 不是审计；Redis 锁不是最终裁决。
- 影响：数据：Outbox/消费记录；异步：发布/重投；通知/缓存通过消费者后续接入；其余无。
- 测试/验收：提交前崩溃无事件；提交后崩溃可补投；重复投递只产生一次消费结果。
- 风险/停止：消费者非幂等、事件 schema 无版本或业务写依赖即时外部调用时停止下游接入。
- 证据：RED 文件/import 守卫退出 1，准确报告 9 个缺失入口与 5 个失败导入；migration dry-run 在模型实现后仍退出 1 并列出待生成的 `EventConsumerRecord`/`OutboxEvent`，随后由 Django 生成 `0001_outbox_foundation`。最小实现要求 `domain.fact.vN` 正版本号和调用方 schema validator，payload 限 64 KiB 并递归拒绝密码、验证码、token、Cookie、连接串、正文、原 IP、邮件正文、私钥和路径；`enqueue_event` 只允许在调用方 `transaction.atomic()` 内执行并复用现有 ULID、Clock、trace owner。发布器使用 PostgreSQL `select_for_update(skip_locked)`、有界 batch、租约 token/过期时间、PENDING 重试和 PUBLISHED 终态；进程在外部发布后硬崩溃会留下租约，过期后至少一次补投。消费者以数据库唯一约束 `(event_id, consumer_name)`、事务内 handler+终态、租约恢复和安全错误码实现幂等；管理命令缺少或无法初始化显式 transport 时关闭失败，输出仅含数量。真实 PostgreSQL 16.14 以低权限用户、loopback `127.0.0.1:55432`、独立临时目录和 `kaj_test_runner/kaj_test_p1` 运行，migration 退出 0；catalog 读回 2 张表、9 个约束和 7 个索引，smoke 行读回 Outbox `published/attempts=1/lease cleared`、consumer `processed/attempts=1/lease cleared`，Django 连接时区为 UTC。GREEN `KAJ_TEST_DATABASE_URL=... uv run pytest --ds=config.settings.test -q tests/contracts` 退出 0，23 项覆盖提交前回滚、发布后硬崩溃补投、普通失败延迟重试、消费失败副作用回滚、重复消费仅一次数据库副作用、版本/schema/敏感 payload、管理命令成功与关闭失败，以及测试 URL 对非 loopback、共享库、错误用户、密码和 query 的拒绝。回归 `ruff check .`、`ruff format --check .`（42 文件）、development/真实 PostgreSQL test `manage.py check`、migration 漂移、compileall、`uv lock --check`、源码空白、秘密模式和 `git diff --check` 均退出 0。Redis 未参与最终裁决且本任务不写缓存；未连接共享/生产库、外部 broker、邮件或文件系统，未提交、推送或部署。残余风险是实际 Celery/Redis transport 尚未由 RUN 阶段配置，当前命令对此保持关闭失败；所有下游 handler 仍必须通过本消费入口或提供等价的数据库幂等约束。
- 授权：`否`。

### FND-006 固化 pytest、Ruff、Playwright 与架构守卫
- 元数据：状态 `完成`；阶段 P1；owner `tests`；优先级 P0。
- 目标/行为：提供一致的 RED/GREEN、真实 PostgreSQL/Redis/临时媒体、四身份浏览器与 import 边界测试命令。
- 来源：访谈 Q217-Q218；`01-system-directory.md` §测试布局；`delivery/02-module-verification-matrix.md`；`delivery/03-code-review-checklist.md`。
- 依赖：前置 `FND-002`、`FND-004`；后续 `RUN-005`、`RUN-006`、`OBS-006`、`ACC-001`、`OBS-001`、`MED-001`、`MED-007`、`CNT-001`、`CMT-001`、`QA-006`。
- 文件：`pytest.ini`/`pyproject.toml`、`tests/{contracts,integration,e2e,fixtures}/`、Playwright 配置、Ruff 配置、测试脚本。
- 边界：不复制生产数据/秘密；mock 不能替代数据读回；不建立第二套测试体系。
- 影响：七类业务影响均无；测试夹具需隔离数据、媒体和邮件。
- 测试/验收：故意制造一条失败断言证明 harness 有效；固定 `uv run pytest`、`uv run ruff check .`、`npx playwright test` 命令及退出码。
- 风险/停止：测试连接生产/共享库、写项目 `var/` 或 Playwright 只跑静态截图时立即停止。
- 证据：RED 骨架守卫退出 1，准确报告缺少 `tests/conftest.py`、integration/e2e/fixtures、Playwright config 和测试脚本共 7 项，以及 pytest/Ruff 配置和 Playwright 依赖缺失；临时 `assert 1 == 2` 由真实 pytest 报告 1 failed、退出 1 后立即删除。实现以 `pyproject.toml` 固定 pytest/Ruff 唯一配置，加入 `scripts/test` 环境门禁、真实 PostgreSQL/Redis/Mailpit/pytest 临时媒体 fixture、AST 绝对/相对 import 方向与 core owner 守卫；缺四项隔离环境时脚本安全退出 2，不回落 SQLite/mock。测试 URL 仅允许 loopback、显式高端口、`kaj_test_runner/kaj_test_*`，Redis 禁止 DB 0/凭据，Mailpit SMTP/API 必须成对且无凭据；fixture 按前缀/邮箱/目录清理。Playwright 1.61.1（Apache-2.0）声明 visitor/user/author/admin 四项目与 `/tmp` mode-0600 storage-state 契约；runner 不直接启动 Chrome，页面动作全部调用 `/usr/local/bin/blog-playwright-cli` 由 `blog-browser` 执行。GREEN 在低权限 loopback 临时服务上运行 PostgreSQL 16.14、Redis 7.0.15、Mailpit 1.30.5（官方 SHA-256 校验通过，SMTP 仅收 `@kaj.test`），`uv run pytest` 退出 0、43 passed，真实读回 PostgreSQL 测试库/UTC、Redis value+TTL+删除、媒体字节+大小+项目 `var/` 外路径、Django SMTP 投递及 Mailpit API sender/recipient；FND-005 事务/租约/重试/幂等合同同时回归。`npx playwright test` 退出 0，四身份状态合同 4 passed、visitor 真实 404/422/500 流 1 passed，user/author/admin 因 ACC-001 尚未创建真实账户 state 明确 3 skipped；visitor 流覆盖 390/768/1440、light/dark/eye-care、静态资源 200、中文字体、无横溢出、44px 命中区、Tab 焦点与 Enter 历史恢复，不以 runner 自带 root browser 或静态截图代替。总回归 `uv sync --locked`、`npm ci`、`ruff check .`、`ruff format --check .`（50 文件）、development/test `manage.py check`、migration 漂移、compileall、`npm run build`、全依赖 `npm audit --audit-level=high`、83 份 UTF-8 Markdown/66 个本地链接、源码空白、秘密模式和 `git diff --check` 均退出 0。production `check --deploy` 首轮虽退出 0 但报告 W002/W003，补入官方 CSRF/X-Frame middleware 后聚焦测试 2 passed，最终退出 0 且 0 warning；读回 403/200 CSRF 行为及统一 500 的 `DENY`/`nosniff`/`no-store`。测试结束读回 Redis DB size 0、Mailpit message count 0、pytest 测试库已删除，随后正常停止三项服务并删除全部本次 `/tmp` 数据/二进制/截图，项目进程与浏览器 session 均为零。未使用生产/共享数据、真实收件人、root Chrome、`--no-sandbox` 或项目 `var/`；未安装系统包、提交、推送、部署、备份或生产迁移。残余风险是三种登录身份的真实 storage state 与角色流必须等 ACC-001 建立账户后执行，当前明确 skip 而非伪装通过；Celery/Compose/健康编排由后续 RUN 任务建立。
- 授权：`否`；安装浏览器/系统依赖需未来执行环境允许。

[返回总索引](../implementation-todolist.md)
