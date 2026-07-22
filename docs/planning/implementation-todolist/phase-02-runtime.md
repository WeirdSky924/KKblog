# P2 运行时与跨域基础（8）

退出门禁：Compose 运行入口、健康检查、TaskRun/CapacityPolicy 基础和静态模板均可在隔离环境验证。

### RUN-001 定义镜像、Compose 服务、内网与持久卷
- 元数据：状态 `完成`；阶段 P2；owner `docker`；优先级 P0。
- 目标/行为：声明 `web/postgres/redis/worker/beat/caddy/umami/mailpit`，数据落到项目 `var/`，内部服务无公网端口。
- 来源：访谈 Q214-Q215、Q265-Q268；`architecture/README.md` §运行时；`04-operations-testing.md` §容器和端口。
- 依赖：前置 `FND-002`；后续 `RUN-002`、`RUN-003`、`RUN-005`、`EXC-007`、`QA-005`、`QA-006`。
- 文件：`compose.yaml`、`docker/web/Dockerfile`、`.dockerignore`、卷/网络配置、`var/.gitignore`。
- 边界：不启动容器、不创建卷/数据库；development/test 的 HTTP 80 仅限 `localhost`；production 仅在 DEC-002 必需实值齐全后允许对外 80/443，其他服务端口始终不公开。
- 影响：数据：PostgreSQL/媒体/备份卷布局；缓存：Redis；异步：worker/beat；其余由后续接线。
- 测试/验收：`docker compose config --quiet`、镜像非 root/最小权限检查、端口静态断言；无秘密烘入镜像。
- 风险/停止：任何数据库/Redis/Mailpit/Umami 公网绑定、覆盖现有 `var/` 或不明确宿主路径时停止。
- 授权：配置编写 `否`；构建、启动、停止容器 `是`。
- 证据：RED `docker compose config --quiet` 在实现前因缺少配置退出 1。新增 `compose.yaml`、多阶段非 root Web 镜像、`.dockerignore`、项目 `var/.gitignore` 与结构化 `docker/scripts/verify_compose.py`；GREEN 两条 Compose 命令均退出 0，读回 8 个精确服务、唯一 `127.0.0.1:80` 宿主端口、internal backend、全部 bind 源位于项目 `var/`，数据库/Redis/Mailpit/Umami 端口为 0。授权安装 Docker 29.1.3、Compose 2.40.3、Buildx 0.30.1 并启用 daemon；本轮镜像代理仅作 build arg，默认仍为标准镜像名。`docker build` 最终退出 0，锁定安装 9 个生产包并完成 Tailwind/esbuild；镜像 inspect 退出 0，读回 65,207,361 bytes、linux/amd64、`USER 10001:10001`、Gunicorn CMD，配置环境无项目秘密。回归 Ruff/format（51 文件）、Django check、`uv lock --check`、npm build/audit、秘密扫描和 `git diff --check` 均退出 0。按本卡边界未启动项目容器、创建卷/数据库/项目网络；读回仅有 Docker 内置三个网络、`var/.gitignore`，项目容器与卷为 0。Docker Hub/官方 PyPI 在本机极慢，最终用同 digest 的只读镜像代理完成构建；后续运行验证仍须显式覆盖镜像来源且不得写成生产默认。

### RUN-002 接通 PostgreSQL、Redis、Mailpit、Gunicorn 与 Celery 入口
- 元数据：状态 `完成`；阶段 P2；owner `config`；优先级 P0。
- 目标/行为：各进程使用同一 settings/schema；开发邮件进入 Mailpit；Redis 可清空；worker/beat 入口可启动但不复制业务规则。
- 来源：访谈 Q153-Q157、Q214、Q223-Q225；ADR-004；`modules/01-platform-foundation.md`。
- 依赖：前置 `RUN-001`、`FND-003`；后续 `RUN-004`、`OBS-006`、`ACC-003`、`CNT-004`、`CMT-004`、`QA-005`、`QA-006`。
- 文件：`config/{wsgi,asgi,celery}.py`、Gunicorn/worker entrypoint、服务环境模板。
- 边界：不创建业务 migration/生产库；Redis 不持久化业务事实；Mailpit 不对公网。
- 影响：数据：连接契约；缓存：Redis；异步：Celery；通知：开发邮件；权限/审计/媒体无。
- 测试/验收：隔离 Compose 中 Django DB ping、Redis set/flush 后正确退化、Mailpit 捕获测试邮件、真实 worker smoke task。
- 风险/停止：误连生产主机、broker 重启导致永久状态丢失或邮件发往外部时停止。
- 授权：运行容器/真实服务 `是`；隔离配置与测试代码 `否`。
- 证据：RED `PATH=/root/.local/bin:$PATH uv run python -c 'from config.celery import app'` 在入口缺失时退出 1；实现 `config/celery.py`、`config/runtime_tasks.py`、Celery settings、开发环境模板，并为 Gunicorn 显式禁用只读容器不可用的 control socket。GREEN `uv sync --locked`、Ruff/format、Django check、Compose JSON 守卫均退出 0；真实镜像构建退出 0，inspect 读回 `USER 10001:10001`、Gunicorn 命令和 Celery smoke 任务注册。隔离 Compose 只启动 `postgres redis mailpit web worker beat`（无 Caddy/Umami、无迁移），PostgreSQL 容器健康且 Django `SELECT 1` 读回数据库 `kaj`、用户 `kaj`、时区 `UTC`；Redis set/read/delete 读回成功，重启后临时标记为 `None`；Mailpit API 读回唯一邮件 `no-reply@kaj.test -> admin@kaj.test`；真实 worker `config.runtime_tasks.smoke` 返回 UUID probe 与 `status=ok`、状态 `SUCCESS`，Redis 重启断线后 worker 日志读回自动重连并再次 smoke 成功。服务端口均未宿主发布；未执行 migration、生产邮件或生产数据库操作。镜像拉取因 Docker Hub 超时使用显式代理覆盖，未改生产默认；运行数据在本地隔离目录并于验收后清理。

### RUN-003 配置 Caddy 的 HTTP 测试、未来 HTTPS 与受控文件发送
- 元数据：状态 `完成`；阶段 P2；owner `docker`；优先级 P0。
- 目标/行为：development/test 只通过 `localhost` HTTP 验证；production 必须有真实域名并使 80 跳 443，缺生产域名时不启动公网站点；管理端同源；私有媒体/导出经 Django 授权后内部发送。
- 来源：访谈 Q141-Q147、Q215、Q266-Q267；`data/05-storage-lifecycle.md` §服务器目录；DEC-002。
- 依赖：前置 `RUN-001`、`DEC-002`；后续 `RUN-004`、`ACC-010`、`MED-004`、`EXC-007`、`QA-005`、`QA-006`。
- 文件：`docker/caddy/Caddyfile`、环境模板、受控 internal redirect 约定。
- 边界：不签发真实证书、不开放额外端口、不让 Caddy 任意静态暴露私有媒体或归档。
- 影响：权限：同源与文件授权边界；媒体：传输；缓存：只允许明确公开不可变资产；其余无。
- 测试/验收：配置静态校验；隔离请求验证 localhost Host、production 缺域名关闭失败、有域名时 HTTP→HTTPS redirect 和未授权私有路径 404/403。
- 风险/停止：真实客户端 IP 信任链无法确认、目录 alias 越界或管理/Umami 绕过认证时停止。
- 授权：配置 `否`；绑定 80/443、证书或重载 Caddy `是`。
- 证据：RED 为基础 Compose 的 Caddy 无配置入口，实际 localhost 请求不可代理；实现专用 Caddy 镜像、development/production Caddyfile、production Compose override、启动 fail-closed gate 和结构化 `verify_caddy.py`。`caddy validate` 对两套配置均退出 0；基础 Compose 守卫读回仅 `127.0.0.1:80`，production contract-only 渲染读回仅 `0.0.0.0:80/443`，web/worker/beat 共用 production settings，Caddy 环境不含数据库、Redis、Resend key 或 Django secret；逐项删除 12 个 production 必填变量均配置失败。入口缺域名、保留域名、URL/host 不一致分别退出 78。隔离真实请求读回 localhost 200、伪造 Host 421、直接 media/export 404；受控 `/_kaj/media/*` 先删除客户端存储键再 forward-auth，授权探针返回的 `X-Kaj-Storage-Key` 读回精确文件内容和 200，拒绝探针下伪造同名头仍为 403。一次性 production Caddy 仅绑定 `127.0.0.1:18080`，ACME 指向不可达 loopback，真实 HTTP 请求读回 301 与保留 path/query 的 HTTPS Location，未申请证书、未绑定公网 80/443。测试探针、容器、网络和运行目录均已清理；production 仍缺真实域名/身份/密钥，按设计不可启动，这是保留的安全边界。

### RUN-004 实现 live/ready、依赖就绪与自动重启策略
- 元数据：状态 `完成`；阶段 P2；owner `operations`；优先级 P0。
- 目标/行为：`/health/live` 只证进程，`/health/ready` 检查数据库/必要 schema/关键依赖；Compose 按健康依赖并在异常/重启后恢复。
- 来源：访谈 Q183-Q184、Q268-Q270；`modules/01-platform-foundation.md` §启动门禁；`04-operations-testing.md`。
- 依赖：前置 `RUN-002`、`RUN-003`；后续 `RUN-006`、`OBS-010`、`QA-005`、`QA-006`。
- 文件：health view/query、URL、Compose healthcheck、dependency/restart 配置。
- 边界：健康响应不泄露版本、堆栈、连接串/容器名；进程存在不等于 ready。
- 影响：数据：schema ready 读；权限：健康最小公开面；异步：服务状态；通知由 OBS-007；其余无。
- 测试/验收：数据库未就绪/迁移缺失/依赖恢复场景；真实 HTTP 返回码和 Compose health 状态一致。
- 风险/停止：健康检查具有写副作用、依赖循环或假绿色时停止上线。
- 授权：配置/隔离测试 `否`；重启真实服务 `是`。
- 证据：RED `pytest apps/operations/tests/test_health.py -q` 因 `apps.operations.services` 缺失在收集期退出 2；建立 operations owner 的只读 PostgreSQL `SELECT 1`、migration plan、Redis ping 服务与 `/health/live`、`/health/ready` 安全 JSON 入口。聚焦 GREEN/架构回归 7 passed，Ruff/format、Django check、Compose/Caddy 守卫均退出 0。fresh Compose 数据库读回 `django_migrations` 不存在，真实 HTTP live 为 200、ready 为 503 且只含 `status=unavailable`，Web health 最终 unhealthy，Caddy `service_healthy` 前置以退出 1 拒绝启动。真实 integration 初次因 test settings 未暴露统一 `REDIS_URL` 退出 1；修复后 disposable PostgreSQL 自动测试 schema 读回数据库/用户、migration plan 为空，Redis DB 15 ping 为真，ready 200，1 passed。一次性非 root/read-only Web+Caddy 环境中，Redis pause 时 live 200、ready 503、Caddy health unhealthy；unpause 后 ready 200、Caddy healthy；容器内部终止 Gunicorn master 后退出 137，`unless-stopped` restart count 从 0 变 1 并恢复 ready 200。未对项目或生产库执行 `manage.py migrate`；pytest 自动测试 migration 随一次性容器删除，全部项目/探针容器和运行目录已清理。残余边界：真实生产 schema/域名未配置，按设计仍不可启动。

### RUN-005 建立静态资源构建、基础模板、404/500 与维护页
- 元数据：状态 `完成`；阶段 P2；owner `core`；优先级 P0。
- 目标/行为：Tailwind/HTMX/Alpine/Lucide 基础加载；三主题 token、全局反馈、错误页、维护页在桌面/手机可用。
- 来源：访谈 Q166-Q173、Q185-Q186、Q219-Q222；`03-frontend-design-system.md` §Token/页面骨架/响应式；原型。
- 依赖：前置 `FND-004`、`FND-006`、`RUN-001`；后续 `MED-005`、`DSC-001`、`ADM-001`、`QA-005`、`QA-006`。
- 文件：Tailwind/JS build、`templates/base.html`、`templates/errors/`、`templates/maintenance.html`、共享反馈组件。
- 边界：不实现品牌导航/通知业务；不引入 SPA、营销 Hero、渐变/大圆角/卡片嵌套。
- 影响：权限：错误隐私；缓存：静态指纹；其余业务影响无。
- 测试/验收：构建命令、模板检查；Playwright 1440/390/768、三主题、键盘、焦点、长错误码、无横向溢出。
- 风险/停止：CSP/静态依赖失效、文本重叠、焦点不可见或错误页泄露内部信息时停止后续 UI。
- 证据：RED `pytest tests/contracts/test_frontend_foundation.py -q` 在修正测试 URLconf handler 接线后稳定退出 1、5 failed，准确读回缺少 `base.html`、维护页、共享反馈、生产静态指纹和 Caddy 静态路由。最小实现复用 `core` 错误 owner，新增基础/维护/反馈模板、外部同源主题预载与 HTMX/Alpine/Lucide 单一入口、淡杏酒红 light/dark/eye-care 语义 token、409/422 partial 交换、错误来源焦点恢复和 reduced-motion；production 使用 Manifest 指纹，Caddy development 不缓存、production 仅作为指纹 URL 长缓存入口，Compose Web 共享项目 `var/staticfiles` bind。GREEN 前端构建退出 0（theme 298 bytes、app 112,899 bytes），聚焦 6 passed；Manifest `collectstatic` 在临时目录真实读回 CSS/theme/app 三个不同哈希文件且无 `static/src`，真实 Caddy 读回 CSS/JS 200、`no-cache`、缺失静态/私有路径 404、伪造 Host 421，两套 Caddy validate 与重建镜像均退出 0。`/usr/local/bin/blog-playwright-cli` 真实验收 390 dark 500、768 eye-care maintenance、1440 light 404、390 light HTMX 422、成功反馈和 184 字符 trace：三主题/字体/Lucide 均加载，横向溢出 0，按钮高 44px，秘密泄露 false，Tab 焦点环 3px，Enter 返回并恢复来源焦点，反馈关闭恢复区域焦点；原始截图检查无重叠/裁切后已清理。既有 E2E 5 passed、3 skipped（accounts 阶段身份状态尚不存在），相关 Python 回归 15 passed；Ruff/format 65 文件、Django 两环境 check、Compose/Caddy 守卫、uv lock、npm build/audit、`git diff --check` 和边界化秘密扫描均退出 0/无漏洞或秘密命中。未执行 migration、生产域名/邮件/备份、部署、Git 提交或推送；维护切换由 `RUN-006` 接线，生产仍缺真实 DEC-002 值并按设计 fail closed。
- 授权：`否`。

### RUN-006 编写可模拟的部署/迁移/回滚脚本骨架
- 元数据：状态 `完成`；阶段 P2；owner `operations`；优先级 P1。
- 目标/行为：把“检测 migration→备份→维护→迁移/切换→健康→应用回滚”编码成显式、幂等、可 dry-run 的步骤。
- 来源：访谈 Q179-Q186；`flows/04-import-export-sequences.md` §部署门禁；`modules/10-exchange-analytics-maintenance.md` §部署。
- 依赖：前置 `RUN-004`、`FND-006`；后续 `EXC-006`、`QA-005`、`QA-006`。
- 文件：`docker/scripts/deploy*`、migration 检测/维护页切换/健康/回滚脚本、运维说明。
- 边界：本任务只写和模拟；不执行迁移、不重启/切换真实服务、不回滚数据库、不部署。
- 影响：数据：迁移前备份门禁；审计：部署记录；异步/通知：失败接 OBS；其余无。
- 测试/验收：shell/static lint；假命令模拟无迁移、迁移失败、健康失败、旧应用恢复；每步保留退出码。
- 风险/停止：脚本包含 `down -v`、宽泛进程终止、不可逆迁移或未验证路径删除时立即停止。
- 授权：脚本 `否`；生产备份、迁移、部署、重启、切换 `是`。
- 证据：RED `uv run pytest tests/contracts/test_deploy_skeleton.py -q`（在 `.venv` 等价锁定环境复核）退出 1，7 项均因 `docker/scripts/deploy` 缺失而失败。实现 `docker/scripts/deploy`/`deploy.py` 和 `docs/operations/deployment.md`：仅接受 dry-run 或预定义本地模拟，不执行 shell/网络/容器/数据库命令；以原子替换写 `0600` JSON journal，拒绝路径穿越、符号链接、损坏/未完成日志，成功 ID 重放幂等，事件仅含 step/outcome/exit_code。GREEN `.venv/bin/pytest tests/contracts/test_deploy_skeleton.py -q` 7 passed、`bash -n`、Ruff check/format、compileall、`git diff --check`、Compose/Caddy 守卫均退出 0；锁定 `uv 0.11.30` 离线复核同样退出 0。模拟读回 dry-run 无状态目录；成功退出 0/status succeeded/maintenance false；迁移失败退出 30 且未切候选；候选健康失败退出 40、应用恢复且 `database_rollback_attempted=false`；旧应用不健康退出 50 且维护保持启用；重放只返回 `already_succeeded`；journal mode 0600。相关前端/HTTP 回归 15 passed，development Django check 与生产 `check --deploy`（随机进程内值）退出 0；生产缺真实 DEC-002 值仍 fail closed。未执行真实部署、生产备份/迁移/重启/服务切换、真实邮件、Git 交付。

### OBS-006 建立 TaskRun、三次退避与租约基础
- 元数据：状态 `完成`；阶段 P2；owner `operations`；优先级 P0。
- 目标/行为：所有 Celery 入口记录幂等键、attempt、状态和时序；统一执行 1/5/30 分钟加抖动、最多三次、租约和异常释放；最终失败只写 TaskRun 终态和 `task.final_failed` 事实事件。
- 来源：访谈 Q224-Q225；`contracts/05-background-tasks.md` §统一协议/Lease/任务测试；`modules/09-notifications-observability.md` §TaskRun。
- 依赖：前置 `RUN-002`、`FND-005`、`FND-006`；后续 `MED-006`、`CNT-004`、`CNT-008`、`CMT-004`、`CMT-006`、`OBS-009`、`OBS-010`、`EXC-003`、`EXC-005`、`EXC-006`、`EXC-007`、`ADM-008`、`QA-001`、`QA-004`、`QA-006`。
- 文件：TaskRun model/service/task wrapper/lease recovery/final-failure event schema/tests。
- 边界：任务只调可重入 service；PostgreSQL 约束/租约为裁决，Redis 锁仅优化；不在本任务实现 RuntimeError、通知或邮件；修 BUG 后新幂等键，不网页重跑。
- 影响：数据：TaskRun/lease；权限：admin 只读；审计由任务 owner 后续接入；缓存可选锁非事实；异步核心；媒体任务关联；通知仅产生事实事件。
- 测试/验收：首成、重复、双 Worker、2 败 1 成、3 败、提交前后崩溃、对象中途变；真实隔离 Worker smoke，读回 TaskRun 和事件终态。
- 风险/停止：eager 测试冒充 broker 证据、失败被标成功或租约永不释放即停止所有后台任务接入。
- 授权：代码/隔离worker `否`；运行真实worker `是`。
- 证据：RED `.venv/bin/pytest apps/operations/tests/test_task_runs.py -q` 退出 2，收集期准确报告唯一 owner `apps.operations.models` 缺失。实现 `TaskRun`/migration、operations task service、1/5/30 分钟加最多 10% 注入 jitter、PostgreSQL 唯一幂等与 lease/heartbeat/过期恢复、薄 Celery adapter、版本化 `task.final_failed.v1` schema，并把现有 smoke 入口接入；没有 RuntimeError、通知、邮件或 Redis 最终裁决。真实 PostgreSQL 16 聚焦 GREEN 12 passed，覆盖首成/重复、两败一成、三败终败、双 Worker、外层提交前回滚、提交后硬崩溃、第三次硬崩溃终败、对象中途变化、heartbeat、jitter、Celery eager 接线及 AST 入口守卫。隔离 migration 退出 0，catalog 读回 `operations_task_run`、唯一幂等、attempt/lease/completion 约束和两个条件索引；非 root/read-only 真实 Worker 经 Redis broker 两次接收同一 probe，均返回成功，PostgreSQL 只读回一条 `succeeded/attempt=1/lease cleared/completed` TaskRun，Redis 队列为 0。独立三次失败读回 `final_failed/attempt=3/lease cleared`，恰好一条 pending Outbox 事实，payload 私密字符串命中 false。相关 operations/contracts/health 回归 69 passed；Ruff/format 75 文件、compileall、migration drift、Django check、Compose/Caddy 守卫和 `git diff --check` 均退出 0。Worker/Redis/PostgreSQL 仅绑定 loopback 或 host 内部访问，临时库/tmpfs/容器/端口/volume 已全部删除；未连接共享/生产数据，未发送邮件、执行生产迁移、部署、重启项目服务或 Git 交付。

### OBS-007 建立统一 CapacityPolicy 与同步门禁
- 元数据：状态 `完成`；阶段 P2；owner `operations`；优先级 P0。
- 目标/行为：提供统一、可注入的 CapacityPolicy 与同步门禁；既有内容继续可读，<5%禁止图片创建，<2%禁止所有新文字/图片，所有写服务在可信服务端重判。
- 来源：访谈 Q269-Q272；`data/05-storage-lifecycle.md` §磁盘保护；`modules/09-notifications-observability.md` §容量/告警；DEC-002。
- 依赖：前置 `FND-003`、`FND-004`；后续 `MED-002`、`OBS-010`、`EXC-006`、`ADM-008`、`QA-001`、`QA-004`、`QA-005`、`QA-006`。
- 文件：CapacityPolicy/state contract、同步 gate、health service adapter、policy tests。
- 边界：本任务不负责周期采样、告警、邮件或恢复通知；不阻止既有内容读取；审计/错误保留最低写通道；前端按钮不是门禁。
- 影响：数据：容量状态接口；权限：全写门禁；审计由状态采样任务记录；缓存无事实；异步由 OBS-010；媒体：5%/2% 门禁；通知由 OBS-009/010。
- 测试/验收：10/5/2% 边界和直接 POST 门禁；隔离容量样本下所有 policy consumer 读回同一结果。
- 风险/停止：门禁在服务端缺失、既有内容被错误阻断或错误日志通道被容量策略阻断即停止后续写服务。
- 授权：代码/模拟 `否`；真实容量采样、告警邮件和生产门禁 `是`。
- 证据：RED `.venv/bin/pytest apps/operations/tests/test_capacity.py -q` 退出 2，收集期准确报告 `apps.operations.services.capacity` 缺失。实现 operations 唯一 `CapacityPolicy`/`CapacityGate`/state/sample/health snapshot contract，使用整数比例严格判定 `<10% WARN`、`<5% NO_IMAGE`、`<2% READ_ONLY`；sample source 可注入且每次写前重读，既有读取和 `DIAGNOSTIC_WRITE` 永远允许，新增两个统一 503 安全错误码与运维消费者说明。GREEN 聚焦 13 passed，覆盖 10/5/2% 精确边界、无效/naive sample、READ_ONLY 诊断最低通道、恢复后自动解除、三个 consumer 同结果，以及真实 Django direct POST 在命令调用前拒绝图片/文字并返回已确认文案；相关错误/前端回归 21 passed。全仓 Ruff/format 77 文件、compileall、development Django check、migration drift、Compose/Caddy 守卫和 `git diff --check` 均退出 0；源码扫描确认阈值/状态只存在 operations owner、core 错误 registry 和测试。按边界未新增 Capacity 持久表、真实磁盘采样、周期任务、告警、通知、邮件或生产门禁；无页面模板变化，复用 RUN-005 已浏览器验收的统一 503 页。

## 阶段总审计（2026-07-22）

- 状态与拓扑：结构化读回 102 张任务卡；P2 精确为 `RUN-001..006/OBS-006..007` 8 项且全部完成。缺失 ID、未来阶段前置、依赖环、P2 前后关系不对称、Q 来源追踪缺口和同时进行中的 Todo 均为 0；P0/P1/P2 非完成项为 0。
- 数据与回归：全新 loopback PostgreSQL 16、Redis DB 15、Mailpit 环境中 `./scripts/test` 退出 0，`86 passed`。测试后 PostgreSQL 临时测试库与基础库表均为 0，Redis DB 15/0 均为 0，Mailpit 消息为 0；三只一次性容器、tmpfs 与四个宿主端口均已删除/释放。
- 静态与运维：Ruff check/format（77 文件）、compileall、Django check、migration drift、Compose/Caddy 守卫、`uv lock --check`、npm build/audit、shell syntax 和 `git diff --check` 均退出 0；owner/import 守卫包含在全量 pytest 中。Compose 读回 8 个服务、唯一 loopback HTTP、internal data plane、项目 `var/` bind、应用只读 rootfs/全 capability drop；production 合约继续对缺失 DEC-002 实值关闭失败。
- 浏览器：RUN-005 卡内已有同一实现的 `5 passed, 3 skipped`、390/768/1440、三主题、键盘/焦点和原始截图检查证据。本次阶段复核中 `/usr/local/bin/blog-playwright-cli` 直接打开 fixture、语义快照和关闭成功，但 `scripts/test-e2e` 在 1.6 GiB 无 swap 主机上多次因嵌套 CLI 的 Chrome/daemon 进入 `folio_wait_bit_common`，最终报 `spawnSync ... ETIMEDOUT` 或 `Session closed`，未产生新的页面断言结果；按三次停止条件记录为当前环境阻塞，不把失败复核记为 GREEN。失败结果、浏览器 session/profile 和 server 已清理，登录身份仍按 P3 前置明确跳过。
- 未执行与风险：未执行生产 migration/数据库、真实邮件、真实备份、部署/服务切换、生产域名/证书、Umami 业务集成或 Git add/commit/push/merge。残余风险为低内存主机上的固定 E2E 入口需在资源恢复后复跑；生产所需真实 DEC-002 值仍缺失并按设计关闭失败。

[返回总索引](../implementation-todolist.md)
