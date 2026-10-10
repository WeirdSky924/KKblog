# Kajspace 下一轮 Labs 迭代与公告台账（2026-10-09）

状态：答题考试/刷题模式已完成本地实现、隔离回归和本地真实浏览器验收；Labs 已应用 `learning.0014_quizattempt_mode_and_more` 与 `learning.0015_quiz_attempt_mode_db_default` 并读回数据库级默认值。统一提交入口和解析栏位置已由用户确认；首页导航平滑定位已在 Labs 完成 390/768/1440 视口真实浏览器验证。2026-10-10 招聘来源适配器修复已在 Labs 通过 35 项聚焦回归和有界真实来源解析；正式 Worker 更新及生产状态修复待本轮增量发布。题库仍因 `security_review` 处于管理隐藏状态。

## 正式基线与 Labs 工作区

- 正式 Web、Worker、Beat 当前镜像均为 `kaj-blog-web:42adeb4ceb74`，容器镜像 revision 为 `42adeb4ceb74ec5823df70a66144b21b80b0f275`。
- 当前远端默认分支为 `origin/main=631253fef50f7cfa459300bd00c61372180e7985`。从正式 revision 到该提交的差异只涉及 handoff 和 2026-09-20 发布记录；`apps/`、`config/`、`templates/`、`static/` 与正式 revision 相同。
- Labs 服务工作目录仍为 `/home/code/.codex-worktrees/personal-blog/labs-test-environment`。该目录现由新分支 `codex/labs-next-20261009` 使用，起点为 `origin/main`；建立时工作树干净，应用运行时代码与正式镜像源码一致。
- 原 Labs worktree 已完整移动到 `/home/code/.codex-worktrees/personal-blog/labs-test-environment-archive-20261009`。其 detached HEAD `a06a94f8349144fcba1c69f37d56088d9834573b`、未提交改动和未跟踪文件均保留；没有提交、推送或删除。
- 旧本地分支 `codex/labs-next-iteration` 与旧远端跟踪引用仍保留；其提交是当前 `origin/main` 的祖先。本轮不更新远端分支。
- Labs Web `kaj-labs.service` 当前为 `active/running`，工作目录未漂移；`https://labs.kajspace.cn/health/live=200`。Worker/Beat 未启动，因为本次答题页面不需要。启动时发现 unit 声明的 `var/media`、`var/backups` 缺失，已创建为 `0750`、`kaj-labs:kaj-labs` runtime 目录。Labs 数据库已应用刷题模式 migration；未执行生产 migration。

## 已发布能力与公告来源

正式公告和部署事实以 [2026-09-20 正式增量公告](../2026-09-20-production-increment/announcement.md) 与同目录部署记录为准。下一轮正式公告应从这些已发布事实向前描述，不把 Labs 草稿、旧 worktree 改动或测试数据写成正式能力。

## 下一轮范围状态

`docs/planning/implementation-todolist.md` 将原定 P0-P12 的 102 项任务标记为全部完成，没有指定新的产品 Todo。用户随后指定本轮产品切片为答题刷题模式，已完成本地实现与验收。外部 P0 性能复测和生产知识审核 capability check 仍是独立运维跟进。

## 正式运行规模参考（内部背景，不属于本轮变更效果）

生产库只读快照截止 `2026-10-09 03:20:00 UTC`：9 个 ACTIVE 账户且 9 个账户有登录、文章、答题或文档行为；159 篇文章、301 条文章修订、4 个 APPROVED 知识文档、4 套 PUBLISHED 题库，当前公开最新版共 999 道题。TaskRun 共 1,737,523 条，成功率 `99.9930%`、重试率 `0.1112%`，端到端 P95 `254ms`。这些数据属于当前生产规模背景，不能归因于下一轮迭代，也不能代替长期监控。

## 本轮完成的环境准备

- 归档旧 Labs 工作树并在服务配置的原路径建立干净分支，保留旧改动以供后续按需挑选；未合并旧 worktree 的脏改动。
- 对照运行容器 revision、Git 祖先关系和源码目录差异，确认当前 Labs 分支基于最新远端默认分支，且应用代码等同当前正式镜像源码。
- 基线准备阶段仅整理本地 Git/worktree 与文档；应用功能变更和验证记录见下方产品切片。没有生产数据库迁移、生产写入、生产部署或 Git 提交/推送。

## 本轮产品变更记录（逐切片追加）

### 答题考试模式与刷题模式（本地实现与验收完成）

用户要求在保留现有考试模式的基础上增加刷题模式：题型、题量、随机题目/选项和软计时继续沿用现有配置；考试模式仍在整套答题提交后揭晓结果；刷题模式由用户逐题提交，提交当前题后立即显示该题正确答案与解析，其余未提交题继续隐藏。自动保存不触发判分或答案揭晓；为避免揭晓后改答案和重复累加错题统计，已逐题提交的题目锁定。简答题逐题揭晓参考答案和评分要点，并允许按现有契约自评，最终整套提交仍汇总结果。

模式入口位于开始答题配置页，默认考试模式；旧记录通过 `learning.0014_quizattempt_mode_and_more` 初始化为考试模式。Labs 已应用 `0014` 和 `0015`；`0015` 保留数据库级默认值，兼容旧应用省略新列时写入。正式数据库迁移需与新应用在同一维护窗口部署。

唯一业务 owner 为 `apps.learning`：`QuizAttempt.mode` 持久化模式，`submit_quiz_response` 在锁定本人 attempt/response 后保存答案、判客观题和更新错题本；query 只对已提交的刷题 response 投影答案与解析。最终整套提交保留已处理结果，只完成未逐题提交的响应并汇总成绩。简答题按揭晓后自评，考试模式的自动保存与整套提交时机保持不变。

验证记录：隔离 PostgreSQL/Redis/Mailpit 上 `test_quiz_modes.py`、`test_quiz_order.py`、`test_quiz_records_t18.py` 共 `14 passed in 91.79s`；`manage.py check` 和 `makemigrations learning --check --dry-run` 均退出 `0`，migration drift 为 `No changes detected`；目标 Ruff lint/format、Python/JS 语法及 `git diff --check` 通过；`npm run build` 退出 `0`。

真实浏览器通过 `/usr/local/bin/blog-playwright-cli` 以隔离本地 PostgreSQL 账户完成登录、模式选择、自动保存、逐题提交、刷新读回和最终整套提交。浏览器及数据库读回为 `PRACTICE / SUBMITTED`、`2/2` response 已提交、客观成绩 `1/2`、错题 `wrong_count=1`（未因整套提交重复增加）、题库完成数 `+1`；未提交题的正确答案/解析保持隐藏。390/768/1440 × light/dark/eye-care 共 9 种布局均无横向溢出，键盘 Enter 能切换题目，控制台 `0` error / `0` warning，静态资源请求为 `200/304`。

浏览器测试使用的本地 `kaj_test_*` 数据库和 `/tmp` 媒体目录已清理。Labs 测试库已应用 `learning.0014` 和 `learning.0015`，并读回 `mode` 数据库默认值为 `EXAM`；生产迁移和部署状态以本轮单独的正式增量记录为准。

每完成一个 Labs 切片，立即在此补录 owner、迁移、测试命令/退出码、Labs 或隔离本地浏览器用户流、模式隔离与回归结果；后续切片至少记录：

- 日期、用户可见行为和问题；
- 唯一 owner、受影响页面/服务/数据；
- 目标测试、命令退出码和 Labs 页面/用户流读回；
- migration、数据修复、外部服务、通知或任务副作用；
- 后续正式发布所需迁移、配置、数据和回退动作。

### 2026-10-10 Labs 资源显示诊断

- Labs Web 已保持 `active/running`，公网 `/health/live=200`。
- 媒体运行目录按当前 Labs 数据库的 storage key 从旧 Labs 归档恢复 11 个非删除文件；数据库记录与文件的大小、SHA-256 一致，头像、Hero、封面、正文图片和附件媒体 URL 返回 `200`。
- 知识文档媒体需要账户授权，匿名 `404` 属于既有访问控制；当前测试库文档记录为 `APPROVED=1`、`DELETED=1`。
- 公开题库页为空的直接原因是 3 个已发布卷均为 `ADMIN_HIDDEN`，管理原因是 `security_review`。刷题模式 migration `learning.0014_quizattempt_mode_and_more` 仍未应用。
- 用户要求停止继续测试；本次只记录证据，未执行 Labs migration、题库可见性恢复、生产操作、服务重启、Provider/AGENT 或 Git 交付。后续若要开放 Labs 练习流，应分别授权 schema 迁移和安全可见性恢复。

### 2026-10-10 Labs 答题 500 修复

- 根因：答题模式代码已经读写 `QuizAttempt.mode`，但 Labs 测试库仍停在 `learning.0013_generation_batches`，`learning_quiz_attempt` 缺少该字段，考试和刷题模式创建答题记录都会触发 500。
- 修复：仅在 Labs 测试库应用 `learning.0014_quizattempt_mode_and_more`；`mode` 字段、`learning_quiz_attempt_mode_valid` 约束和 migration 记录已读回。
- 验证：`manage.py check` 与 `makemigrations learning --check --dry-run` 均通过，Web 保持 `active/running`、live `200`。未执行生产 migration、部署、服务重启或题库安全可见性恢复；未追加浏览器矩阵。

### 2026-10-10 统一答题提交入口与刷题解析栏

- 考试模式继续使用页面底部主提交按钮提交整套答题；刷题模式复用同一位置，按钮绑定当前题目并提交当前 response，不再在题目卡内生成第二颗提交按钮。
- 解析面板保持在答题工作区外层右侧第三栏；窄屏时位于答题区下方。刷题开始时维持考试模式的两栏布局，未提交题不显示侧栏；提交题切入时侧栏平滑展开并显示对应答案与解析，切到未提交题时收起，返回已提交题时恢复。
- 外层网格轨道负责面板展开/收起，关闭状态下不留空白轨道；收起时面板也从键盘/无障碍浏览顺序移除。`npm run build:css` 退出码 `0`，Labs 公网 CSS SHA-256 与本地构建产物一致，health 为 `200`。Playwright 的 `/knowledge/quiz/` 入口重定向登录（HTTP `302`），当前专用浏览器无登录态，因此没有观察到答题页的实际视觉位置。
- 后续由用户手动确认解析栏已位于原右侧栏位置。

### 2026-10-10 首页导航平滑定位

- 在主页顶部大图或文章页任意滚动位置打开侧边导航并选择分区后，文章列表先完成 HTMX 更新，再平滑定位到列表顶部；目标避开固定站点头部，并尊重系统减少动态效果设置。
- `npm run build:js` 退出码 `0`；Labs 公网 `app.js` SHA-256 与本地一致，服务保持 `active/running`、health `200`。Playwright 在 390、768、1440 视口和桌面底部滚动位置真实点击验证，文章区顶端与站点头部下沿对齐，无横向溢出，控制台 0 errors/0 warnings。

### 2026-10-10 招聘来源失败的 Labs 验证与最小修复

生产只读诊断显示每日 18:00 批次已为 129 个来源全部生成终态、0 个未执行；Celery 没有全局软/硬时限。浏览器来源的确定性故障是 Worker 容器绑定了旧 `/run/kaj-opportunity-browser` 目录 inode；生产侧恢复仍需在 socket 就绪后重建 Worker。最近多个 HTTP adapter 连续出现响应校验失败，因此先在 Labs 用只读真实来源响应校准解析契约。

`apps.opportunities.checks` 的改动只处理已证实的契约差异：Dahua 将单响应上限调整为项目既有允许值 384 KiB；Beisen 对被截断的大页执行最多三次有界降页重试；Getui 不再要求岗位列表包含 URL 中的分类路由 ID；Hotjob 接受空结果合法返回的 `pageSize=0`。Worker healthcheck 在环境已配置浏览器 socket 时检查 socket 路径存在且类型正确。

Labs 聚焦回归：Dahua、Beisen、Getui、Hotjob、Meituan 适配器及 Worker Compose contract 共 `35 passed in 1.17s`。Ruff check、format 和目标 `git diff --check` 通过。五种来源用 SafeHttpClient、robots 校验和至少 2 秒请求间隔进行直连，只读取状态/计数元数据：Dahua 144 条、Getui 5 条完整；Beisen 60 条/3 页、Hotjob 30 条/2 页、Meituan 25 条/5 页均因本次测试上限标记 `truncated`，未发生 parser 错误。响应正文只在进程内处理，没有写入 Labs 或生产数据库。

Labs Web 保持 `active/running`，`/health/live=200`。Labs 未运行 Worker/浏览器沙箱，socket mount 的运行态恢复尚未在 Labs 复现；当前证据是生产 inode 只读对照和 Compose contract 回归。没有运行生产招聘任务、Provider/AGENT、migration、镜像切换或 Worker 重建。正式更新仍需只包含岗位修复的可追溯候选，之后按发布流程更新 Worker 并验证 socket；不触发招聘采集。

正式候选形成时，再新增独立的 deployment plan/record；完成正式部署后另建该轮正式公告，并从本台账逐条核对，不以记忆补写。

## 发布边界

- 本台账不是正式发布公告；服务未运行时，不得声称 Labs 页面或用户流已通过。
- 未获当前回合明确授权，不执行 Labs 服务启动/重启、生产迁移、备份、镜像切换、部署、招聘采集、真实 Provider/AGENT 调用或 Git 提交/推送。
