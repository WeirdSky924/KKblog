# P12 跨模块回归与部署准备（6）

退出门禁：数据、权限、浏览器、无障碍、任务、缓存、文件、Compose 和部署沙箱证据全部新鲜。

### QA-001 执行 schema、migration、约束与并发总回归
- 元数据：状态 `完成`；阶段 P12；owner `tests-integration`；优先级 P0。
- 目标/行为：从空库完整migrate并验证所有约束/索引/外键/删除策略；覆盖邀请码、昵称、修订、标签、评论、导出等并发裁决和expand/migrate/contract兼容。
- 来源：`data/04-indexes-constraints.md` 全文；`delivery/02-module-verification-matrix.md` §数据并发；`delivery/03-code-review-checklist.md` §数据迁移。
- 依赖：前置 `ACC-001`、`MED-001`、`CNT-001`、`CNT-010`、`CNT-011`、`CMT-001`、`OBS-001`、`OBS-004`、`OBS-005`、`OBS-006`、`OBS-007`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-004`、`ADM-006`；后续 `QA-002`、`QA-004`、`QA-005`、`QA-006`。
- 文件：`tests/integration/migrations/`、constraint/concurrency suites、migration notes。
- 边界：只用隔离PostgreSQL；不对生产/共享库迁移；SQLite结果不作证；每个迁移记录锁/兼容/备份/回滚限制。
- 影响：数据：全schema；权限/审计/缓存/异步/媒体/通知仅验证关联约束。
- 测试/验收：RED至少包含双事务；`uv run pytest tests/integration/migrations tests/integration/concurrency -q`、`manage.py makemigrations --check`、迁移读回SQL。
- 风险/停止：迁移不向前兼容旧应用、约束只在表单或测试触碰生产连接即停止。
- 证据：在独立 `kaj-p12-postgres` PostgreSQL 16 容器和 loopback `kaj_test_p12` 数据库中执行。聚焦 RED 首轮退出 1，`4 failed, 7 passed`：迁移兼容说明确实缺失，另三项准确识别为新探针的迁移总数、表达式唯一索引分类和标签作者 fixture 假设错误，未据此修改产品。补齐 `docs/operations/migrations.md` 对 43 条 migration 的逐条锁/兼容/备份/回滚记录并修正探针后，目标套件退出 0，`11 passed in 22.84s`；其中每次从新建空 PostgreSQL 数据库完整 migrate 后读回全部 leaf、`pg_trgm` 与核心表，并在 finally 终止定向连接和删除临时库。六组真实双事务分别验证邀请码行锁、昵称 casefold 唯一、修订序号唯一、标签规范值、评论条件公开和 `RUNNING/CANCEL_REQUESTED` 导出部分唯一的单胜者/幂等终态。账户、内容、评论、媒体、通知、TaskRun 与新套件相关回归退出 0，`83 passed in 80.80s`；新测试 Ruff lint/format 均退出 0。`manage.py makemigrations --check --dry-run`、`manage.py check` 与 `git diff --check` 均退出 0；Django 仅报告未构建 `static/dist` 的已知 warning。隔离主库 SQL 读回 `43` 条 migration、`315` 个约束、`303` 个索引，确认同文章修订延迟外键、评论树延迟 trigger 和 TaskRun 幂等唯一；无残留 `kaj_test_p12_empty_*` 数据库。未执行生产/共享数据库 migration、生产备份、部署、服务重启、Git add/commit/push。
- 授权：隔离测试 `否`；生产 migration `是`。

### QA-002 执行四身份完整授权矩阵与存在性隐私回归
- 元数据：状态 `完成`；阶段 P12；owner `tests-security`；优先级 P0。
- 目标/行为：访客、普通用户、对象作者、其他作者、唯一管理员对文章/评论/举报/账户/通知/设置/交换每个GET/POST/HTMX直接请求均符合矩阵；IP封禁覆盖有效会话。
- 来源：`contracts/02-authorization-matrix.md` 全文；ADR-005；`delivery/02-module-verification-matrix.md` §高风险权限。
- 依赖：前置 `ACC-010`、`ACC-011`、`CNT-005`、`CNT-008`、`CNT-009`、`MED-004`、`DSC-004`、`DSC-005`、`DSC-006`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-003`、`ADM-002`、`ADM-003`、`ADM-004`、`EXC-007`、`QA-001`；后续 `QA-003`、`QA-006`。
- 文件：parameterized policy/service tests、direct HTTP/browser security specs、fixtures。
- 边界：按钮隐藏不算证据；私人/草稿/软删统一404；管理员例外不得扩大；举报人/完整IP/收藏/会话严格隔离。
- 影响：数据：权限读回；权限核心；审计：admin写；缓存：命中后重判；异步：事件接收者；媒体：直接URL；通知：去重/隐私。
- 测试/验收：`uv run pytest tests/integration/authorization -q`；Playwright直接URL/伪造POST；核对HTTP差异、DB无副作用、通知/审计。
- 风险/停止：任一越权、对象存在性侧信道或不同入口策略漂移即阻断全部上线。
- 证据：在 `kaj_test_p12` PostgreSQL、独立 P12 Redis DB 15 与 Mailpit 上新增 15 个参数化授权测试，逐个请求 17 个管理入口和 5 个作者入口的 GET/POST/HTMX，覆盖访客、普通用户、对象作者、其他作者、唯一管理员；验证公开/登录/私人文章、草稿/定时/冷静期、管理员显式只读入口与上海日去重、伪造作者编辑、通知接收者隔离、评论回复/删除/举报和 IP 封禁有效会话降级。测试首先发现账户设置、主题和会话响应缺少私有缓存头，补充统一 `private, no-store` 与 `Vary: Cookie` 后目标套件退出 0，`15 passed`；当前修改后的内容、账户、评论、媒体、通知与分析相关回归退出 0，`57 passed in 70.03s`。浏览器 RED 先以退出 1 证明完整应用 E2E server 缺失；建立只接受 loopback `kaj_test_*` PostgreSQL、`/tmp` mode `0600` storage state 和文档网段客户端 IP 的确定性 fixture 后，首次表面绿色又由服务器日志识别 CLI 会以退出 0 返回 `### Error`。共享 CLI runner 改为把该标记判为失败，并修正基础错误页对固定 Tab 次数的错误假设；受限 `/usr/local/bin/blog-playwright-cli`、`blog-browser` 用户和单 worker 重跑退出 0，授权规格 `1 passed (2.5m)`，基础响应式/键盘错误流 `2 passed (1.0m)`。真实浏览器证明普通用户 `/admin/users/` 为 403；其他作者和管理员对对象作者编辑 URL/伪造 HTMX POST 均为 404，普通用户 POST 为 403；私人和未知文章对无权身份使用同一安全 404；管理员从显式入口两次查看私人文章成功；封禁 `203.0.113.70` 后带有效用户 session 的首页为访客 200、设置页为 403 且不泄露备注。E2E PostgreSQL 读回草稿 revision 仍为 `1`、管理员查看 receipt/event 各 `1`、IP 封禁 Audit `1`，storage state 均为 `0600 blog-browser:blog-browser`，无遗留浏览器进程。Ruff、format、Django check 与 `git diff --check` 均退出 0。隔离 E2E 数据库、P12 容器和 `/tmp` state 为后续 QA 保留；未连接生产/共享服务、未发送真实邮件、未执行生产动作。
- 授权：`否`。

### QA-003 执行桌面/平板/手机全用户流、状态与无障碍验收
- 元数据：状态 `完成`；阶段 P12；owner `tests-e2e`；优先级 P0。
- 目标/行为：按访客/用户/作者/管理员覆盖页面矩阵 42 个路由及适用身份，执行注册登录、阅读发现、评论审核、编辑发布、设置、管理和交换；1440/390 全页，密集管理页 768；三主题及 S0-S7。
- 来源：`project-plan.md` §3原型验收；`03-frontend-design-system.md` §视觉验收；`prototype/page-state-matrix.md` 全文；`delivery/02-module-verification-matrix.md` §页面视觉/手工验收；21张原型图。
- 依赖：前置 `ACC-002`、`ACC-003`、`ACC-004`、`ACC-005`、`ACC-006`、`ACC-007`、`ACC-008`、`ACC-009`、`ACC-010`、`ACC-011`、`MED-002`、`MED-003`、`MED-004`、`MED-005`、`MED-007`、`CNT-002`、`CNT-003`、`CNT-004`、`CNT-005`、`CNT-006`、`CNT-007`、`CNT-008`、`CNT-009`、`CNT-010`、`CNT-011`、`DSC-001`、`DSC-002`、`DSC-003`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`DSC-008`、`CMT-002`、`CMT-003`、`CMT-004`、`CMT-005`、`CMT-006`、`CMT-007`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-002`、`OBS-003`、`OBS-005`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-002`、`EXC-003`、`EXC-004`、`EXC-005`、`EXC-006`、`EXC-007`、`AUT-001`、`AUT-002`、`AUT-003`、`AUT-004`、`AUT-005`、`AUT-006`、`ADM-001`、`ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-002`；后续 `QA-005`、`QA-006`。
- 文件：`tests/e2e/`、视觉快照/证据索引（不放敏感数据）、a11y checks。
- 边界：截图只证布局；必须真实点击/请求/DB读回；不以原型假数据为验收；不创建与设计token冲突的第二视觉系统。
- 影响：数据：关键写读回；权限：四身份；审计/缓存/异步/媒体/通知：各流观察真实结果。
- 测试/验收：`npx playwright test` desktop/mobile/tablet；检查键盘、焦点锁/Escape/返回、WCAG AA、44px触控、reduced-motion、缩放、无横溢/遮挡。
- 风险/停止：文本/控件重叠、移动端关键动作不可达、错误态丢输入或页面成功与后台事实不一致即阻断。
- 证据：在 `kaj_test_p12_e2e` PostgreSQL、P12 Redis DB 13、Mailpit 与 `/usr/local/bin/blog-playwright-cli` 的 `blog-browser` 用户下，以单 worker 运行完整应用套件，退出 0，`5 passed (8.5m)`。真实流覆盖邀请码注册与 Mailpit 验证码、HttpOnly session、错误登录 422 与输入保留、收藏和搜索空态、昵称/深色主题保存、评论 201 与作者缓冲区读回、390 视口 Markdown 编辑/预览/保存/终稿审查/立即发布及独立访客读回、管理员确认弹窗焦点锁/Escape/触发点恢复、导出 S0 防重复和 RUNNING→CANCELLED。RED 先发现普通表单 pending 状态晚一帧、Markdown 正文缺少可访问标签、共享确认弹窗未显式锁定首尾焦点，分别在唯一前端 owner 中修复并由真实浏览器 GREEN。42 路由矩阵覆盖 41 个页面路由加收藏动作，390/1440 全量、16 个密集管理页追加 768，三主题、reduced-motion、正文 WCAG AA、main 可见、横向溢出和按钮文字裁切均通过；分析页在测试环境的 503 为精确预期。`/tmp/kaj-p12-visual` 共 98 张 PNG，逐张解码成功，宽度分布为 390/768/1440=`41/16/41`，最少 64×64 采样颜色数 144。PostgreSQL 读回新账户 1、DARK 偏好、收藏 1、BUFFERED 评论 1、PUBLISHED 文章且 published revision 匹配、CANCELLED 导出与 request/cancel 审计各 1、文章 Outbox 1；TaskRun 在 worker 消费入口创建，故 QA-003 无 worker 环境为 0，真实 worker 留给 QA-004。授权与前端基础回归退出 0，`22 passed in 34.26s`；Ruff lint/format、Django check、`makemigrations --check --dry-run`、完整 `npm run build` 与 `git diff --check` 均退出 0，无残留浏览器/应用进程。未连接生产/共享服务、未发送真实邮件、未执行生产动作或 Git 交付动作。
- 授权：`否`；仅隔离测试数据。

### QA-004 执行 Outbox、Celery、缓存、文件 Saga 与故障回归
- 元数据：状态 `完成`；阶段 P12；owner `tests-operational`；优先级 P0。
- 目标/行为：对每项任务验证首成/重复/双worker/2败1成/3败/提交前后崩溃/对象中变；验证Redis清空、缓存全失效、媒体/文章/导出清理与告警去重。
- 来源：`contracts/05-background-tasks.md` §任务目录/任务测试；`04-operations-testing.md`；`delivery/02-module-verification-matrix.md` §数据并发。
- 依赖：前置 `FND-005`、`MED-006`、`CNT-004`、`CNT-008`、`CMT-004`、`DSC-008`、`OBS-006`、`OBS-007`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-003`、`EXC-005`、`QA-001`；后续 `QA-005`、`QA-006`。
- 文件：worker integration tests、fault injection fixtures、temporary media/archive/cache assertions。
- 边界：不以Celery eager替代真实worker；不发送真实外部邮件；文件/DB测试在隔离命名空间；不手工重试失败TaskRun伪装成功。
- 影响：数据：TaskRun/业务终态；权限：任务重判；审计关联；缓存：Redis；异步核心；媒体：Saga；通知：最终失败一次。
- 测试/验收：启动隔离worker执行任务矩阵，核对DB/文件/Redis/通知/RuntimeError；Ruff/pytest相关回归。
- 风险/停止：重复副作用、孤儿文件可访问、最终失败无可追踪证据或缓存泄露私密内容即阻断。
- 证据：在独立 `kaj_test_p12_worker` PostgreSQL、P12 Redis DB 11/12、Mailpit 和临时归档/媒体目录中验证。真实 Celery worker 使用 `pool=solo`、`concurrency=1`、专用 `qa004` 队列和 DB 12 broker；两次同幂等键 smoke 与一次 Outbox 发布均由 worker 接收，读回 smoke `TaskRun` 只执行一次、两条任务均 `succeeded`、`attempt=1`、租约为空、队列深度 0，worker 正常 warm shutdown。通用任务/Outbox/评论与定时文章故障矩阵先退出 0，`40 passed in 31.43s`，覆盖首成、重复、双 worker、两败一成、三败终态、提交前回滚、提交后崩溃、租约恢复、业务对象中变、发布后崩溃和消费者去重。新增导出归档生命周期回归退出 0，`7 passed in 12.06s`，真实读回原子 ZIP、SHA-256、三天到期、完成/取消竞态、provider 失败 `.part` 清理与重试、取消清理失败后重试、Outbox 写失败时事务回滚及已提交归档补偿删除、最终失败消费单次生效；新增真实 Redis 发现缓存回归退出 0，`3 passed in 8.97s`，验证文章/列表 generation、`flushdb` 全失效后 PostgreSQL 重建，以及 Redis 不可达时列表和正文 fail-open。文件 Saga、最终失败/通知和既有 Redis 丢失分组分别退出 0，`22 passed in 26.21s`、`33 passed in 29.75s`、`13 passed in 18.09s`；同一代码状态的 18 文件合并回归退出 0，`107 passed in 82.46s`。Mailpit 只接收 `@kaj.test` 测试邮件并在 fixture 后为 0；专用 Redis DB 11/12 定向清理后均为 0，无临时测试库、Celery/pytest/浏览器进程或 `.part` 文件残留。全仓 Ruff lint、619 文件 format check、Django check、`makemigrations --check --dry-run` 与 `git diff --check` 均退出 0。资源门禁为黄色，约 `924-968 MiB` 可用内存、约 `709 MiB` Swap 已用且无持续换页，所有重型命令单 worker 串行完成。未连接生产/共享服务、未执行生产任务/清理、真实外部邮件、部署、服务重启或 Git 交付。
- 授权：隔离容器 `是`（当前回合）；生产任务/清理 `是`。

### QA-005 执行 Compose、健康、备份与部署/回滚沙箱验收
- 元数据：状态 `完成`；阶段 P12；owner `operations`；优先级 P0。
- 目标/行为：在隔离环境验证构建、依赖未就绪、自动重启、live/ready、内部端口、一次数据库+媒体备份、迁移检测、维护页、迁移失败中止、健康失败应用回滚。
- 来源：访谈 Q179-Q186、Q265-Q274、Q288；`flows/04-import-export-sequences.md` §部署门禁；`delivery/02-module-verification-matrix.md` §Operational。
- 依赖：前置 `RUN-001`、`RUN-002`、`RUN-003`、`RUN-004`、`RUN-005`、`RUN-006`、`OBS-007`、`EXC-006`、`EXC-007`、`QA-001`、`QA-003`、`QA-004`、`DEC-002`、`DEC-004`；后续 `QA-006`。
- 文件：Compose/health/deploy sandbox specs、backup evidence、port/secret checks、runbook。
- 边界：沙箱不等于生产部署；首版全部功能完成前不得增量部署；不自动回滚数据库；备份只声明命令成功；无生产域名时只验证 production 关闭失败与 localhost development/test HTTP；不重启现有服务。
- 影响：数据：隔离migration/backup；权限：端口/管理；审计：部署记录；缓存/异步/媒体/通知：全栈运维读回。
- 测试/验收：`docker compose config`、隔离up/health/故障注入/backup/deploy dry-run；备份额外核对 `Asia/Shanghai` 周一 03:00（`0 3 * * 1`）、仅 `local` 和一个周实例；记录命令、退出码、健康HTTP与回滚版本。
- 风险/停止：端口额外暴露、秘密进镜像/日志、旧应用不能读新schema或回滚脚本有破坏操作即阻断。
- 证据：在独立 `kaj-p12-qa005` Compose 项目和 `/tmp` bind root 中，串行构建当前源码 `kaj-blog-web/postgres/caddy:qa005`；从空 PostgreSQL 16 库应用 43 条 migration、收集 107 个静态文件，读回 `showmigrations` 为 `43 applied/0 pending`。缺 PostgreSQL/Redis 时 Compose 明确拒绝启动 web，绕过门禁只探测进程时 `/health/live=200`、`/health/ready=503`；依赖恢复后 web/worker/Caddy 均 healthy，唯一 web/worker/beat 各 1，worker 为 `solo/concurrency=1`，经 `127.0.0.1:58080` 的 live、ready、首页均 200。只有 Caddy 发布 loopback HTTP；PostgreSQL、Redis、Mailpit 无主机端口，backend/analytics 网络为 internal。异常终止 Gunicorn master 后 `RestartCount 0→1`，2 秒内恢复 healthy/ready。运行中 RED 发现两份 Caddyfile 同时 delete/set `X-Kaj-Client-IP`，适配后删除覆盖设置并使所有代理请求触发 `ClientIpError` 500；新增适配 JSON 门禁并移除冗余 delete 后 GREEN，伪造无效头仍由 Caddy 覆盖且首页 200。正式 Celery 周备份对隔离库和 47 字节媒体执行成功：TaskRun `succeeded/attempt=1/lease empty`，BackupRecord `COMPLETED/local`、归档 96672 字节、数据库 dump 530834 字节、SHA-256 与文件一致、30 天到期；TAR 仅含 manifest/custom dump/媒体，`pg_restore --list` 识别核心表，重复投递后仍为 1 record/1 task/1 archive。另一个真实 PostgreSQL 聚焦套件验证 schedule 只有一个、UTC 周日 19:00 等价上海周一 03:00、同周幂等与到期清理，退出 0，`2 passed`。部署 planner 的 current/pending dry-run 和 5 个模拟场景全部符合顺序；迁移失败/候选健康失败/旧应用也不健康分别退出 30/40/50，journal mode `0600`，数据库从不自动回滚，维护页只在旧应用也不健康时保持；新增 `previous/candidate/active/rollback_version` 后聚焦合同退出 0，`7 passed`，成功 ID 重跑仅 `already_succeeded`。缺生产域名时 Caddy 退出 78，缺生产密钥时 Django 拒绝启动；维护页契约通过。合并运维回归退出 0，`19 passed in 15.28s`；全仓 Ruff lint、620 文件 format check、Django check、migration drift、Compose/Caddy 守卫与 `git diff --check` 均退出 0。Mailpit 为 0、Celery 队列为 0，所有 TaskRun 终态且租约为空；QA-005 的 7 容器、3 网络、临时库/媒体/归档/部署日志已定向清理，P10/P11/P12 既有容器未重启。沙箱未连接生产、未执行生产备份/migration/部署/重启或 Git 交付；`restore_verified=false` 诚实表示只验证 dump 可读，未做完整恢复演练；部署脚本仍是无生产命令适配器的模拟器，不得解释为真实部署。
- 授权：运行容器/沙箱服务 `是`；生产部署/迁移/重启另行 `是`。

### QA-006 完成需求追踪、架构评审、交付记录与授权门禁
- 元数据：状态 `完成`；阶段 P12；owner `project-governance`；优先级 P0。
- 目标/行为：逐条核对 Q001-Q322、47 份原始文档、3 份施工派生文档和 102 个任务证据；检查 owner/依赖/重复/遗漏；更新 README/运维/迁移/验证记录，形成可部署但未部署的最终交付说明。
- 来源：`reference/03-requirements-traceability.md` 全文；`planning/requirements-todo-traceability.md` 全文；`planning/implementation-readiness.md` 全文；`prototype/page-state-matrix.md` 全文；`05-architecture-study-guide.md` §文档维护；`delivery/03-code-review-checklist.md` 全文；本清单。
- 依赖：前置 `DEC-001`、`DEC-002`、`DEC-003`、`DEC-004`、`DEC-005`、`FND-001`、`FND-002`、`FND-003`、`FND-004`、`FND-005`、`FND-006`、`RUN-001`、`RUN-002`、`RUN-003`、`RUN-004`、`RUN-005`、`RUN-006`、`OBS-006`、`OBS-007`、`ACC-001`、`OBS-004`、`OBS-001`、`ACC-002`、`ACC-003`、`ACC-004`、`ACC-005`、`ACC-006`、`ACC-008`、`ACC-009`、`ACC-010`、`ACC-011`、`MED-001`、`MED-002`、`MED-003`、`MED-004`、`MED-005`、`MED-006`、`MED-007`、`ACC-007`、`CNT-001`、`CNT-002`、`CNT-010`、`CNT-011`、`CNT-003`、`CNT-004`、`CNT-005`、`CNT-006`、`CNT-007`、`CNT-008`、`CNT-009`、`DSC-001`、`DSC-002`、`DSC-003`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`DSC-008`、`CMT-001`、`CMT-002`、`CMT-003`、`CMT-004`、`CMT-005`、`CMT-006`、`CMT-007`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-002`、`OBS-003`、`OBS-005`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-002`、`EXC-003`、`EXC-004`、`EXC-005`、`EXC-006`、`EXC-007`、`AUT-001`、`AUT-002`、`AUT-003`、`AUT-004`、`AUT-005`、`AUT-006`、`ADM-001`、`ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-001`、`QA-002`、`QA-003`、`QA-004`、`QA-005`；后续 无其他 Todo。
- 文件：本Todo索引/阶段状态、README、operations runbook、migration/verification records、review findings。
- 边界：文档不能把未运行项写成完成；不自动git add/commit/push/部署；不修改需求真值来迁就实现；发现漂移先新决策/ADR。
- 影响：数据/权限/审计/缓存/异步/媒体/通知：仅核对全量证据与残余风险。
- 测试/验收：运行 ID/依赖/链接/322 行 coverage/页面矩阵/Goal 脚本、Ruff/pytest/Playwright/Operational 最终命令；代码评审先列发现，逐项关闭或标阻塞。
- 风险/停止：任一P0失败、需求无落点、owner重复、测试过期/缺失或生产值未确认即不得宣布完成/可部署。
- 证据：一次性结构审计退出 0：13 个阶段、102 张任务卡均有 10 个强制字段且全部为 `完成`；555 条前置边与对应后续边无缺失、自环、环、反向阶段边或双向不互认；102 张卡各有且仅有 1 个合法 owner，共 22 个 owner；Q001-Q322、322 行追踪和 322 个 `REQ-Qnnn` 一一对应；47 份原始文档、3 份施工派生文档、两表各 42 个一致 URL name、13 个 Goal/102 Todo 并集、63 个本地 Markdown 链接及本阶段 Goal 附件 `QA-001..006` 均完整。Findings-first 评审发现并关闭 4 个 P1：E2E `/tmp` 目录符号链接越界由共享路径 owner 拒绝；部署 journal 现校验 v1 schema、场景、事件序列、终态和版本字段且兼容完整旧 v1；默认 Playwright 配置只收集 8 个基础错误页用例；390px 编辑器 action bar 改为稳定两列、提交动作整行并满足最多两行和 44px 触控。对应 RED 分别退出 2/1，聚焦 GREEN 为 `2 passed`、部署合同 `9 passed`、移动编辑器 `1 passed (1.3m)`；最终全量 `pytest` 退出 0，`405 passed in 305.48s` 且 0 skip。仅通过 `/usr/local/bin/blog-playwright-cli` 以 `blog-browser`、单 worker 串行验收：授权 `1 passed (2.9m)`、应用 `5 passed (9.0m)`、基础四身份 `8 passed (3.7m)`；应用套件生成并解码 98 张唯一 PNG，390/768/1440=`41/16/41`，并人工检查首页、390 编辑器和 768 管理页。隔离 PostgreSQL 读回账户 5、注册账户 1、深色主题 1、昵称更新 1、收藏 1、缓冲评论 1、已发布文章 1、已取消导出 1、审计 8，导出请求/取消各 1。最终 `ruff check .`、`ruff format --check .`（622 files）、`manage.py check`、`makemigrations --check --dry-run`、`npm run build`、`docker compose config --quiet`、Compose/Caddy 守卫、部署合同和 `git diff --check` 均退出 0。隔离测试库、Redis DB 13/14/15、Mailpit、浏览器状态、截图、输出目录和本任务进程均已定向清理；P10/P11/P12 九个既有容器启动时间未变且 `RestartCount=0`。README 与运维、备份、迁移、部署文档已统一为当前源码候选满足部署前门禁但尚未部署；未配置生产域名、管理员邮箱、Resend 身份或密钥，未执行生产 migration、备份、恢复演练、部署或服务重启，`restore_verified=false`，部署入口仍是 fail-closed 规划器/模拟器而非生产命令适配器。QA-006 验收期间未执行 Git add/commit/push；后续 Git 动作按独立授权执行。
- 授权：文档/审查 `否`；git add/commit/push、生产备份/迁移/部署/重启均 `是`。

[返回总索引](../implementation-todolist.md)
