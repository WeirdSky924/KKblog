# Risks, Blockers, And Unknowns

## Current Blockers

- 管理员重置功能所需 Labs schema 已经用户明确授权并应用；迁移状态、字段、约束和 health/readiness 均读回成功。剩余未知仅是管理员点击后的邮件实际投递/链接兑换；缺少授权管理员 session 和四项隔离 `KAJ_TEST_*` 值，不得通过共享 Labs DB/Mailpit 测试或发送真实邮件。
- CSRF 403 修复的协议级验证已通过，但修复后的真实浏览器流受 Labs 两次 `504 Gateway Time-out` 阻断；需要 Labs 稳定后再做一次真实无效令牌 422 读回。不要把 curl 协议对比写成完整浏览器验收。
- 本次 Playwright 首次导航发生 504/超时，页面后来可读；截图和主题交互超时。390px fragment 清除/表单/无溢出/Tab 焦点读回成功；768/1440 视觉和认证态流程未验收。不要把伪造 fragment 的 UI 检查说成密码重置成功。
- Labs Web、Worker、Beat 当前为 `active/running`；P12 PostgreSQL/Redis/Mailpit 已启动并通过连接/健康读回，数据卷保留。Outbox service 为 `failed/timeout`、timer 为 `inactive/dead`。Labs 已应用 `learning.0014/0015`、`comments.0006_guestbook_board`、`accounts.0010_account_author_permission_requested_at` 和 `accounts.0011_admin_password_reset`，DB schema 读回正常。
- 2026-10-16 用户实测发现通知未到达；根因是 Worker 于 10 月 13 日启动、未加载 10 月 16 日新增事件路由。重启 Labs Worker 后注册/申请事件和管理员未读通知回执均读回成功。两条旧 `apps.operations.weekly_backup` 失败事件仍 pending，留待 B-027 调查。
- 答题、首页导航、招聘适配器和增量镜像聚焦验证均完成；生产 browser sandbox 已更新并通过真实 Feishu source service smoke。
- Labs 当前数据库的 3 个题库卷均为 `ADMIN_HIDDEN`，锁定原因 `security_review`；公开题库页返回 `0 个结果` 是业务可见性事实，不应通过原始 SQL 静默改公开。若要测试公开答题入口，需要用户授权由 learning 管理 owner 恢复指定题库卷。
- Labs `var/media` 初始为空导致数据库中 11 个非删除媒体引用返回 404；已从旧 Labs 归档按 storage key 定向恢复，当前媒体文件存在且属主为 `kaj-labs`。后续禁止从 `/home/code/personal-blog/var/production/media` 复制，除非用户明确授权并完成数据边界评审。
- Labs 当前媒体数据库记录与恢复文件的大小和 SHA-256 已逐项一致；知识文档媒体匿名 404 是既有访问控制结果，不应当作文件缺失。
- 外部正式 P0 复测尚未执行；本地隔离回归不能替代公网并发 1/2/5、Nginx timing 和生产数据库/队列快照。
- 首页留言板的公开读取已经在 Labs 真实页面验证；本轮没有登录发布或真实留言写入，2/20 配额、管理动作和删除事实由隔离 PostgreSQL 回归覆盖。正式环境仍未应用迁移。
- 2026-10-15 用户复测确认早先的面板宽高快照方案在真实发布入口下仍会缩小；该模拟验证已被稳定页面容器方案替代。当前桌面等价 HTMX 替换、留言区实际滚轮和 390px 边界通过；真实认证 POST 仍未执行，因为没有可授权的登录态。
- 新作者申请页面已通过隔离 PostgreSQL HTTP 回归；Labs schema 已应用并读回，但登录后路由尚未在真实数据库中完成浏览器验收，因为没有可授权登录 session。不要把匿名 302、静态模板或隔离测试说成认证态验收。
- 两条历史每周备份 `task.final_failed.v1` 事件仍持续 transport failure，当前没有对应 consumer 记录或通知；重试需先查明根因。不得用同步直接发通知、删除事件或清空状态绕过既有 Outbox owner。账户注册/申请通知已由重载后的 Celery Worker 正常消费。

## Current Risks

- 本轮一次宽泛本地检索错误读取了受保护的 Labs SMTP 环境文件并使其值进入工具输出；迁移命令强制使用 Mailpit，未发送邮件、未修改配置或写入仓库。该 SMTP 凭据应由运维按流程立即轮换。
- 本轮 35 条来源已通过现有 service 逐条复查：30 `HEALTHY`，1 `DEGRADED/TRUNCATED`，4 `STALE`（Qcraft timeout、2 Hotjob response invalid、1 Meituan response invalid）。保留真实失败终态，不能用直接 SQL 清状态。
- 正式 browser sandbox 当前在版本化 release `d06af75a9c315a9966d612a34a9ba27211629583`；Worker socket mode `0660`、UID/GID `999:10001`，设备/inode 与宿主一致。
- Nginx maintenance marker 已移除；正式 Web/Worker/Beat 候选运行且健康，Caddy 保持 `2cbead0`。备份与 Compose 快照已保存为 `0600`。
- 定向来源复查期间 PostgreSQL backend 两次记录 exit-code 2 后自动 WAL recovery。容器 restart count `0`、OOM `false`，当前 healthy；根因未明，需另案调查。
- `learning.0014` 与 `0015` 必须在同一维护窗口完成；若 `0015` 失败，保持维护模式，不开放旧应用写入。新刷题记录产生后，旧应用回退不理解 `PRACTICE`，后续应前向修复。
- 旧 Labs worktree 已归档并保留脏改动；后续需要某项旧工作时先逐文件审查，禁止整体复制或覆盖新基线。
- 本轮生产部署代码基线为 `d06af75`；Labs 当前迭代分支为 `codex/labs-next-20261013`，生产应用运行 `d06af75a9c31`。
- 根主工作区仍有 handoff 修改与未跟踪 P0 文档；本轮没有清理或同步这些改动，后续 Git 交付必须排除无关内容。
- 旧 `codex/labs-next-iteration` 本地分支及远端跟踪引用仍存在且未推送更新；当前 Labs 工作不使用该旧分支。
- 正式项目快照 `/home/code/.codex-worktrees/personal-blog/production-688c25b` 仍有性能文档未提交改动；运行目录 `/home/code/personal-blog/var/production` 含生产凭据、数据库、媒体和备份，禁止当作源码同步目标。
- P0 性能测试尚未在本轮重新执行；本轮应用与定向来源检查读回不能替代公网并发 1/2/5 与 Nginx timing 测试。
- 2026-09-15 的历史只读诊断曾发现生产知识审核 profile 缺少匹配当前 Endpoint row version 的 `knowledge-review.v1` 严格能力检查；本轮未复核生产状态，重试前需重新只读确认。
- 其他历史规划文档可能保留其编写时的运行状态；当前生产 revision 与迁移状态以带日期的发布执行记录为准，README、架构入口、运维入口和实施清单摘要已更新至 2026-10-12。

## Unknowns / Confirmations Needed

- UNKNOWN: 是否授权解除指定题库卷的 `security_review` 管理隐藏；该动作必须通过 `apps.learning` 管理服务并留下审计。
- UNKNOWN: 根主工作区未跟踪 P0 文档是否应独立交付；不能与 Labs 迭代自动混交。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun 和 Outbox 的只读快照。
- UNKNOWN: 本机是否有可用且获授权的 Labs 管理员/目标用户浏览器状态及安全测试邮箱，以完成按钮 POST 与 Mailpit 链接兑换；未创建或借用账户。
- UNKNOWN: 隔离测试环境何时提供 `KAJ_TEST_DATABASE_URL`、`KAJ_TEST_REDIS_URL`、`KAJ_TEST_MAILPIT_SMTP_URL`、`KAJ_TEST_MAILPIT_API_URL`；不得退化为共享 Labs 数据库/Mailpit。
- UNKNOWN: 是否需要同时维护 Claude Code 的 `.claude/CLAUDE.md`；当前只生成 Codex `AGENTS.md` handoff protocol。

## 2026-10-13 Labs Runtime Risk

- Labs Outbox timer/service 当前停止。两次启动都在 30 秒 start timeout 内失败；日志记录 2 条待处理 `task.final_failed.v1` 的 transport failure，且批处理结束后进程未及时退出。没有直接改写 `core_outbox_event`。
- Web/Worker/Beat 最终恢复为 active/running，P12 PostgreSQL/Redis/Mailpit 重启后通过连接/健康读回；首次 Web 启动曾因 swap 等待延迟，主机仍处于黄色资源区间，后续测试必须保持单一重型执行组。
- Labs 的 `127.0.0.1` 是受信代理地址；本地 health 读回必须带 `X-Kaj-Client-IP`，公网 Nginx 路径已正常返回 `200`。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
