# Workspace Map

## Repository Structure

- `apps/accounts/`: 账户、登录、会话、个人资料和权限入口。
- `apps/content/`, `apps/authoring/`: 文章、不可变修订、发布状态和作者编辑工作台。
- `apps/discovery/`: 公开阅读、文章索引、作者主页和 query/presenter 组合。
- `apps/administration/`: 管理页面编排；不拥有其他领域事实。
- `apps/notifications/`: Notification、NotificationReceipt、模板、Consumer 和已读服务。
- `apps/agents/`: Endpoint、AGENT Profile/Prompt、LangChain Gateway、schema capability、token ledger/reservation。
- `apps/learning/`: 知识文档、审核、题库、答题记录和错题本。
- `apps/opportunities/`: 招聘来源、岗位、适配器、检查运行和筛选查询。
- `apps/core/`, `apps/operations/`, `config/`: ID、事件/Outbox、TaskRun、容量、错误和运行配置。
- `static/src/`, `templates/`: 前端模块、主题、HTMX/Alpine 增强和服务端模板。
- `docker/`, `scripts/`, `var/`: 运行/测试入口；`var/`、凭据、数据库、媒体和日志不得进入 Git。
- `AGENT_HANDOFF.md`: handoff 索引和恢复顺序。
- `.agent-handoff/`: 当前状态、决策、验证、风险和 backlog。

## Main Entry Points

- `manage.py`: Django 管理入口。
- `config/settings/`: base/test/运行配置；不要读取或输出秘密文件。
- `config/urls.py` 与各 app `urls.py`: 页面和局部 HTTP 入口。
- `docker/scripts/deploy`: fail-closed 部署计划器/模拟器，不代表真实生产部署。
- `scripts/test`: 隔离依赖门禁后运行 pytest 的固定入口。

## Test Entry Points

- `uv run pytest`: 隔离 PostgreSQL/Redis/Mailpit 下的后端测试。
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python manage.py check`
- `npm run build`（或受影响的 `npm run build:css` / `npm run build:js`）。
- `npx playwright test`；真实浏览器必须经 `/usr/local/bin/blog-playwright-cli`、`blog-browser` 用户和单 worker。
- 正式性能测试文档：`/home/code/.codex-worktrees/personal-blog/production-688c25b/docs/operations/performance-testing/`。

## Docs And Specs

- `README.md`: 项目边界和固定入口。
- `docs/planning/implementation-todolist.md`: 102 项实施清单索引；部分历史提交信息可能滞后于当前 Git 事实。
- `docs/architecture/README.md`: owner、数据、权限、事件、任务和交付门禁总览。
- `docs/prototype/page-state-matrix.md`: 路由、身份、加载/空/错误/成功状态和视口矩阵。
- `docs/operations/testing.md`: Labs 同步、隔离测试、Provider 密钥和浏览器边界。
- `docs/operations/README.md`: 运维、备份、容量、部署和性能测试入口。
- `docs/operations/performance-testing/`: P0/P1/P2 任务和执行日志。

## Worktree Map

- `/home/code/personal-blog`: 开发主工作区，`main`，当前脏且落后远端，不得直接覆盖。
- `/home/code/.codex-worktrees/personal-blog/labs-test-environment`: Labs 快照，当前 detached `0b700d4`，服务已停。
- `/home/code/.codex-worktrees/personal-blog/production-688c25b`: 正式版本快照，当前 detached `1f9d47c`，仅保留文档准备改动。
- `/home/code/personal-blog/var/production`: 生产 Compose 运行目录，不是源码 worktree；含凭据、数据库、媒体和备份，禁止复制/清理。

## Durable Project Context

- PostgreSQL 是业务事实；Redis 只承载可丢失的验证码、限流、冷却和公开缓存；跨领域副作用经事务 Outbox 和幂等 Consumer。
- View 只编排 HTTP/模板，业务授权、事务、锁、审计、状态和 Outbox 属于领域 service/query/task owner。
- Labs-first：先在 Labs 编码和验证，按任务清单同步读回；确认后从 Labs 任务分支提交/推送，再让主工作区同步。
- 生产部署、迁移、备份、真实邮件、服务重启、生产数据修复和 Git 交付必须由用户当前回合明确授权。
- 当前正式性能测试分 P0（低风险只读基线）、P1（隔离环境容量）、P2（AGENT/故障恢复），必须按顺序推进。
- AGENT 调用要求当前 Endpoint row version 与对应 schema 的严格 `SCHEMA_SUPPORTED` capability check 匹配；Endpoint 修改会使旧检查失效。

## Project Conventions

- 每次只保留一条 Todo 为 `进行中`，按 `implementation-readiness.md` 的前置关系执行。
- 先读规则、owner、调用方和测试；优先复用唯一 owner，不建立第二套权限、通知、缓存、重试或错误体系。
- 有意义的逻辑改动默认 RED → 最小闭合实现 → GREEN → 相关回归；文档/轻量资源改动做静态检查和范围相称验证。
- 资源预算默认串行、一个重型执行组、单 worker；出现脏工作区不得用 reset/stash/宽泛同步掩盖。
- 新文件 UTF-8；写入使用 `apply_patch`；不把秘密、正文、Cookie、Token、连接串或生产个人数据写进差异/日志。
