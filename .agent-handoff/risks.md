# Risks, Blockers, And Unknowns

## Current Blockers

- Labs Web `/home/code/.codex-worktrees/personal-blog/labs-test-environment` 当前为 `active/running`，公网 `/health/live` 返回 `200`；测试库已应用 `learning.0014` 和 `0015`，读回模式数据库默认值 `EXAM`。答题解析栏位置由用户确认，首页导航平滑定位已通过 390/768/1440 浏览器验证。
- 招聘适配器、Worker socket、Caddy 维护路由和增量镜像合同回归为 `36 passed`；Labs 已通过 SafeHttpClient/robots 检查完成五种来源有界直连，未写招聘数据。Beisen/Hotjob/Meituan 的 `truncated=True` 是刻意设置的测试上限。
- Labs 没有 Worker 或浏览器沙箱；`kaj-labs.service` 只运行 Web。生产 socket inode 问题已由生产只读证据确认，但 Worker 重建后的 socket 可见性尚未在 Labs 运行态验证。
- Labs 当前数据库的 3 个题库卷均为 `ADMIN_HIDDEN`，锁定原因 `security_review`；公开题库页返回 `0 个结果` 是业务可见性事实，不应通过原始 SQL 静默改公开。若要测试公开答题入口，需要用户授权由 learning 管理 owner 恢复指定题库卷。
- Labs `var/media` 初始为空导致数据库中 11 个非删除媒体引用返回 404；已从旧 Labs 归档按 storage key 定向恢复，当前媒体文件存在且属主为 `kaj-labs`。后续禁止从 `/home/code/personal-blog/var/production/media` 复制，除非用户明确授权并完成数据边界评审。
- Labs 当前媒体数据库记录与恢复文件的大小和 SHA-256 已逐项一致；知识文档媒体匿名 404 是既有访问控制结果，不应当作文件缺失。
- 外部正式 P0 复测尚未执行；本地隔离回归不能替代公网并发 1/2/5、Nginx timing 和生产数据库/队列快照。

## Current Risks

- 生产浏览器服务 active，但当前 Worker 容器内配置的 socket 不存在；根因为容器 bind mount 指向旧 RuntimeDirectory inode。重建 Worker 后必须在来源重查前读回 socket 和 healthcheck。
- 生产 35 条 `STALE` 来源分别记录 26 个浏览器 socket 错误、8 个响应契约错误和 1 个超时。当前请求已明确授权状态修复；只能通过现有来源检查 service 逐条重查并读回终态，不可直接把状态字段改为成功，也不运行全量扫描。
- 五个本轮代码提交已在任务分支本地形成，Git 远端集成尚未完成；当前请求明确授权提交/推送和正式增量更新。
- 生产容器使用 `/home/code/personal-blog/var/production/compose.runtime.yaml`；正式更新会定向切换 Web/Worker/Beat/Caddy 镜像，先保存权限 `0600` 的 Compose 快照，不读取或输出环境秘密。
- `learning.0014` 与 `0015` 必须在同一维护窗口完成；若 `0015` 失败，保持维护模式，不开放旧应用写入。新刷题记录产生后，旧应用回退不理解 `PRACTICE`，后续应前向修复。
- Docker Hub 基础镜像元数据请求超时；Caddy 候选已复用现有正式镜像构建并通过 `caddy adapt --validate`。Web 候选使用本轮新增的基线源码增量 Dockerfile，正式构建仍待执行。
- 旧 Labs worktree 已归档并保留脏改动；后续需要某项旧工作时先逐文件审查，禁止整体复制或覆盖新基线。
- 当前 Labs 分支 `codex/labs-next-20261009` 跟踪 `origin/main`，HEAD `631253f`；正式应用 revision 为 `42adeb4`，其后的提交仅有文档差异。
- 根主工作区仍有 handoff 修改与未跟踪 P0 文档；本轮没有清理或同步这些改动，后续 Git 交付必须排除无关内容。
- 旧 `codex/labs-next-iteration` 本地分支及远端跟踪引用仍存在且未推送更新；当前 Labs 工作不使用该旧分支。
- 正式项目快照 `/home/code/.codex-worktrees/personal-blog/production-688c25b` 仍有性能文档未提交改动；运行目录 `/home/code/personal-blog/var/production` 含生产凭据、数据库、媒体和备份，禁止当作源码同步目标。
- P0 性能测试尚未重新执行；正式环境已完成运行时增量切换，但当前只有代码级证据、发布 smoke 和历史部分失败结果，不能把它们当作优化后的 P0 通过证据。
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
