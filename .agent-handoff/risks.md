# Risks, Blockers, And Unknowns

## Current Blockers

- Labs Web、Worker、Beat、Outbox service 与 Outbox timer 均为 `inactive/dead`；P12 PostgreSQL/Redis/Mailpit 已退出，数据卷保留。Labs 已应用 `learning.0014/0015`，DB 默认值为 `EXAM`。
- 答题、首页导航、招聘适配器和增量镜像聚焦验证均完成；生产 browser sandbox 已更新并通过真实 Feishu source service smoke。
- Labs 当前数据库的 3 个题库卷均为 `ADMIN_HIDDEN`，锁定原因 `security_review`；公开题库页返回 `0 个结果` 是业务可见性事实，不应通过原始 SQL 静默改公开。若要测试公开答题入口，需要用户授权由 learning 管理 owner 恢复指定题库卷。
- Labs `var/media` 初始为空导致数据库中 11 个非删除媒体引用返回 404；已从旧 Labs 归档按 storage key 定向恢复，当前媒体文件存在且属主为 `kaj-labs`。后续禁止从 `/home/code/personal-blog/var/production/media` 复制，除非用户明确授权并完成数据边界评审。
- Labs 当前媒体数据库记录与恢复文件的大小和 SHA-256 已逐项一致；知识文档媒体匿名 404 是既有访问控制结果，不应当作文件缺失。
- 外部正式 P0 复测尚未执行；本地隔离回归不能替代公网并发 1/2/5、Nginx timing 和生产数据库/队列快照。

## Current Risks

- 本轮 35 条来源已通过现有 service 逐条复查：30 `HEALTHY`，1 `DEGRADED/TRUNCATED`，4 `STALE`（Qcraft timeout、2 Hotjob response invalid、1 Meituan response invalid）。保留真实失败终态，不能用直接 SQL 清状态。
- 正式 browser sandbox 当前在版本化 release `d06af75a9c315a9966d612a34a9ba27211629583`；Worker socket mode `0660`、UID/GID `999:10001`，设备/inode 与宿主一致。
- Nginx maintenance marker 已移除；正式 Web/Worker/Beat 候选运行且健康，Caddy 保持 `2cbead0`。备份与 Compose 快照已保存为 `0600`。
- 定向来源复查期间 PostgreSQL backend 两次记录 exit-code 2 后自动 WAL recovery。容器 restart count `0`、OOM `false`，当前 healthy；根因未明，需另案调查。
- `learning.0014` 与 `0015` 必须在同一维护窗口完成；若 `0015` 失败，保持维护模式，不开放旧应用写入。新刷题记录产生后，旧应用回退不理解 `PRACTICE`，后续应前向修复。
- 旧 Labs worktree 已归档并保留脏改动；后续需要某项旧工作时先逐文件审查，禁止整体复制或覆盖新基线。
- 本轮生产部署代码基线为 `d06af75`；Labs 服务已停止，生产应用已切换到 `d06af75a9c31`。
- 根主工作区仍有 handoff 修改与未跟踪 P0 文档；本轮没有清理或同步这些改动，后续 Git 交付必须排除无关内容。
- 旧 `codex/labs-next-iteration` 本地分支及远端跟踪引用仍存在且未推送更新；当前 Labs 工作不使用该旧分支。
- 正式项目快照 `/home/code/.codex-worktrees/personal-blog/production-688c25b` 仍有性能文档未提交改动；运行目录 `/home/code/personal-blog/var/production` 含生产凭据、数据库、媒体和备份，禁止当作源码同步目标。
- P0 性能测试尚未在本轮重新执行；本轮应用与定向来源检查读回不能替代公网并发 1/2/5 与 Nginx timing 测试。
- 2026-09-15 的历史只读诊断曾发现生产知识审核 profile 缺少匹配当前 Endpoint row version 的 `knowledge-review.v1` 严格能力检查；本轮未复核生产状态，重试前需重新只读确认。
- `docs/planning/implementation-todolist.md` 等历史文档含旧远端提交号/部署口径；Git、服务和数据库读回优先级高于历史文案。

## Unknowns / Confirmations Needed

- UNKNOWN: 是否授权解除指定题库卷的 `security_review` 管理隐藏；该动作必须通过 `apps.learning` 管理服务并留下审计。
- UNKNOWN: 根主工作区未跟踪 P0 文档是否应独立交付；不能与 Labs 迭代自动混交。
- UNKNOWN: 外部 P0 测试机是否能取得 PostgreSQL、Redis、TaskRun 和 Outbox 的只读快照。
- UNKNOWN: 是否需要同时维护 Claude Code 的 `.claude/CLAUDE.md`；当前只生成 Codex `AGENTS.md` handoff protocol。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
