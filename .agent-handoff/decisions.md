# Decision Log

| Date | Decision | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-10-11 | 将 `learning.0014` 与 `0015` 作为同一维护窗口迁移；`QuizAttempt.mode` 同时保留应用和数据库级 `EXAM` 默认值。 | 只靠 Django 模型默认值时旧应用省略新列会在数据库写入时报错；`0015` 失败时也不能开放旧应用写请求。新刷题数据产生后旧应用不理解 `PRACTICE`，按前向修复处理。 | RED 用例读到 PostgreSQL `column_default=NULL`；加入 `0015` 后隔离 DB 和 Labs DB 均读回 `'EXAM'::character varying`。 |
| 2026-10-11 | 对 35 条招聘来源状态只通过现有来源检查 service 重新检查，不直接 SQL 改写 `check_state`。 | `STALE` 是此前 socket/parser/timeout 失败的事实；只有修复后检查的真实终态才能决定 HEALTHY/DEGRADED/STALE，原始状态不能安全批量置成功。 | 生产只读聚合为 26 个 socket 错误、8 个响应契约错误、1 个 timeout；当前请求明确要求修正这些状态。 |
| 2026-10-11 | 增量发布复用当前正式 Web 镜像构建源码候选；正式维护门禁由宿主 Nginx 唯一控制，Caddy 维持现有下游静态/媒体职责。 | 公网 `kajspace.cn` 由 Nginx `kaj-manual` server 接入，Nginx 已有 `kaj-manual-maintenance.conf` 和 `/run/kaj-production-maintenance.enabled`。Caddy 容器实际运行 development profile 且不在 TLS 入口；避免重复维护状态。 | Nginx marker 读回公网 `503`、no-store/Retry-After，Web loopback live/ready `200`；Caddy 已恢复 `2cbead0`；独立公告目录 `docs/releases/2026-10-11-production-increment/`。 |
| 2026-10-10 | 适配器线上响应诊断只在 Labs 通过 SafeHttpClient、robots.txt 校验、2 秒请求间隔和页数上限执行；调用 collect 后只读计数与截断状态，不持久化岗位数据。 | 需要真实上游响应验证 parser，同时避免在生产触发批次或写入岗位记录；人为页数上限通过 `truncated` 明确标记。 | 五个来源 Labs 直连元数据；35 个聚焦回归通过；生产 DB 未写入。 |
| 2026-10-10 | 修复确定的招聘 parser 契约差异，并保留严格结构校验；生产浏览器来源通过 socket 就绪后的 Worker 重建刷新 bind mount。 | Dahua 响应超过旧 256 KiB 上限；Beisen 可通过减小页大小处理截断；Getui 分类路由 ID 不是岗位 ID；Hotjob 的零结果响应允许 `pageSize=0`；浏览器来源失败由 Worker 旧目录 inode 导致。 | `apps/opportunities/checks/{dahua,beisen,getui,hotjob}.py`、Compose contract test、Labs 直连结果及生产只读 inode 对照。 |
| 2026-10-10 | 将招聘来源失败拆分为确定性运行时故障和待证据适配器故障；不以放宽时限处理。 | 最近 7 个定时批次中浏览器来源连续失败，生产 Worker 内 socket 不可见而宿主 socket 存在，根因是 Worker 绑定旧 RuntimeDirectory inode；Hotjob、Getui、Dahua、Meituan、Beisen 的响应无效也连续出现，但未保存上游响应体。浏览器故障需 socket 就绪后重建 Worker；parser 故障需安全响应契约证据。 | 生产 Worker/宿主 inode 对照、`kaj-opportunity-browser.service` 状态、生产只读错误聚合；未执行招聘采集或生产重启。 |
| 2026-10-10 | 首页侧边导航分区链接在 HTMX 成功更新文章列表后，使用 discovery 首页现有 `snapTo(articles)` 平滑定位文章区顶部。 | 在请求成功后计算锚点，避免文章区交换时滚动位置被覆盖；共用既有固定页眉偏移和减少动态效果策略。 | `static/src/home-navigation.js`；Labs 真实导航点击在 390/768/1440 和桌面深处滚动位置验证，落点与站点头部下沿对齐。 |
| 2026-10-10 | Labs 媒体只按当前测试库的 storage key 从旧 Labs 归档恢复非删除文件；不复制生产媒体，也不通过假数据绕过访问控制。 | 当前媒体数据库记录与归档文件逐项匹配，11 个非删除文件的大小和 SHA-256 一致；公开媒体 URL 已能读回 200，知识文档媒体匿名 404 属于权限策略。 | Labs `var/media`、`media_asset` 只读聚合、文件 SHA-256 与 `https://labs.kajspace.cn/_kaj/media/<id>` 状态读回。 |
| 2026-10-10 | 因开始答题的 500 已确认由 schema 漂移造成，按用户当前修复请求只在 Labs 测试库应用 `learning.0014_quizattempt_mode_and_more`；不改变题库 `security_review` 隐藏状态。 | 应用代码已读写 `QuizAttempt.mode`，数据库原先缺少字段；迁移后字段、约束和 migration 记录均已读回。题库可见性是独立安全状态。 | Labs `manage.py migrate learning --noinput` 退出 `0`；PostgreSQL 字段/约束查询、Django check、migration drift check。 |
| 2026-10-10 | 考试和刷题模式共用答题页底部主提交位置；刷题解析栏保留在工作区外层右侧第三栏（窄屏在答题区下方），按当前题揭晓状态展开/收起，切回已提交题恢复该题结果。 | 避免内层网格改变既有侧栏位置；未提交题收起时外层轨道和间距归零，并从键盘/无障碍顺序移除面板。 | `quiz_attempt.html`、`quiz.js`、`quiz.css`；旧版模板/Git 基线对照、CSS 构建及 Labs 哈希读回。答题页视觉读回因登录态缺失未完成。 |
| 2026-10-09 | 答题新增 `EXAM`/`PRACTICE` 两种模式；默认 `EXAM`，配置页选择。刷题须显式提交单题后才揭晓该题并锁定，自动保存仍不判分/泄露答案，最终整套提交只补处理未逐题提交的响应且不重复更新错题统计。 | 保留现有考试语义，同时满足逐题解析需求；服务端持久化模式和 response 揭晓状态，支持刷新/跨设备并防止未提交答案泄露。 | 用户需求；`test_quiz_modes.py` 聚焦回归；真实浏览器单题 POST/刷新和隔离 PostgreSQL 读回；migration `0014_quizattempt_mode_and_more`。 |
| 2026-10-09 | 下一轮 Labs 使用新分支 `codex/labs-next-20261009`，基于远端默认分支 `631253f`；旧脏 worktree 归档保留。 | 旧 Labs HEAD `a06a94f` 是正式应用 revision `42adeb4` 的父提交，且包含未提交代码/测试/文档；归档后重建可验证的干净起点且不丢工作。 | Docker Web/Worker/Beat revision `42adeb4`；`git diff 42adeb4..origin/main -- apps config templates static` 为空；新 worktree clean。 |
| 2026-10-09 | 每个 Labs 产品切片必须同步追加到新一轮公告台账，正式部署后再生成独立正式公告与部署记录。 | 避免从会话记忆追补发布内容，并保持 Labs 草稿与正式部署事实分离。 | `docs/releases/2026-10-09-next-iteration/announcement.md`；项目 Git/交付规则。 |
| 2026-09-16 | Use multi-document Agent handoff memory in the main worktree. | 当前项目跨会话、跨 Labs/正式快照、存在长期 backlog；索引与状态/风险/验证分离，恢复成本更低。 | `agent-handoff` bootstrap；`AGENT_HANDOFF.md` 与 `.agent-handoff/`。 |
| 2026-09-15 | 所有先行修改遵循 Labs-first；提交/推送从 Labs 任务分支开始，之后才同步主工作区。 | 主工作区存在历史脏改动，直接同步会覆盖未分类内容；Labs 应是测试和发布候选的事实起点。 | 用户当前工作流要求；`docs/operations/testing.md`；worktree 审计记录。 |
| 2026-09-15 | 性能测试文档由 Labs 提交并 fast-forward 到远端 `main`，提交为 `0b700d4`。 | 让外部测试机使用稳定、可追踪的 P0/P1/P2 任务与执行日志；不部署、不重启生产。 | Labs Git 读回、远端 `origin/main`、提交 `docs: 添加性能测试任务与执行记录`。 |
| 2026-09-15 | P0 先由服务器外部机器执行低风险只读基线。 | 避免本机 AI/浏览器/压测进程干扰正式服务器性能；P0 不调用 AGENT、不上传、不抓取招聘。 | `docs/operations/performance-testing/p0-production-canary.md`；用户确认。 |
| 2026-09-15 | AGENT capability check 按 Endpoint row version + schema 绑定；Endpoint 修改后必须重新严格检查。 | 文章解释、题库生成、知识审核使用不同 schema，不能用其他 schema 的成功检查授权。 | `apps/agents/services/invocations.py`、`apps/agents/services/checks.py`、生产只读状态。 |
| 2026-09-15 | 站内通知分为 Outbox 事件、Notification 本体和 NotificationReceipt 回执；Toast 不进入通知中心。 | 保证事务一致性、幂等投递、每用户已读隔离，并区分持久业务通知与临时操作反馈。 | `apps/core/events/`、`apps/notifications/`、通知模板/已读服务。 |
| 2026-09-20 | 岗位公开页的性能优化保留在 `apps/opportunities` 唯一 public query owner：合并三个筛选选项查询、复用已加载来源计数，并让 HTMX fragment 跳过完整页摘要。 | P0 隔离 PostgreSQL 证据显示筛选页从 5 条 owner SQL 降为 3 条，完整请求从 17 条降为 14 条；岗位分页仍固定为 count/page/prefetch 三条，无模板 N+1 或响应字段删减。 | `apps/opportunities/queries/public.py`、`apps/opportunities/views.py`；本轮临时聚焦回归探针（已清理）6 个测试、9 个既有领域回归通过。 |
| 2026-09-20 | 本轮正式发布只做运行时应用镜像增量切换；无待执行 migration 时不运行 migration，不启动招聘采集、Provider/AGENT 或状态补偿任务。 | 候选只读预检为空、备份和回退边界已建立；Web/Worker/Beat 按顺序切换后健康且岗位路径/静态资源返回 200。 | `docs/releases/2026-09-20-production-increment/deployment-record.md`；候选 `42adeb4ceb74` / 镜像 `sha256:26caccd5…`。 |

## Decision Guidelines

- Record durable decisions only.
- Include reason and evidence.
- Do not record guesses as decisions.
- If evidence is missing, mark it as `UNKNOWN`.
