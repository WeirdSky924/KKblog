# Kaj 的小房间（Kajspace）

Kaj 的小房间是一个面向中文创作者的多用户博客与内容管理平台。项目以 Django 模块化单体为核心，使用服务端模板，并用 HTMX、Alpine.js 和少量 JavaScript 增强交互；文章版本、权限、审核、后台任务和外部模型调用分别由清晰的领域模块管理。

> 本页状态核对日期：2026-10-12。运行数据使用各自注明的生产只读快照日期；它们不是实时仪表盘，也不代表长期 SLO。

## 当前状态

| 项目 | 当前可核验状态 | 证据 |
| --- | --- | --- |
| 正式应用 | 2026-10-11 增量发布完成；Web、Worker、Beat 运行代码 revision 为 `d06af75`，镜像标签为 `kaj-blog-web:d06af75a9c31`。 | [正式增量执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md) |
| 仓库主线 | 远端 `main` 为 `91b88e7`。生产部署点之后的主线提交只更新发布记录和 handoff 文档；生产运行版本仍记录为 `d06af75`。 | [本轮正式公告](docs/releases/2026-10-11-production-increment/announcement.md) |
| 数据库 | `learning.0014` 与 `learning.0015` 已应用；答题模式约束存在，数据库默认模式为 `EXAM`。 | [正式增量执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md) |
| 公网入口 | 正式入口由宿主 Nginx 提供，Caddy 保持 `2cbead0` 下游版本。2026-10-12 现场读回：主页、`/health/live`、`/health/ready` 均返回 HTTP `200`。 | [正式增量执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md)；本次只读 HTTP 核验 |
| Labs 测试环境 | 2026-10-12 核验时 Web、Worker、Beat、Outbox service/timer 均为 `inactive/dead`；P12 PostgreSQL、Redis、Mailpit 容器均已退出，数据卷保留。 | [测试环境说明](docs/operations/testing.md)；`.agent-handoff/validation.md` |
| 正式性能金丝雀 | P0 正式环境低风险性能与容量基线尚未执行；当前健康检查不能替代并发、延迟、数据库和队列指标复测。 | [P0 任务](docs/operations/performance-testing/p0-production-canary.md)；[P0 执行记录](docs/operations/performance-testing/p0-production-canary.execution.md) |

正式更新由人工按发布记录执行；仓库没有自动生产部署命令适配器。未来的生产 migration、备份、部署和服务重启仍需当次明确授权。2026-10-11 的实际步骤、镜像、迁移、备份和读回结果以本页链接的执行记录为准。

## 产品能力

| 能力 | 当前实现范围 | 主要 owner |
| --- | --- | --- |
| 账户与权限 | 登录会话、验证与访问控制；访客、用户、作者和管理员按服务端策略获得不同能力。 | `apps.accounts`、`apps.administration` |
| 文章与作者工作台 | 草稿和不可变文章修订、预览/发布、定时发布、版本恢复、Markdown/ZIP 导入预览及作者管理。 | `apps.content`、`apps.authoring` |
| 阅读与发现 | 首页、分区、标签、文章详情、搜索、书签、主题和 SEO 读取投影。 | `apps.discovery`、`apps.navigation` |
| 评论与内容治理 | 文章评论和留言、缓冲与管理、举报、申诉、审核和终局裁决。 | `apps.comments`、`apps.moderation` |
| 媒体 | 头像、封面、正文图片和附件的上传校验、受控存储、引用及生命周期管理。 | `apps.media` |
| 知识与答题 | 知识文档、题库、答题记录和错题；答题支持考试模式与逐题查看解析的刷题模式。 | `apps.learning` |
| 招聘机会 | 招聘来源适配器、岗位列表与筛选、来源检查和后台任务。 | `apps.opportunities` |
| 后台平台能力 | Outbox 通知、审计与任务运行记录、数据交换、Umami 管理入口、运维状态，以及受限的 Provider/AGENT 网关。 | `apps.notifications`、`apps.operations`、`apps.exchange`、`apps.analytics`、`apps.agents` |

默认关闭的匿名题库只读 API 使用独立 `/api/v1/question-banks` 路由和受限 CORS/限流策略；内部 HTMX 端点不作为公共 API。模型凭据由运行环境提供，不写入仓库或日志。

## 架构与技术栈

- **后端：** Python `>=3.12,<3.13`、Django `>=5.2,<5.3`、Gunicorn、Celery。
- **数据与任务：** PostgreSQL 保存业务事实；Redis 用于短时状态、缓存、限流及 Celery broker；跨领域副作用由 Outbox 和幂等消费者驱动。
- **前端：** Django Templates、HTMX `2.0.10`、Alpine.js `3.15.12`、Tailwind CSS `4.3.3`、TipTap `3.28.0`。
- **媒体：** 受控文件系统存储媒体；数据库保存引用和权限事实。
- **生产入口：** 宿主 Nginx 是公网入口，Caddy 位于其下游；Web、Worker、Beat 使用版本化应用镜像。
- **本地工具：** `uv`、pytest、Ruff、Node.js `22`、npm `10`、Playwright、Docker Compose、Mailpit。

`apps/` 下有 17 个本地 Django 应用。页面层调用领域 query/service；PostgreSQL 是持久事实，缓存和锁不作最终裁决；文件、通知和任务等跨资源副作用采用明确的生命周期、幂等和补偿边界。架构目录见[架构总览](docs/architecture/README.md)。

## 有日期的数据快照

### 生产使用规模

截至 **2026-10-09 03:20 UTC** 的生产只读快照：

| 指标 | 读回值 |
| --- | ---: |
| 有登录、文章、答题或文档行为的 ACTIVE 账户 | 9 |
| 文章 | 159 |
| 文章修订 | 301 |
| APPROVED 知识文档 | 4 |
| PUBLISHED 题库 | 4 |
| 当前公开题库版本题目 | 999 |
| TaskRun 累计记录 | 1,737,523 |
| TaskRun 成功率 / 重试率 | 99.9930% / 0.1112% |
| TaskRun 端到端耗时 P50 / P95 | 42 ms / 254 ms |

TaskRun 耗时是 `started_at` 到 `completed_at` 的端到端时间，包含排队等待、重试等待和租约恢复等情况，不能直接解释为任务处理器的纯执行耗时。上述数量和比例是该时点的快照，不应作为当前实时值或长期稳定性承诺。来源：[2026-10-09 迭代公告中的生产快照](docs/releases/2026-10-09-next-iteration/announcement.md)。

### 招聘来源与最近发布

截至 **2026-10-11** 的生产来源复查，共有 129 个启用来源，最终聚合为 `123 HEALTHY`、`2 DEGRADED`、`4 STALE`。本轮重点复查的 35 个来源中，30 个恢复 `HEALTHY`，1 个因结果截断为 `DEGRADED`，4 个因真实响应错误或超时继续为 `STALE`。来源状态由现有检查服务按实际结果写入，没有直接 SQL 清零；未触发每日全量采集或 Provider/AGENT 调用。来源详情见[执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md)。

## 工程与验收数据

- 实施计划包含 **13 个阶段、102 条唯一任务**；当前任务清单记录 P0-P12 全部完成。
- 需求追踪覆盖 **322 项需求**；页面矩阵覆盖 **42 个路由**及访客、用户、作者、管理员的适用状态。
- P12 最终回归记录为 **405 passed**；这是阶段验收结果，不是本 README 更新时重新运行的测试。
- 2026-10-11 发布关联的聚焦回归记录：答题与记录 **15 passed**、招聘适配器和 Worker **35 passed**、浏览器运行器契约 **19 passed**。发布期间另通过部署检查、migration drift 检查、静态收集及生产健康读回；详情见[验证记录](.agent-handoff/validation.md)和[发布执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md)。

这些验收数字证明的是有记录的测试与需求覆盖，不代表本次重新跑过完整测试，也不代表 P0 生产负载金丝雀已经通过。

## 本地开发与检查

前置工具：Python `3.12`、`uv`、Node.js `22`、npm `10`。仓库提供无秘密占位配置 `.env.example`；不要将真实凭据、数据库、媒体或日志放入版本控制。

安装依赖并执行基础检查：

```bash
uv sync --locked
npm ci
uv run python manage.py check
npm run build
```

常用验证命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
npm run test:frontend
npx playwright test
```

完整 pytest 需要隔离的 loopback PostgreSQL、Redis 和 Mailpit；Playwright 登录身份、服务启动和安全边界见[测试环境与固定命令](docs/operations/testing.md)。开发和测试只使用 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit，不连接生产或共享数据库，也不调用真实 Provider。

## 重要文档

- [实施总清单与验收证据](docs/planning/implementation-todolist.md)
- [阶段执行契约](docs/planning/implementation-readiness.md)
- [架构总览与模块边界](docs/architecture/README.md)
- [需求真值与需求追踪](docs/planning/requirements-interview.md)、[页面状态矩阵](docs/prototype/page-state-matrix.md)
- [测试环境与固定命令](docs/operations/testing.md)、[运维入口](docs/operations/README.md)
- [2026-10-11 正式更新公告](docs/releases/2026-10-11-production-increment/announcement.md)及[执行记录](docs/releases/2026-10-11-production-increment/deployment-record.md)
- [贡献指南](CONTRIBUTING.md)
