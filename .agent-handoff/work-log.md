# Current Work Log

## 2026-10-12（README 当前状态整理）

- Objective: 更新项目 README，使其反映当前产品能力、正式运行版本、可核验数据和开发入口。
- Changes: 重写 `README.md`；同步更正架构、运维入口和实施清单中的“尚未部署”旧状态。记录生产业务快照（2026-10-09）、招聘来源状态（2026-10-11）和 HTTP 健康读回日期（2026-10-12），不把快照写成实时 SLO。
- Evidence: README 编辑基线 `main=91b88e7`，生产代码 revision `d06af75`；正式执行记录确认 `learning.0014/0015` 和 129 个启用来源终态；项目清单记录 13 阶段/102 任务、322 项需求、42 个路由及 P12 `405 passed`。
- Validation: `git diff --check` 通过；README 14 个唯一内部文档链接目标均存在；检查了生产、招聘、测试和 P0 状态数据来源。没有运行测试或启动 Labs 服务（本次仅更新文档，Labs 按要求保持关闭）。
- Git: 用户在后续当前回合明确要求提交推送；具体提交与集成状态以最终 Git 历史和远端读回为准。

## 2026-10-11（正式增量发布与状态修复）

- Objective: 提交推送本轮答题/导航/招聘修复，增量更新正式环境，按真实终态修复 35 条来源状态，并关闭 Labs 测试服务。
- Changes: 最终有效提交已 fast-forward 到远端 `main=d06af75`。答题迁移 `0014/0015` 已应用；Web/Worker/Beat 使用 `kaj-blog-web:d06af75a9c31`；独立 browser sandbox 更新到版本化 `d06af75` release，Feishu allowlist 与应用契约一致；Nginx marker 已移除、Caddy 保持 `2cbead0`。
- Validation: Quiz/记录回归 `15 passed`；adapter/Worker `35 passed`；增量镜像合同 `1 passed`；browser runner 合同 `19 passed`。Django check、migration drift、生产 plan、Ruff、JS 语法、`npm run build` 和 Caddy profile 验证通过。
- Production: `learning.0014/0015`、模式约束和 DB `EXAM` default 读回；Web/Worker/Beat healthy/running、restart 0；Worker socket 与宿主 inode一致。35 条最新来源检查为 30 healthy、1 degraded/truncated、4 stale（Qcraft timeout、2 Hotjob parser、1 Meituan parser）；无活动检查/每日全量任务/Provider/AGENT。
- Safety: PostgreSQL dump、媒体归档、Compose 快照均为 `0600` 并校验。来源状态只经现有 service 更新。生产 PostgreSQL backend 两次 exit-code 2 后自动 WAL recovery；容器无 restart/OOM，当前 healthy，根因需后续调查。
- Labs: Web 与 P12 PostgreSQL/Redis/Mailpit 已 stop 并读回 inactive/exited；数据卷保留。
- Next: 独立调查 PostgreSQL backend exit 根因；在 Labs 修复三条仍 `adapter_response_invalid` 来源和 Qcraft timeout，再定向复查。外部 P0 性能复测与生产 knowledge-review capability check 仍是独立运维待办。

## 2026-10-10（Labs 招聘来源适配器验证与修复）

- Objective: 在 Labs 先验证每日招聘来源失败并修复稳定的 parser 根因；验证通过后进入正式更新准备。
- Changes: Dahua 列表响应上限采用项目允许的 384 KiB；Beisen 对截断页执行最多 3 次有界降页重试；Getui 不再把分类路由号当作岗位 ID；Hotjob 接受合法空列表的 `total=0/pageSize=0`；Worker healthcheck 在配置浏览器 socket 时要求路径为 Unix socket。
- Live Labs probes: 使用安全客户端、robots 检查和 2 秒请求间隔；Dahua 144 条完整、Getui 5 条完整。Beisen 3 页 60 条、Hotjob 2 页 30 条、Meituan 5 页 25 条均按探针页数上限正常返回并标记 truncated；不输出或保存岗位正文，不写 Labs/生产数据库。
- Validation: 五个 adapter 文件 + 容器 contract 共 `35 passed in 1.17s`；目标 Ruff check、format、`git diff --check` 退出码 `0`；Labs service `active/running`、live `200`。`uv` 不在 shell PATH，使用现有 `.venv` 工具，没有安装依赖。
- Boundary: 没有运行定时采集、Provider/AGENT、生产 migration 或生产任务；Labs 未部署 Worker/浏览器沙箱，socket 运行态仅有 Compose contract 证据。正式更新尚未执行。
- Next: 正式发布需只包含岗位修复的可追溯候选；当前 Git commit/push 授权待用户明确确认。候选通过后重建 Worker 并验证 socket/健康状态，不触发生产招聘采集。

## 2026-10-10（生产招聘定时失败诊断）

- Objective: 判断每天 18:00 批量招聘检查的大量来源失败是否由整批超时中断造成。
- Evidence: 只读检查生产 `kaj-production-worker-1` 和 PostgreSQL；最新批次 129 个来源全部有终态（93 成功、35 失败、1 截断、0 未执行），TaskRun `succeeded`/attempt 1、耗时 1810 秒。运行时 Celery `task_time_limit=None`、`task_soft_time_limit=None`；来源单独 `max_duration_seconds=600`。
- Failure categories: 当天 26 个 `opportunities.adapter_browser_unavailable.v1`、8 个 `opportunities.adapter_response_invalid.v1`、1 个 `opportunities.request_timeout.v1`。近 30 天分别累计 509/20 runs、176/28 runs、23/16 runs；`opportunities.collection_timeout.v1` 仅 1/1 run。
- Separate incident: 2026-09-20 有一次 TaskRun attempt 3 以 `operations.task_lease_expired.v1` 终结，批次耗时 88,837 秒；这是租约/heartbeat 类异常，不是 Celery 全局硬时限，也不符合最近每日失败分布。
- Boundary: 所有生产数据库操作均在 `BEGIN READ ONLY`、5 秒 statement timeout 下执行；未运行招聘采集、Provider/AGENT、生产写入、migration、部署或重启，也未执行 Git 写操作。

## 2026-10-10（定位重复招聘来源失败根因）

- Deterministic browser failure: 最新 7 个定时批次内，21 个 `feishu-career-v1` 来源以及 Alibaba、ByteDance、Hikvision、Xiaomi 浏览器来源均连续 7/7 返回 `adapter_browser_unavailable`。生产 Worker 已配置 `/run/kaj-opportunity-browser/browser.sock`，但容器内挂载目录 inode 为 `26:10264108` 且 socket 不存在；宿主当前 socket 位于 inode `26:13168080`，权限 `0660`、UID 999/GID 10001。Worker 创建时间为 2026-09-20 10:41 UTC，浏览器 systemd 服务启动于 2026-09-25 22:59 UTC。
- Root cause: Worker 容器创建早于浏览器 socket 就绪；宿主 `/run/kaj-opportunity-browser` 的目录 inode 此后变化，而 Worker 的只读 bind mount 仍固定在旧 inode。浏览器服务 `active/running` 并不代表容器可见 socket。修复需在 socket 已就绪时重建 Worker 容器，让挂载重新绑定当前目录。
- Other stable failures: 最近 7 个批次中，Hotjob 3 个、Getui 2 个、Dahua/Meituan/Beisen 各 1 个来源连续返回 `adapter_response_invalid`。错误记录仅保留 `FILTERS`/错误码，不保存 HTTP 响应体；没有当前响应证据，不能安全放宽 parser。
- Boundary: 未重建生产 Worker；此前用户边界明确禁止生产重启/部署，当前尚未明确解除。未访问招聘来源或调用 Provider/AGENT；等待用户决定 worker recreate 和后续来源诊断授权。

## 2026-10-10（首页导航定位文章列表顶部）

- Objective: 从主页大图手动打开侧边导航后，点击任一文章分区链接，无论当前滚动位置都平滑定位到文章列表顶部。
- Changed: `static/src/home-navigation.js` 在侧边导航 HTMX 请求成功后调用现有 `snapTo(articles)`，等待列表替换完成再计算目标；`templates/base.html` 更新 JS/CSS 缓存版本。
- Validation: `npm run build:js`、`node --check static/src/home-navigation.js`、`git diff --check` 均退出码 `0`；Labs 公网 `app.js` SHA-256 与本地一致；Web `active/running`、health `200`。
- Browser: Labs 首页真实点击分区导航，390/768/1440 视口和桌面底部滚动位置下文章区顶端均与站点头部下沿一致；横向溢出 `0`，console errors/warnings `0`；浏览器已关闭。
- Resource gate: `yellow`; browser/build concurrency `1`; 任务期间 Swap 余量保持约 `2.2 GiB`，主机有响应，构建与单一浏览器会话均完成。

## 2026-10-10（修复 Labs 答题 500）

- Root cause: Labs 应用已读写 `QuizAttempt.mode`，测试库仍停在 `learning.0013_generation_batches` 且 `learning_quiz_attempt` 缺少 `mode` 字段；因此考试与刷题模式都在创建答题记录时返回 500。
- Fix: 仅在 Labs 测试库运行 `manage.py migrate learning --noinput`；`learning.0014_quizattempt_mode_and_more` 应用成功，没有修改题库 `ADMIN_HIDDEN/security_review` 状态。
- Validation: 字段、约束、migration 记录读回；Django check、learning migration drift check、health 均通过。未运行浏览器矩阵或全量回归，用户可重新开始答题验证。

## 2026-10-10（统一答题提交入口与解析栏）

- Changed: `quiz_attempt.html` 移除题目内刷题提交按钮，底部原主提交位置按模式绑定整卷或当前题；`_attempt_context` 只在已有揭晓题目时让解析栏进入布局。
- Interaction: `quiz.js` 在切题时更新底部按钮的 form/formaction，并按当前题的揭晓状态同步解析栏布局、`aria-hidden` 和 `inert`；已揭晓题目禁用提交。解析面板恢复为工作区外层第三栏，外层网格轨道随状态展开/收起；窄屏时放在答题区下方。`templates/base.html` 更新静态缓存版本。
- Validation: 本轮 `npm run build:css`、`git diff --check` 均退出 `0`；Labs CSS 公网 SHA-256 与本地构建产物一致，服务 `active/running`、live `200`。Playwright 打开正确答题入口后被重定向到登录（`302`），无登录态，未能查看答题页布局。

## 2026-10-10（Labs 资源显示诊断收口）

- User feedback: 启动后头像、知识文档、图片和题库没有正确出现；随后明确不需要继续测试。
- Evidence: Labs Web 保持 `active/running`，公网 live 为 `200`；11 个非删除媒体文件已按数据库 storage key 从旧 Labs 归档恢复，文件大小/SHA-256 与数据库一致，头像、Hero、封面、正文图片和附件 URL 均返回 `200`。
- Root cause split: 知识文档媒体匿名读取被访问控制返回 `404`；当前数据库文档记录为 `APPROVED=1`、`DELETED=1`。公开题库为空是因为 3 个题库卷均为 `ADMIN_HIDDEN/security_review`，不是模板或媒体路由缺陷。刷题模式依赖的 `learning.0014_quizattempt_mode_and_more` 也尚未应用。
- Boundary: 本轮停止浏览器和回归测试；没有应用 migration、修改题库可见性、生产写入、服务重启或 Git 交付。后续必须先得到对应 Labs 共享数据动作的明确授权。

## 2026-10-09（启动 Labs Web）

- User request: 启动 Labs 服务进行答题模式测试。
- Result: `kaj-labs.service` 已 `active/running`，WorkingDirectory 为当前 Labs worktree；公网 `/health/live=200`，未登录 `/knowledge/quiz/` 为 `302`。仅启动 Web，Worker/Beat 未启动。
- Runtime fix: systemd 首次启动因 unit 声明的 `var/media`、`var/backups` 目录缺失而 `226/NAMESPACE`；按现有 unit 只创建两个 `0750`、`kaj-labs:kaj-labs` runtime 目录，未改源码/数据库。
- Limitation: 服务日志提示 Labs 数据库有 1 个未应用 migration，即本轮 `learning.0014_quizattempt_mode_and_more`；本轮没有执行 migration。登录后的刷题模式公网流需要下一步单独授权 Labs migration。

## 2026-10-09（复核 Labs 依赖资源）

- Readback: `kaj-p12-postgres`、`kaj-p12-redis` 已 running，`kaj-p12-mailpit` running/healthy；`kaj_test_production_clone` 可用、Redis PONG、Mailpit API 200，相关端口均监听。
- Action: 未重复启动或重启容器；Labs Web 继续保持 active/running。剩余阻塞是 `learning.0014` 尚未授权/执行。

## 2026-10-09（答题考试/刷题模式）

- Objective: 保留考试模式既有整套揭晓行为，新增每题提交即揭晓的刷题模式。
- Changed: `QuizAttempt.mode` + migration `learning.0014`（默认 `EXAM`）；`submit_quiz_response` 在事务内判客观题、更新错题本并锁定已揭晓 response；query 按单题提交状态隐藏/揭晓答案；配置页、回答页、短答自评、模式结果标签、静态缓存版本及 planning/architecture/release 文档同步。
- RED/GREEN: 初始聚焦 RED 明确落在缺少模式选项；真实浏览器又发现重入 `requestSubmit` 被忽略，改为下一事件循环任务再提交后成功。
- Validation: 隔离 PostgreSQL/Redis/Mailpit 上模式、答题顺序和记录回归 `14 passed in 91.79s`；Django check、migration drift、目标 Ruff/format、JS 语法、完整静态构建和 `git diff --check` 通过。
- Browser/data: 本地隔离站点登录并真实选择 PRACTICE、逐题提交、刷新和最终提交；DB 读回 `PRACTICE/SUBMITTED`、2/2 responses、objective `1/2`、错题计数只增一次、题库完成数 `+1`。390/768/1440 × 三主题无横向溢出，Enter 导航有效，控制台 0 error/0 warning。
- Runtime/boundary: 临时 `kaj_test_quizmode_ui_20261009` 数据库和 `/tmp` 媒体目录已删除；Labs 源码目标与当前 worktree 相同，但服务仍 `inactive/dead`、公网 live `502`，未启动/重启；未执行生产 migration/部署/Provider/AGENT/Git 写操作。
- Next: 等 Labs 服务由运维恢复后再做公网 Labs 只读页面读回；生产发布需另行授权。

## 2026-10-09（恢复 Labs 正式基线）

- Objective: 盘点分支/worktree，并让新 Labs 迭代从当前正式源码基线开始；建立独立公告台账。
- Evidence: 正式 Web/Worker/Beat image revision 均为 `42adeb4ceb74ec5823df70a66144b21b80b0f275`；最新 `origin/main=631253f` 在其后只有 handoff/发布文档差异，`apps/ config/ templates/ static/` 完全一致。
- Worktree: 旧 Labs detached `a06a94f`（包含未提交应用代码、handoff、测试及公告）完整移动到 `labs-test-environment-archive-20261009`；原服务工作目录建立干净分支 `codex/labs-next-20261009`，跟踪 `origin/main`。旧分支保留，未提交/推送。
- Docs: 新增 `docs/releases/2026-10-09-next-iteration/announcement.md`，作为逐切片公告台账；补齐新分支 handoff 状态。
- Planning: 复核实施清单与 readiness；计划文档称原定 P0-P12 的 102 项已完成，没有新的产品 Todo。外部 P0 复测和生产知识审核能力核对仍是独立运维待办，不擅自选为新产品功能。
- Runtime: Labs 服务仍 `inactive/dead`，`/health/live=502`；只完成源码基线确认，没有启动或重启服务，也没有执行产品测试或生产操作。
- Next: 等待明确下一产品切片；服务运行时验收须待 Labs 获明确授权恢复后进行。

## 2026-09-17

- Objective: 按 Labs-first 规则提交并推送 handoff。
- Changed files: `AGENT_HANDOFF.md`、`AGENT_SESSION_PROMPTS.md`、`.agent-handoff/*.md`、`AGENTS.md` 的 handoff protocol。
- Result: handoff 初始内容和状态收口均由 Labs 任务分支推送并 fast-forward 到远端 `main`；临时分支已删除；Labs 保留在集成后的 detached 快照。
- Remaining risks: 主工作区仍为 `e5adc20`、落后远端 23 个提交且保留原有脏改动，未执行同步或覆盖。

## 2026-09-20

- Objective: 按 P0 `03-backend-performance.md` 定位 Kajspace 公开岗位性能，先形成 SQL/模板/响应传输证据，再做最小优化和聚焦回归。
- Evidence: 正式公网三个岗位 GET 均 `200`；未压缩响应 `394–420 KB`，Nginx gzip 后 `60–62 KB`。隔离 PostgreSQL 探针显示筛选选项 owner SQL `5→3`，完整岗位请求 `17→14`；岗位查询本身保持 count/page/prefetch 三条，无模板 N+1。
- Changed files: `apps/opportunities/queries/public.py`、`apps/opportunities/views.py`；临时回归文件仅用于本轮验证，已清理。
- Result: 合并筛选选项查询、复用来源计数、HTMX 跳过未使用摘要；聚焦测试 `6 passed`，既有岗位回归 `9 passed`，合并 `15 passed`；Ruff/format/Django check/diff check 通过。
- Labs: 三个已完成文件已定向同步并 `cmp` 验证；Labs 服务仍 `inactive/dead`，`health/live=502`，未启动/重启；本任务未执行 Git add/commit/push、生产 migration、部署或 P0 外部复测。

## 2026-09-20（正式增量发布）

- Objective: 将岗位性能优化提交 `42adeb4` 增量更新到正式环境。
- Preflight: 构建 `kaj-blog-web:42adeb4ceb74` 成功；候选 `check --deploy`、migration drift 和正式 `migrate --plan` 通过且无待执行 migration。
- Safety: 新鲜 PostgreSQL dump、媒体归档和 Compose 快照均为 `0600` 并完成 SHA-256/TOC/成员校验；未执行 migration、招聘采集、Provider/AGENT、恢复或 Outbox 补偿。
- Result: Web/Worker/Beat 按顺序切换，均为候选镜像、healthy/running、RestartCount 0；健康、岗位默认/搜索/筛选/分页及 JS/CSS 均 HTTP 200。
- Remaining: Labs 仍 inactive/dead；外部 P0 并发复测仍待执行；发布记录已由 `6f59ed8` 推送并 fast-forward 到远端 `main`。

## 2026-09-16

- Objective: 为 `/home/code/personal-blog` 建立完整的 repository-local multi-document handoff。
- Changed files:
  - `AGENT_HANDOFF.md`: 保留索引和恢复顺序。
  - `.agent-handoff/*.md`: 写入当前快照、工作区地图、决策、验证、backlog、风险和归档入口。
  - `AGENT_SESSION_PROMPTS.md`: 写入新窗口、继续、收口和质量复核提示词。
  - `AGENTS.md`: 追加标记的多文档 handoff protocol，保留既有项目规则。
- Result: handoff 已按当前主工作区、Labs、正式快照、Git 和服务状态填充；未创建 `.claude/CLAUDE.md`，因为项目当前没有 Claude Code 项目规则文件。
- Remaining risks: 主工作区脏且落后远端；handoff 文件当时尚未提交，后续已在 2026-09-17 完成交付。

## 2026-09-15

- Objective: 将性能测试任务文档从 Labs 提交并推送，保留当前正式快照，准备外部机器远程 P0。
- Changed files: `docs/operations/README.md`、`docs/operations/performance-testing/`（P0/P1/P2 任务及执行日志）。
- Result: Labs 任务提交 `0b700d4`，fast-forward 集成远端 `main`；临时分支已删除；未部署、未重启生产。
- Remaining risks: 外部 P0 尚未执行；执行日志仍为“未执行”。

## 2026-09-15（工作区审计）

- Objective: 核对 Labs-first 提交路径和主工作区漂移。
- Result: `origin/main`/Labs 为 `0b700d4`；主工作区 `e5adc20` 落后 21 个提交，存在 69 个 tracked 修改和 12 个 untracked 路径；未执行 reset、pull、merge 或覆盖。
- Remaining risks: 主工作区改动需要逐文件分类，不能整体迁移或丢弃。

## 2026-09-15（生产审核诊断）

- Objective: 诊断知识文档审核 `agents.profile_capability_unverified.v1`。
- Result: 生产只读读回显示知识审核 profile 需要 `knowledge-review.v1`；当前 Endpoint row version 为 8，但匹配的严格检查只有其他 schema，旧审核检查对应旧 row version。失败发生在 AGENT 外呼之前。
- Next action: 管理员对当前 Endpoint 选择知识文档审核 profile 执行严格 capability check，成功后重试审核。

## Work Log Guidelines

- Keep only recent, still-operationally-useful work here.
- Move stale or long history to `archive.md` as a compressed summary.
- Prefer file paths and concrete outcomes over prose summaries.
