# Validation History

| Date | Command/Check | Result | Notes |
| --- | --- | --- | --- |
| 2026-10-12 | README internal-link and source review | passed | All 14 unique README link targets exist; usage metrics were checked against dated release records, deployment revision against the 2026-10-11 execution record, and P0 state against its execution file. |
| 2026-10-12 | `git diff --check` | passed, exit `0` | Documentation-only changes in `README.md`, architecture, operations, and implementation status summaries. No test suite or Labs runtime was started. |
| 2026-10-11 | Quiz RED compatibility test: DB column default for old application writer | failed as RED, exit `1` | Before `0015`, PostgreSQL `column_default` was `NULL`; this reproduced old-version insert incompatibility. |
| 2026-10-11 | `./scripts/test apps/learning/tests/test_quiz_modes.py::test_quiz_attempt_mode_has_database_default_for_previous_app_versions -q` | passed, exit `0` | `1 passed in 77.14s`; after adding `db_default=EXAM` and migration `0015`, isolated PostgreSQL readback returned `'EXAM'::character varying`. |
| 2026-10-11 | `./scripts/test apps/learning/tests/test_quiz_modes.py apps/learning/tests/test_quiz_order.py apps/learning/tests/test_quiz_records_t18.py -q` | passed, exit `0` | `15 passed in 94.78s`; isolated PostgreSQL/Redis/Mailpit. |
| 2026-10-11 | Focused adapter/Worker and incremental-image contract tests | passed, exit `0` | Adapter/Worker suite `35 passed`; after the incremental Dockerfile guard fix, `tests/contracts/test_incremental_image.py` `1 passed`. The redundant Caddy maintenance contract was removed after confirming Nginx owns public ingress. |
| 2026-10-11 | Django check and migration drift | passed, exit `0` | `manage.py check`: no issues; `makemigrations --check --dry-run`: no changes detected. |
| 2026-10-11 | Ruff, JavaScript syntax, frontend build, and diff check | passed/partial | Target Ruff check and format pass after formatting; `node --check` for quiz/home navigation, `npm run build`, and `git diff --check` exited `0`. `app.js` output about 1.1 MB. |
| 2026-10-11 | Labs `learning.0015_quiz_attempt_mode_db_default` migration | passed, exit `0` | Applied through the Labs service environment; P12 DB readback confirmed both `0014`/`0015` and database default `'EXAM'`. |
| 2026-10-11 | Production preflight readback | passed, exit `0` | Original Web/Worker/Beat `42adeb4ceb74`, learning leaf `0013`; live/ready `200`; exactly 35 enabled stale sources (26 socket, 8 parser, 1 timeout), no active check run. |
| 2026-10-11 | Nginx production maintenance gate | passed, exit `0` | Host Nginx `/run/kaj-production-maintenance.enabled` produced public `503`, `Cache-Control: no-store`, `Retry-After: 120`; direct Web loopback with Nginx Host/forwarding headers returned live/ready `200`. Marker was removed after final page/health readback. |
| 2026-10-11 | PostgreSQL, media, and Compose backups | passed, exit `0` | Dump `262,962,700` bytes, SHA-256 `9dae86c6…`, mode `0600`, `pg_restore --list` 1043 items; media archive `7,056,912` bytes/418 entries, SHA-256 `d5e7a08d…`; runtime/database Compose snapshots both mode `0600`. |
| 2026-10-11 | Candidate production preflight | passed, exit `0` | `check --deploy` no issues; migration drift `No changes detected`; `migrate --plan` lists only `learning.0014` and `0015`. `learning_quiz_attempt` has 10 rows and 212,992 bytes total relation size. |
| 2026-10-11 | Caddy maintenance experiment | partial, not used as public gate | Production runtime uses `Caddyfile.development` behind Nginx; Nginx owns the public marker. Caddy image restored to `2cbead0`; no Caddy-specific maintenance switch remains in final source. |
| 2026-10-11 | Versioned production browser runtime and Worker socket | passed, exit `0` | Browser runner `d06af75` includes the previously missing Feishu tenant contracts; Node contract suite `19 passed`. Systemd sandbox active/running, socket `0660` UID/GID `999:10001`; Worker container device/inode matches host and health is healthy. |
| 2026-10-11 | Production migration and application switch | passed, exit `0` | Applied `learning.0014` and `0015`; DB constraint and `'EXAM'::character varying` default read back, 10 old attempts are EXAM. Web/Worker/Beat all `d06af75a9c31`, healthy/running, restart 0; `collectstatic`: 168 copied, 4 post-processed. |
| 2026-10-11 | Targeted production source checks | partial, exit `0` | 35 distinct source runs through existing domain service: 30 `SUCCEEDED/HEALTHY`, 1 `TRUNCATED/DEGRADED`, 4 `FAILED/STALE` (Qcraft timeout, 2 Hotjob response invalid, 1 Meituan response invalid). No direct source status SQL updates, daily full check or Provider/AGENT. No active runs remain. |
| 2026-10-11 | PostgreSQL recovery during source checks | warning | Two PostgreSQL server backends exited with code 2; PostgreSQL performed WAL recovery automatically. Container restart count 0, OOM false, kernel logs showed no OOM, health and subsequent queries recovered. Root cause unknown; investigate separately before another large source batch. |
| 2026-10-11 | Public readback and Labs shutdown | passed, exit `0` | Nginx marker removed; public root/jobs/live/ready/CSS/JS returned `200`; anonymous quiz entry redirected to login `302`. Labs Web/Worker/Beat/Outbox service and timer inactive/dead; P12 PostgreSQL/Redis/Mailpit exited without volume deletion. |
| 2026-10-10 | `.venv/bin/pytest apps/opportunities/tests/test_dahua_adapter.py apps/opportunities/tests/test_beisen_adapter.py apps/opportunities/tests/test_getui_adapter.py apps/opportunities/tests/test_hotjob_adapter.py apps/opportunities/tests/test_meituan_adapter.py tests/contracts/test_opportunity_container_runtime.py -q` | passed, exit `0` | `35 passed in 1.17s`；覆盖四个修复适配器、Meituan 相关回归和 Worker Compose contract。固定入口 `uv` 不在本机 PATH，使用 Labs worktree 现有 `.venv/bin/pytest`，没有安装依赖。 |
| 2026-10-10 | Labs 五种来源直接适配器探针 | passed/partial | SafeHttpClient + robots.txt、请求间隔 2 秒；只输出状态、字节数、行数、页数和 complete/truncated，不保存岗位正文、不写 DB。Dahua `144/1 complete`、Getui `5/1 complete`；Beisen `60/3`、Hotjob `30/2`、Meituan `25/5` 均由本次页数上限标记 truncated，未报 parser 错误。 |
| 2026-10-10 | `.venv/bin/ruff check`（本轮 9 个 Python 源码/测试文件） | passed, exit `0` | `All checks passed!`。 |
| 2026-10-10 | `.venv/bin/ruff format --check`（本轮 9 个 Python 源码/测试文件） | passed, exit `0` | 首次检查仅提示两处新增断言格式；定向格式化后 9 个文件均已格式正确。 |
| 2026-10-10 | 目标文件 `git diff --check` | passed, exit `0` | 只检查本轮 `apps/opportunities/checks/`、其聚焦测试、`compose.yaml` 与 container contract。 |
| 2026-10-10 | `systemctl show kaj-labs.service ...` 与 `curl --max-time 10 .../health/live` | passed, exit `0` | Labs 工作目录仍为活动 worktree、服务 `active/running`、live `200`；Labs 无 Worker/浏览器沙箱。 |
| 2026-10-10 | 生产 Worker 只读发布前状态：`docker inspect`、浏览器 systemd/socket `stat`、Celery `inspect.active/reserved` | passed, exit `0` | Worker 当前 `running/healthy`，活动和 reserved 任务数均为 `0`；浏览器服务 `active/running`、宿主 socket 存在。现运行 healthcheck 仍只看 Celery 进程，正式配置位于受保护的 runtime Compose 快照。 |
| 2026-10-10 | 正式镜像构建/切换、Worker 重建、生产招聘任务、migration、Provider/AGENT、Git 提交/推送 | not run | 用户要求 Labs 成功后更新生产；Labs 验证已过。正式部署仍需形成远端可追溯候选，Git 写权限待用户明确授权；生产数据库未写入。 |
| 2026-10-10 | `docker exec kaj-production-worker-1 python -c 'from config.celery import app; print(app.conf.task_time_limit, app.conf.task_soft_time_limit)'` | passed, exit `0` | 生产 Worker 运行时读回 `None None`；未触发 Celery 任务或 Provider/AGENT。 |
| 2026-10-10 | 生产只读 SQL 聚合（`docker exec --user postgres kaj-production-postgres-1 ... psql`） | passed, exit `0` | `BEGIN READ ONLY` + `statement_timeout=5s`。最新 18:00 run 为 `PARTIAL`，129 个来源（93/35/1/0），TaskRun `succeeded`、attempt 1、1810 秒；失败码聚合显示 browser unavailable 26、response invalid 8、request timeout 1。近 30 天 collection timeout 1 条。只读取状态、错误码、计数与时间，不取岗位正文。 |
| 2026-10-10 | `systemctl show kaj-labs.service -p ActiveState -p SubState -p WorkingDirectory --no-pager`；`docker ps --format ...` | passed | 只读确认 Labs 工作目录以及生产容器运行状态；生产 Worker 镜像标记 `42adeb4ceb74`。 |
| 2026-10-10 | 招聘定时任务执行、Provider/AGENT、生产写入/migration/部署/重启、Git 写操作 | not run | 用户只询问失败是否由时限导致；本轮限定为源码和生产只读聚合诊断。 |
| 2026-10-10 | 生产 Worker/socket 只读对照：`docker inspect`、容器内 `Path.stat/is_socket`、宿主 `stat`、`systemctl show` | passed, exit `0` | Worker mount source/destination 均为 `/run/kaj-opportunity-browser`，但容器目录 inode `26:10264108` 与宿主 `26:13168080` 不同；容器内 socket 缺失，宿主 socket 存在且 `0660`, UID `999`, GID `10001`。Worker 创建早于浏览器 systemd 服务启动。 |
| 2026-10-10 | 生产 PostgreSQL 最近 7 个定时 run 的来源连续失败聚合 | passed, exit `0` | `BEGIN READ ONLY` + 5 秒 statement timeout；浏览器失败 26 个来源、parser 错误 8 个来源均 `7/7`。parser 错误分布 Hotjob 3、Getui 2、Dahua/Meituan/Beisen 各 1。没有读取正文或响应体。 |
| 2026-10-10 | Worker 容器重建、浏览器来源 smoke、招聘来源访问 | not run | Worker 重建属于生产重启/服务切换，受先前明确限制；招聘来源访问也仍被禁止。需要当前回合授权后才能进行。 |
| 2026-10-10 | `npm run build:js`、`node --check static/src/home-navigation.js`、`git diff --check` | passed | 三项均退出码 `0`；app bundle 构建完成，源码语法与差异检查通过。 |
| 2026-10-10 | 首页导航 Playwright 用户流 | passed | Labs `/` 手动展开主页导航并点击分区链接；390/768/1440 视口下 `data-home-articles.getBoundingClientRect().top` 与站点头部高度相同（`189/189/81px`），桌面深处滚动路径也对齐。无横向溢出，console errors/warnings `0`。 |
| 2026-10-10 | Labs 首页脚本/服务读回 | passed | 本地及公网 `app.js` SHA-256 均为 `073bcfdd44078dcf37faf455f50a9ca361ecb8ff4eb0c17188e72ee90a42899`；HTML 引用 `home-navigation-article-scroll-20261010` 缓存版本；`kaj-labs.service=active/running`、`/health/live=200`。 |
| 2026-10-10 | Labs 服务与资源只读复核 | passed/partial | `kaj-labs.service=active/running`，`https://labs.kajspace.cn/health/live=200`；当前数据库引用的 11 个非删除媒体文件已存在，文件大小/SHA-256 与 `media_asset` 一致；头像、Hero、封面、正文图片和附件 URL 返回 `200`。知识文档媒体匿名返回 `404`，符合授权策略。 |
| 2026-10-10 | Labs 内容可见性只读复核 | observed | 知识文档为 `APPROVED=1/DELETED=1`；3 个已发布题库卷均为 `ADMIN_HIDDEN/security_review`，公开题库页为 `200` 但 0 个结果。未修改题库可见性。 |
| 2026-10-10 | 生产与外部副作用边界 | not run | 未执行生产迁移、部署、重启、招聘采集、Provider/AGENT 或 Git 写操作；Labs migration 仅在后续答题 500 修复步骤中应用。 |
| 2026-10-10 | Labs `manage.py migrate learning --noinput` | passed | 仅对 `kaj_test_production_clone` 应用 `learning.0014_quizattempt_mode_and_more`，输出 `Applying ... OK`，退出码 `0`；未执行生产 migration。 |
| 2026-10-10 | Labs schema/运行时收口 | passed/partial | `mode` 字段、`learning_quiz_attempt_mode_valid` 约束和 migration 记录读回；`manage.py check` 输出 `0 issues`，`makemigrations learning --check --dry-run` 输出 `No changes detected`；Web `active/running`、live `200`。未追加浏览器答题流。 |
| 2026-10-10 | `KAJ_TEST_* ... uv run pytest apps/learning/tests/test_quiz_modes.py::test_start_configuration_offers_exam_and_practice_without_changing_question_count -q --reuse-db` | passed | 隔离 PostgreSQL/Redis/Mailpit，`1 passed in 75.73s`；新增断言覆盖刷题提交前无解析面板、无题目内重复按钮，逐题提交后存在解析面板且只保留一个底部刷题提交入口。 |
| 2026-10-10 | `ruff check`、`ruff format --check`、`node --check static/src/quiz.js`、`git diff --check` | passed | 退出码均为 `0`。 |
| 2026-10-10 | `npm run build` 与 Labs 静态读回 | passed | CSS/JS 产物构建退出码 `0`；`https://labs.kajspace.cn/static/dist/styles.css` 与 `app.js` 均返回 `200`；Web 仍 `active/running`、live `200`。 |
| 2026-10-10 | 解析栏逐题状态静态资源重建与 Labs 哈希读回 | passed | 本轮 `npm run build` 退出码 `0`；本地/公网 `app.js` SHA-256 均为 `9e8b35897b435a7b563bd380d37a5849668bece81473bfa420a28cded159991c`，`styles.css` 均为 `939f7ad364de357faa36a57dfa79725923e9a205c9162052dfafa5cfc8d8e269`；Labs 服务 `active/running`，live `200`。 |
| 2026-10-10 | Labs 切题浏览器交互 | not run | 用户此前明确表示无需代测；按其要求未启动浏览器，待用户手动确认提交题展开、未提交题收起、返回已提交题恢复。 |
| 2026-10-10 | 浏览器用户流 | not run | 用户此前要求停止继续测试；本轮未启动浏览器，仅完成服务器渲染回归、静态检查、构建和资源读回。 |
| 2026-10-10 | 解析面板恢复外层右侧栏 | partial | `npm run build:css` 与 `git diff --check` 均退出码 `0`；Labs 公网 CSS SHA-256 与本地均为 `cc36f1ff5770893234cacfcdfe54d52bedc39bebafcea6d08ef614cc575d6134`；服务 `active/running`、live `200`，登录页读回新缓存版本。资源门禁 `yellow`；CSS 构建前 `MemAvailable=645 MiB/SwapFree=2.18 GiB`，浏览器前 `667 MiB/2.17 GiB`，结束后 `631 MiB/2.22 GiB`；Swap I/O 有活动但整体 Swap 使用量下降、系统有响应，单一并发操作均完成。 |
| 2026-10-10 | `/usr/local/bin/blog-playwright-cli -s=quiz-layout` | partial | `/learning/quiz/` 是错误前缀并返回 `404`；按 `config/urls.py` 改为 `/knowledge/quiz/` 后重定向 `/accounts/login/`（HTTP `302`）。浏览器无登录态，未能观察答题页面；会话已关闭，未尝试猜测凭据或修改 Labs 数据。 |
| 2026-10-09 | Labs media readback/restoration | partial/passed | 当前 `var/media` 初始为 0 文件；数据库有 15 个媒体记录，其中 11 个非删除记录在旧 Labs 归档中有同 storage key。按 key 定向恢复 11 个文件，设置 `kaj-labs:kaj-labs`/`0640` 文件和 `0750` 父目录；头像、Hero、封面、附件媒体路由读回 200。未复制生产媒体、未改数据库。 |
| 2026-10-09 | Labs content visibility readback | observed | 数据库有 2 个账户、2 个知识文档、3 个题库卷；3 个题库卷均 `ADMIN_HIDDEN` 且 reason=`security_review`，公开题库页返回 `200` 但显示 `0 个结果`；知识文档状态为 `APPROVED=1`、`DELETED=1`。未直接修改可见性。 |
| 2026-10-09 | Labs dependency readback: `docker inspect`、`pg_isready/psql`、`redis-cli ping`、Mailpit API、ports | passed | `kaj-p12-postgres`/`kaj-p12-redis` 已 running，Mailpit running/healthy；`kaj_test_production_clone` 以 `kaj_test_runner` 可连接，Redis `PONG`，Mailpit API `200`，端口 `57432/56381/51027/58027` 均监听。未重复启动或重启容器。 |
| 2026-10-09 | `systemctl start kaj-labs.service` + `systemctl show` | partial | 首次启动因缺少 Labs runtime 目录 `var/media`/`var/backups` 触发 `226/NAMESPACE`；已仅创建这两个被 unit 明确声明的 `0750`、`kaj-labs:kaj-labs` 目录后恢复，当前 Web `active/running`、工作目录正确。未启动 Worker/Beat。 |
| 2026-10-09 | Labs health/入口读回 | partial | `https://labs.kajspace.cn/health/live` 返回 `200`，未登录 `/knowledge/quiz/` 返回 `302`；服务日志提示 Labs 数据库有 1 个未应用 migration，登录后的新模式流尚未读回。未执行 migration。 |
| 2026-10-09 | `/root/.local/bin/uv run pytest -q apps/learning/tests/test_quiz_modes.py apps/learning/tests/test_quiz_order.py apps/learning/tests/test_quiz_records_t18.py`（隔离 P12 PostgreSQL/Redis/Mailpit） | passed | `14 passed in 91.79s`；覆盖模式入口/default、考试自动保存仍隐藏/整套揭晓、刷题逐题揭晓/锁题/错题幂等、简答预提交自评和历史记录兼容。退出码 `0`。 |
| 2026-10-09 | `manage.py check`；`manage.py makemigrations learning --check --dry-run` | passed | Django `0 issues`；`No changes detected in app 'learning'`；migration `0014_quizattempt_mode_and_more.py` 已生成并由隔离测试库应用。生产未执行 migration。 |
| 2026-10-09 | 目标 `.venv/bin/ruff check`、`ruff format --check`、`node --check static/src/quiz.js`、`git diff --check` | passed | Python 目标文件 12 个格式检查通过；JS 语法和差异空白检查退出码 `0`。 |
| 2026-10-09 | `npm ci --ignore-scripts --no-audit --no-fund`；`npm run build` | passed | 安装 94 个锁定依赖；CSS、主题/导航、字体和 `app.js` 构建退出码 `0`。esbuild 对 1.1MB app bundle 发出体积提示，无构建失败。 |
| 2026-10-09 | `/usr/local/bin/blog-playwright-cli` 隔离本地真实用户流 + PostgreSQL 读回 | passed | 登录、配置选择 PRACTICE、自动保存、逐题 POST/揭晓、刷新持久化和整套提交成功；DB `PRACTICE/SUBMITTED`、2/2 responses、score `1/2`、错题 `wrong_count=1`、题库完成数 `+1`。390/768/1440 × light/dark/eye-care 九组无横向溢出，Enter 切题有效，控制台 0 error/0 warning，静态请求均 200/304。临时数据库和媒体已清理。 |
| 2026-10-09 | Labs `systemctl` 与公网 health | partial | 服务工作目录与当前 Labs worktree 相同；Web/Worker/Beat `inactive/dead`，`/health/live=502`，未启动/重启，因此无 Labs 页面运行时读回。 |
| 2026-10-09 | Docker image labels + `git diff 42adeb4..origin/main -- apps config templates static` | passed | Web/Worker/Beat 均报告 revision `42adeb4ceb74ec5823df70a66144b21b80b0f275`；应用运行时代码目录与最新远端默认分支一致，后续提交仅为文档。 |
| 2026-10-09 | Labs worktree relocation/recreation | passed | 旧 Labs worktree 从 `a06a94f` 移至 `labs-test-environment-archive-20261009`，读回其所有 dirty/untracked 状态仍在；新 `codex/labs-next-20261009` 建于 `origin/main=631253f`，创建后工作树干净。 |
| 2026-10-09 | Labs service/readiness readback | partial | `WorkingDirectory` 仍为 Labs 原路径；Web/Worker/Beat 为 `inactive/dead`，`https://labs.kajspace.cn/health/live` 返回 `502`。未启动服务，因此无页面或用户流验证。 |
| 2026-10-09 | 文档与 handoff 检查 | passed | `git diff --check` 退出 `0`；新建文件无尾随空格且为 UTF-8。未运行 pytest、构建、Playwright、迁移、生产写入或 Git 提交/推送（本轮只做基线/文档准备）。 |
| 2026-10-09 | 实施计划范围复核 | passed | `implementation-todolist.md` 声明 P0-P12 的 102 项全部完成且无活动 Todo；交接中的 P0 性能复测和知识审核能力检查属于独立运维跟进。下一产品切片仍待用户指定。 |
| 2026-09-16 | `python3 /root/.codex/skills/agent-handoff/scripts/bootstrap_handoff.py --repo /home/code/personal-blog --platform codex --layout multi --session-prompts` | passed | 创建多文档 handoff、会话提示词和 AGENTS 标记块；未创建 Claude 项目规则。 |
| 2026-09-16 | `git status`, `git worktree list`, `git log`, `git rev-list HEAD...origin/main` | passed | 主工作区 `e5adc20`，远端 `0b700d4`，落后 21；Labs `0b700d4` detached；正式快照 `1f9d47c` detached。 |
| 2026-09-16 | `systemctl show kaj-labs*.service` | passed | Labs web/worker/beat/outbox 均为 `inactive/dead`；没有为 handoff 启动服务。 |
| 2026-09-16 | `docker ps --filter label=com.docker.compose.project=kaj-production` | passed | 正式 Web/Worker/Beat 及依赖容器保持运行；未重启或修改生产容器。 |
| 2026-09-16 | `curl https://kajspace.cn/health/live` / `health/ready` | passed | 正式环境读回均为 HTTP 200；仅做只读健康检查。 |
| 2026-09-16 | `file -bi`, `rg '[[:blank:]]+$'`, `git diff --check`（handoff 路径） | passed | 9 个 handoff 文本文件均为 UTF-8/ASCII，无尾随空白；AGENTS 仅新增标记协议块。 |
| 2026-09-16 | handoff 路径/索引/ignore 复核 | passed | `AGENT_HANDOFF.md` 链接的 8 个状态文件均存在、非空且未被忽略；随后由 Labs 提交 `3c34606` 纳入远端 `main`。 |
| 2026-09-17 | `git fetch origin`、远端提交读回 | passed | 本轮 handoff 任务分支均已推送、fast-forward 集成并删除；Labs 保留在集成后的 detached 快照，具体提交以当前读回为准。 |
| 2026-09-16 | pytest/Ruff/build/Playwright/P0 性能测试 | not run | 本轮只生成交接文件；不把历史验证或生产运行状态冒充本轮测试结果。 |
| 2026-09-15 | 性能文档提交/远端读回 | passed | Labs 提交 `0b700d4`，远端 `origin/main` 包含该提交，临时任务分支已删除。 |
| 2026-09-15 | 生产知识审核 capability 只读诊断 | passed | profile/Endpoint/检查版本和最近审核失败状态读回，未读取 API Key、正文或个人数据。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_opp001.py -q --reuse-db`（隔离 P12 PostgreSQL/Redis/Mailpit） | passed | `9 passed in 56.13s`；首次无隔离变量运行错误，SQLite 不支持项目 PostgreSQL 专用迁移 SQL，未作为产品结果。 |
| 2026-09-20 | 性能 RED：`test_public_query_uses_one_filter_option_query_and_no_n_plus_one` | passed as RED | 优化前筛选 owner 查询为 `5` 条，断言目标 `3` 条，准确复现重复筛选选项查询。 |
| 2026-09-20 | 优化前隔离性能探针（临时文件，已删除） | observed | 默认/搜索/筛选/分页完整页分别为 `22/17/17/17` 条 SQL、约 `175/55/35/31ms` SQL 总时长；根模板约 `322/55/64/73ms`；响应约 `70.4/70.4/70.8/42.6KB`。正式公网未压缩读回为 `419230/394019/419608B`，gzip 下载约 `61821/60207/60638B`。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_public_performance.py -q --reuse-db`（临时回归文件，已清理） | passed | `6 passed in 3.99s`；覆盖 4 条匿名岗位路径、筛选/分页固定 SQL 数量、无 N+1 和 HTMX 摘要跳过。 |
| 2026-09-20 | `/root/.local/bin/uv run pytest apps/opportunities/tests/test_public_performance.py apps/opportunities/tests/test_opp001.py -q --reuse-db` | passed | `15 passed in 6.78s`；优化后岗位聚焦回归。 |
| 2026-09-20 | P0 隔离性能探针（临时文件，已删除） | passed | 优化后四路径均 `200`；SQL `17→14`，岗位 owner 查询固定 `3` 条；隔离响应 `42.6–70.8 KB`，根模板约 `33–204ms`。 |
| 2026-09-20 | `ruff check`、`ruff format --check`、`git diff --check`、`python manage.py check` | passed | 目标 3 个代码/测试文件；Django `0 issues`。 |
| 2026-09-20 | 正式公网岗位只读传输读回 | observed | 默认列表/关键词/分页均 `200`；未压缩 `394–420 KB`，gzip 后 `60–62 KB`，`private, no-store`；未执行压测或生产写入。 |
| 2026-09-20 | Labs 定向同步与读回 | partial | 仅同步 `views.py`、`queries/public.py`、`test_public_performance.py` 并 `cmp` 成功；`kaj-labs.service=inactive/dead`，Labs `/health/live=502`，未启动/重启。 |
| 2026-09-20 | 最终轻量复核：目标 Ruff/format、`git diff --check`、临时测试文件清理、`git rev-list HEAD...origin/main`、`systemctl show kaj-labs.service` | passed/partial | 代码静态检查和差异检查退出 `0`；主工作区 `a06a94f` 与远端 `0/0`；两处临时测试文件均已清理；Labs 仍 `inactive/dead`。 |
| 2026-09-20 | 正式候选构建与预检 | passed | `docker build` 退出 `0`；候选 image `sha256:26caccd5272c9173252504d578846f1e21287700c9981a6b2814749fb7c0aaf8`；`check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 均退出 `0`，无待执行 migration。 |
| 2026-09-20 | 正式发布前备份 | passed | PostgreSQL dump `176670834` 字节、TOC `1043`；媒体归档 `7024193` 字节、成员 `410`；Compose 快照 `6413` 字节；三者权限均 `0600`，摘要见正式 deployment record。 |
| 2026-09-20 | 正式应用切换与只读 smoke | passed | Web/Worker/Beat 顺序切换到 `42adeb4ceb74`，healthy/running、RestartCount 0；live/ready、默认/搜索/筛选/分页和 JS/CSS 均 HTTP 200；未执行 migration、招聘采集、Provider/AGENT 或状态补偿。 |
| 2026-09-20 | 发布记录 Git 交付 | passed | `docs: 记录岗位性能正式增量发布` 提交 `6f59ed8` 已推送并 fast-forward 到远端 `main`；临时分支已删除，原有未跟踪 P0 文档未纳入。 |

## Validation Guidelines

- Record commands/checks that were run.
- Record failed checks with concise cause and next action.
- Record checks that were intentionally not run as `not run`, with the reason.
- Do not paste long logs; summarize and reference files when needed.
