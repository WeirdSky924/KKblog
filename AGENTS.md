# Kaj 的小房间项目规则

本文件适用于仓库内全部文件。修改子目录前继续查找更近的 `AGENTS.md`；更近规则可以补充但不能削弱本文件的安全、测试和授权边界。

## 真值与入口

1. 当前用户指令。
2. `docs/planning/implementation-todolist.md` 及对应阶段文件。
3. `docs/planning/implementation-readiness.md`。
4. `docs/architecture/README.md` 指向的 owner、服务、数据、权限、事件和任务契约。
5. `docs/prototype/page-state-matrix.md`。

原型截图和演示代码不是业务真值。发现冲突时停止实现并记录来源与影响，不创建平行口径。

## 实施纪律

- 每次只保留一条 Todo 为 `进行中`，按前置关系顺序完成。
- 修改前先查找调用方与复用点，稳定能力只能有一个 owner。
- 有意义的行为变更执行聚焦 RED、最小完整实现、GREEN 和相关回归。
- View、Task 和模板只调用 owner 的稳定 service/query/event，不复制领域规则。
- PostgreSQL 是持久事实；Redis、缓存和锁不能成为最终裁决。
- 外部副作用在事务提交后执行，或由版本化 Outbox 驱动。
- 错误、日志、事件和审计不得包含密码、验证码、token、Cookie、连接串、正文、原路径或其他秘密。

## 当前阶段 Labs 同步

- 当前测试优化阶段中，每个完成且通过聚焦验证的修改切片默认同步到 `https://labs.kajspace.cn`，用户无需重复要求更新 Labs。
- 同步前必须读回 `kaj-labs.service` 的 `WorkingDirectory/ActiveState/SubState`。当前服务工作目录是 `/home/code/.codex-worktrees/personal-blog/labs-test-environment`；当前开发目录与其不同时，只把本任务已完成的运行时文件定向同步到该 Labs worktree，并保留目标内的无关改动。
- 不同步或删除 `.git`、`.env`、`.venv`、`var/`、数据库、媒体、备份、日志、缓存、测试产物、`node_modules` 或凭据；不得使用会清空目标目录的宽泛同步命令。
- Python 源码和模板由宿主机 `kaj-labs.service` 热重载；前端源码先生成对应 `static/dist/` 产物，再同步本任务产物。普通代码同步不重建或替换容器，也不重启服务。
- 同步后读回服务仍为 `active/running`、`/health/live` 返回 `200`，并验证一个直接受影响的 Labs 页面或安全用户流。热重载或读回失败时停止并报告，不自动扩大为重启、迁移或数据修复。
- 本约定只授权非生产 Labs 的源码、模板和静态产物同步及只读 smoke；不授权生产发布、服务或容器重启、镜像操作、migration、数据修复、真实邮件、Git 写操作或其他外部写操作。详细步骤以 `docs/operations/testing.md` 为准。

## 轻量修改验证预算

- 开始前先按真实风险定验证范围。复用现有反馈组件的提示文案、图标、少量样式或同类局部调整，且不改变数据、权限、路由、公共契约或布局责任时，属于轻量修改。
- 轻量任务的实现也只覆盖用户明确要求和正确性必需行为，不主动增加通用抽象、额外状态策略或可选交互；范围没有扩大，验证范围也不得自行扩大。
- 轻量修改默认只做：确认 owner 与调用链、目标语法/构建检查、一次代表性真实路径和 Labs 读回。用户报告与源码已能证明行为缺失时，不为形式额外执行浏览器 RED。
- 已验证公共组件的响应式、主题、键盘和可访问性能力可以复用为基础证据；只验证本次新增差异，不自动扩展到全视口、全主题、连续操作、计时、悬停和失败矩阵。只有改动直接触及这些维度或发现异常时才扩大。
- 窄范围轻量任务以 10 分钟为提醒线；接近或超过时先报告原因，并收缩到证明请求所必需的最小证据。一次代表性 GREEN、无相关控制台/HTTP 错误且 Labs 读回成功后立即停止，不为增加信心继续追加场景。
- 验证环境出现与改动无关的服务、会话或工具故障时最多恢复一次；仍失败则使用更便宜的可靠证据或准确报告缺口，不连续更换服务器、密钥、身份或测试入口。
- 只有权限、持久化、迁移、跨模块契约、共享交互基础设施或明确响应式布局风险，才进入完整 RED/GREEN、数据读回和多视口用户流。

## Git 与交付

- 普通项目文件的创建、编辑、移动或删除不要求预先创建或切换任务分支；可以在当前工作区完成，但必须保留并区分已有无关改动。
- 准备执行 `git add`、commit 或 push 时，才从已核验远端默认分支创建或确认 `codex/<task>` 任务分支；空仓以 `main` 初始化后再建任务分支。不得把无关工作区改动混入交付。
- 不直接在默认分支提交或推送，不覆盖或隐藏用户改动。
- 除非用户在当前回合明确要求，不执行 `git add`、commit、push、merge、release 或 deploy。
- 部署、生产迁移、真实邮件、生产备份和服务重启也需要当前回合明确授权。
- 完成报告必须给出新鲜命令、退出码、读回证据、未执行项和残余风险。

## 数据与环境

- 开发和测试只使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit。
- 生产缺少真实域名、管理员邮箱、Resend 发件身份、密钥或其他必需秘密时必须拒绝启动。
- `.env`、`var/`、数据库、媒体、备份、日志和凭据不得进入 Git。
- 测试必须使用隔离 PostgreSQL、Redis、临时媒体和邮件环境，不能连接生产或共享数据。

## 用户界面

- 页面状态遵循 `docs/prototype/page-state-matrix.md`，覆盖角色、加载、空、422、系统错误、禁用、无权、成功和恢复。
- 用户可见改动使用 `/usr/local/bin/blog-playwright-cli` 验证 390、768（适用时）和 1440 视口、三主题、键盘与焦点。
- 不以静态截图、DOM 存在或 mock 代替真实点击和持久化读回。

<!-- AGENT_HANDOFF_PROTOCOL:START -->
# Codex Agent Handoff Protocol

Layout: multi-document

## Required Startup Routine

Before making a plan or editing files, read:

1. `AGENT_HANDOFF.md`
2. `.agent-handoff/snapshot.md`
3. `.agent-handoff/risks.md`
4. `.agent-handoff/backlog.md`
5. Additional `.agent-handoff/` files only when needed by the current task, following the Recovery Reading Order in `AGENT_HANDOFF.md`
6. The source files directly relevant to the user's current request

Use the handoff files as continuity memory, but verify implementation details from source files before changing behavior.

## Default Implementation Standard

For non-trivial development work, target production/commercial-grade quality by default rather than minimum viable implementation. Prefer robust, maintainable solutions with appropriate validation, runtime and edge-case consideration, and clear reporting of what was and was not tested. Keep scope aligned with the user's request; do not add unrelated features or speculative abstractions.

## Stable File Reading Protocol

To avoid Read tool line-number or offset drift:

1. Prefer dedicated search/read tools for ordinary file lookup, content search, and file reads.
2. Confirm file size before reading large or volatile files, using line counts or targeted searches when needed.
3. Search for exact targets first, then read small exact ranges around those targets.
4. Keep Read ranges no larger than 240 lines unless the file is known to be small.
5. If Read returns unexpected empty output, offset warnings, stale snippets, inconsistent line numbers, `file is shorter than the provided offset`, or an API termination after a Read attempt, stop paging with Read for that file immediately.
6. Treat Read `offset` as a line number, not a character offset. Never retry the same out-of-range offset, and never guess by adding zeros or using large approximate offsets. If the tool reports the file has N lines, all follow-up Read offsets for that file must be within `0..N`.
7. Recover from Read offset failure by re-anchoring with a targeted `Grep` for the section/title/symbol, or by reading a small known-valid range such as offset `0`; only then read a small range around the confirmed line number.
8. When Read becomes unreliable, use shell verification commands such as `wc -l`, `rg -n`, and `sed -n '<start>,<end>p'` with quoted paths; keep ranges small and record that fallback in validation notes when relevant.
9. Treat read-only shell inspection commands (`wc`, `rg`, `grep`, `sed -n`, `ls`, `pwd`, and non-mutating `git status`/`git diff`/`git log`/`git ls-files`) as safe query operations. They should be pre-approved in project settings where possible so source verification does not require repeated manual approval.
10. Do not propose or edit code based on uncertain offsets; re-anchor with search results first.

## Continuation Recovery Guard

If the user says `continue`, `继续`, `Continue from where you left off.`, or any equivalent continuation request, treat it as an explicit instruction to resume the task. Do not answer `No response requested.` and do not stop silently. First state the last known objective and next concrete action, then continue. If context is insufficient, recover from the handoff files and task-relevant source files before acting.

## Durable Handoff Memory

The repository uses multi-document durable handoff memory:

- `AGENT_HANDOFF.md`: index and recovery route
- `.agent-handoff/snapshot.md`: current objective, status, next actions, active files, blockers, and open questions
- `.agent-handoff/workspace.md`: repository map, entry points, commands, and stable context
- `.agent-handoff/decisions.md`: durable decisions with reasons and evidence
- `.agent-handoff/work-log.md`: recent operational work
- `.agent-handoff/validation.md`: validation commands/checks and results
- `.agent-handoff/backlog.md`: pending work
- `.agent-handoff/risks.md`: risks, blockers, unknowns, and confirmations
- `.agent-handoff/archive.md`: compressed old history

Maintain the smallest relevant file. Do not put all state into `AGENT_HANDOFF.md`; it is an index.

## Handoff Size Discipline

- Keep `AGENT_HANDOFF.md` short; it is an index.
- Keep `.agent-handoff/snapshot.md` short, current, and action-oriented.
- Keep only recent, still-relevant work in `.agent-handoff/work-log.md`.
- Prefer updating existing bullets over appending duplicate or contradictory notes.
- Move stale long history to `.agent-handoff/archive.md`.
- In an ongoing uninterrupted chat, reread only relevant handoff files after compaction, resume, uncertainty, or task changes.

## Mandatory Closeout Protocol

Before any final response for a non-trivial task, update the relevant handoff files without waiting for the user to ask.

Minimum required updates:

- Refresh `.agent-handoff/snapshot.md` with current objective, status, next actions, active files, blockers, and open questions.
- Add or update `.agent-handoff/work-log.md` when files or task status changed.
- Add `.agent-handoff/validation.md` entries for commands/checks run or intentionally not run.
- Record durable decisions in `.agent-handoff/decisions.md`.
- Update `.agent-handoff/backlog.md` and `.agent-handoff/risks.md` when follow-ups, blockers, risks, or unknowns changed.
- Remove or rewrite stale state that would mislead the next agent.

If the task was purely conversational and no project state changed, no file update is required.

## Work Discipline

- Do not assume which subproject is active. Infer it from the user request, handoff files, and repository evidence.
- Prefer existing project conventions over new abstractions.
- Read files before editing them.
- Keep edits scoped to the task.
- Do not modify generated dependency folders unless explicitly asked.
- Never revert unrelated user or agent changes.
- Record validation honestly. If tests or checks were not run, say so in handoff files and in the final response.

## Session Closeout Checklist

Before final response, update the relevant `.agent-handoff/` files with final task status, files changed, commands/checks run and outcomes, and remaining risks, blockers, open questions, or next steps.
<!-- AGENT_HANDOFF_PROTOCOL:END -->
