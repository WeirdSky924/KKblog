# Kaj的小房间完整实施 Todo List

状态：唯一实施清单索引；P0-P12 全部完成。

最后重构：2026-07-29（Asia/Shanghai）。

目标仓库：`/home/code/personal-blog/`。
需求真值：`docs/planning/requirements-interview.md`；冲突按最新明确决策及 `docs/architecture/reference/01-requirements-resolution.md` 处理。

## 1. 当前事实

- 当前根目录是有效 Django/Git 仓库，包含根 `AGENTS.md`、`README.md`、贡献/运维文档、源码、锁文件和测试配置；远端默认分支为 `main`。
- 远端默认分支 `main` 当前为 `7e74a3f`，已包含 P0-P11 全部 96 项；当前安全任务分支 `codex/p12-regression-delivery` 已在工作区完成 P12 全部 6 项。完成状态不等于 Git 交付、部署、生产 migration 或服务操作授权。
- 状态只使用：`待确认`、`待处理`、`进行中`、`阻塞`、`完成`。只有验收证据写回后才能标记完成。
- 优先级：`P0` 阻断后续或安全关键；`P1` 首版必需；`P2` 交付收口。
- 每条任务的“授权”描述执行时是否需要用户在当前回合另行授权；历史授权和完成状态不能替代新的生产、Git 或外部副作用授权。

## 2. 已读取文档与层级

### 2.1 实际层级

```text
docs/
  planning/                 # 需求真值、逐条追踪、就绪契约、Todo 与 Goal
  prototype/                # 视觉原型、42 路由状态矩阵、21 张参考截图
  architecture/
    README + 01..05         # 总纲、目录、数据安全、前端、运维、学习路线
    modules/                # A-J 十个稳定能力摘要
    data/                   # ER、字段、约束/索引、存储生命周期
    flows/                  # 账户、文章、评论、交换/部署状态机
    contracts/              # 服务、权限、前端、事件/错误、后台任务
    adr/                    # ADR-001..006 与索引
    delivery/               # 实施、验证、评审门禁
    reference/              # 消歧、术语、322 项需求追踪
```

### 2.2 全量文本文件（47/47 已全文读取）

- `docs/planning/requirements-interview.md`；`docs/planning/project-plan.md`。
- `docs/prototype/README.md`；`docs/prototype/index.html`。
- `docs/architecture/README.md`；`01-system-directory.md`；`02-data-security-lifecycle.md`；`03-frontend-design-system.md`；`04-operations-testing.md`；`05-architecture-study-guide.md`。
- `docs/architecture/modules/01-platform-foundation.md`；`02-accounts-access.md`；`03-content-versioning.md`；`04-media-rendering.md`；`05-discovery-reading.md`；`06-interactions-moderation.md`；`07-authoring-workbench.md`；`08-administration-navigation.md`；`09-notifications-observability.md`；`10-exchange-analytics-maintenance.md`。
- `docs/architecture/data/01-er-model.md`；`02-identity-content-fields.md`；`03-interaction-operations-fields.md`；`04-indexes-constraints.md`；`05-storage-lifecycle.md`。
- `docs/architecture/flows/01-account-access-state-machine.md`；`02-article-state-machine.md`；`03-comment-moderation-state-machine.md`；`04-import-export-sequences.md`。
- `docs/architecture/contracts/01-application-services.md`；`02-authorization-matrix.md`；`03-frontend-contract-map.md`；`04-events-errors.md`；`05-background-tasks.md`。
- `docs/architecture/adr/README.md`；`ADR-001-domain-modular-monolith.md`；`ADR-002-postgresql-immutable-revisions.md`；`ADR-003-server-rendered-htmx.md`；`ADR-004-redis-outbox.md`；`ADR-005-admin-content-exception.md`；`ADR-006-filesystem-media.md`。
- `docs/architecture/delivery/01-implementation-roadmap.md`；`02-module-verification-matrix.md`；`03-code-review-checklist.md`。
- `docs/architecture/reference/01-requirements-resolution.md`；`02-glossary.md`；`03-requirements-traceability.md`。

### 2.3 原型图片（21/21 已检查）

- 桌面（14）：account、article、auth、authorops、editor、exchange、home、interactive-report、moderation、notifications、operations、report-modal、settings、users。
- 移动（7）：account、article、editor、home、operations、personalsettings、users。

### 2.4 施工派生文档

- `docs/planning/implementation-readiness.md`：阶段 DoR/DoD、真值优先级、跨域拆分和证据模板。
- `docs/planning/requirements-todo-traceability.md`：Q001-Q322 逐条映射到架构、Todo、验收场景和页面/门禁。
- `docs/prototype/page-state-matrix.md`：42 个路由的身份、状态、视口和原型落点。
- `docs/planning/implementation-goal-prompts.md` 与 13 份阶段提示词：每阶段一个一次性 Goal。

## 3. 唯一清单分档

| 顺序 | 阶段文件 | 范围 | 数量 |
| ---: | --- | --- | ---: |
| 0 | [`phase-00-decisions.md`](implementation-todolist/phase-00-decisions.md) | 决策与范围锁定 | 5 |
| 1 | [`phase-01-foundation.md`](implementation-todolist/phase-01-foundation.md) | 项目与质量骨架 | 6 |
| 2 | [`phase-02-runtime.md`](implementation-todolist/phase-02-runtime.md) | 运行时、TaskRun 与 CapacityPolicy | 8 |
| 3 | [`phase-03-accounts.md`](implementation-todolist/phase-03-accounts.md) | 账号、安全、通知与审计基础 | 12 |
| 4 | [`phase-04-media.md`](implementation-todolist/phase-04-media.md) | 媒体、安全渲染与个人资料 | 8 |
| 5 | [`phase-05-content.md`](implementation-todolist/phase-05-content.md) | 文章、修订、分类与发布任务 | 11 |
| 6 | [`phase-06-discovery.md`](implementation-todolist/phase-06-discovery.md) | 阅读与发现 | 8 |
| 7 | [`phase-07-comments-moderation.md`](implementation-todolist/phase-07-comments-moderation.md) | 评论、留言、举报、申诉 | 11 |
| 8 | [`phase-08-observability.md`](implementation-todolist/phase-08-observability.md) | 通知与可观测性集成 | 6 |
| 9 | [`phase-09-exchange-operations.md`](implementation-todolist/phase-09-exchange-operations.md) | 导入导出、备份、Umami | 7 |
| 10 | [`phase-10-authoring.md`](implementation-todolist/phase-10-authoring.md) | 作者工作台 | 6 |
| 11 | [`phase-11-administration.md`](implementation-todolist/phase-11-administration.md) | 管理后台、导航与设置 | 8 |
| 12 | [`phase-12-regression-delivery.md`](implementation-todolist/phase-12-regression-delivery.md) | 跨模块回归与部署准备 | 6 |

总计：13 个阶段、102 条唯一任务。每个 ID 只在一个阶段文件中定义；新增 `OBS-008..010` 分别承接领域通知、最终失败通知和周期容量告警集成。

## 4. 执行与拆分规则

1. 启动阶段前必须满足 `implementation-readiness.md` 的 Definition of Ready；P0 未确认的决定不得被建议值替代。
2. 阶段按 P0→P12 执行；任何前置 ID 指向未来阶段都视为计划缺陷并停止。每次只把一条任务设为 `进行中`。
3. 固定节奏：聚焦 RED → schema/约束 → policy/service/query → 页面/HTMX → outbox/task/通知/审计 → GREEN/回归 → 数据读回 → Playwright/运维证据。
4. UI 按 `prototype/page-state-matrix.md` 实现；至少检查 1440px 与 390px，管理密集页追加 768px，并覆盖 S0-S7 状态。
5. migration、生产数据、容器/服务、外部邮件、Git 与部署只在任务卡授权条件和用户当前回合授权同时满足时执行。
6. 阶段完成后更新本索引“进度与证据”；需求变化先更新访谈/消歧，再更新逐条追踪、架构、Todo、页面矩阵和 Goal 基线。

## 5. 任务卡强制字段

每条任务必须保留：唯一 ID/状态/阶段/owner/优先级；用户可观察目标；章节级来源；前置/后续；预计文件；边界/非目标；数据、权限、审计、缓存、异步、媒体、通知影响；测试先行、命令/用户流、验收；风险/回滚/停止；另行授权。

## 6. 全局退出门禁

- 102 个 ID 唯一，所有依赖 ID 存在，前置图无环且无反向阶段边；每项稳定事实只有一个 owner。
- Q001-Q322 均在 `requirements-todo-traceability.md` 有最终决定、架构落点、Todo 和 `REQ-Qnnn` 验收场景。
- 权限、版本、删除、媒体、任务、缓存、导入导出必须有真实 PostgreSQL/临时文件读回，不能只用 mock。
- 访客、用户、作者、管理员在 42 个路由的适用身份和 S0-S7 状态完成桌面/手机流；密集管理页追加平板。
- 未经明确授权不得执行 Git add/commit/push、生产迁移、部署、服务重启或不可逆数据操作。

## 7. 进度与证据

- 当前：102 条唯一任务全部完成，P0-P12 无 `进行中`、`待处理` 或 `阻塞` 项。P12 的 schema/并发、四身份授权、全应用浏览器流、真实 worker/缓存/文件 Saga、Compose/备份/部署沙箱及最终治理审计均已有新鲜证据；沙箱运行时和本任务临时产物已定向清理。这些完成事实不表示已有生产数据、生产 migration、生产备份或已部署服务。
- P12 `QA-006` 已完成 322 项需求、47 份原始文档、3 份施工派生文档、102 个任务、owner/依赖/页面/链接/Goal 的全量审计，并关闭 findings-first 评审的 4 个 P1；最终全量 `pytest` 为 `405 passed`、Playwright 授权/应用/基础四身份为 `1/5/8 passed`，Ruff、Django、migration drift、前端构建、Compose/Caddy/部署合同与差异检查均退出 0。
- 决定性证据已按 `implementation-readiness.md` 口径写回各任务卡；当前源码候选满足部署前门禁但尚未部署。生产域名、管理员邮箱、Resend 身份/密钥仍未配置，完整恢复演练、生产命令适配器及全部生产动作均未执行；本轮仅创建本地 Git 提交，明确不推送、不集成远端默认分支。

## 8. 已确认 P0 决策摘要

| ID | 已确认口径 | 影响 | 后续门禁 |
| --- | --- | --- | --- |
| `DEC-001` | 先核验 GitHub 远端历史/实际默认分支；有历史从实际默认分支建立 `codex/<task>`，空仓以 `main` 初始化；不直接在默认分支开发 | 首次写入、远端、后续交付 | `FND-001` 前重新读回；提交/推送仍需当前请求明确授权 |
| `DEC-002` | development/test 仅 `localhost`、`admin@kaj.test`、`no-reply@kaj.test` 与 Mailpit；production 缺真实域名、管理员邮箱、Resend 发件身份或密钥时关闭失败 | 管理员初始化、HTTPS、验证码、运维邮件、Umami | 测试值不得进入生产；本决策不表示生产实值或 Resend 已可用 |
| `DEC-003` | 昵称以 Unicode `casefold` 规范值大小写不敏感唯一，展示保留原始大小写 | 账户唯一约束与并发裁决 | P3/P4 由数据库唯一约束和共享规范化函数证明 |
| `DEC-004` | `Asia/Shanghai` 每周一 03:00（`0 3 * * 1`）同轮备份数据库与媒体；首版仅 `local` | Beat、设置页、运维窗口 | 不展示/保存外部假目标；不表示当前已有备份服务或产物 |
| `DEC-005` | 仓库自有 `1600x900` 默认封面和 `800x450` 失效图；静态图 `8192`/`25 MP`，动图 `200` 帧/`100 MP`；导入 `64/256 MiB`、`1000` 项、`8` 层、`100:1`；正文默认 `2 MiB`、可配 `64 KiB..2 MiB` | 视觉资产、上传/导入安全、设置校验 | 不表示素材已制作；2 MiB 单图硬上限不放宽，其他安全上限只能收紧，放宽需新决策 |

## 9. 结构与依赖审计

- 任务：已验证 13 个阶段文件、102 个任务块、102 个唯一 ID、0 个重复；阶段计数与索引一致。
- 字段：`元数据/目标/来源/依赖/文件/边界/影响/测试/风险/授权` 已分别出现 102 次；0 张缺字段任务卡。
- 依赖：已验证 555 条前置边和 555 条反向生成的后续边；0 个缺失 ID、0 个自环/环、0 条反向阶段边、0 组前后不互认。前置 ID 是唯一依赖真值，生成器据此计算完整后续列表。
- Owner：102 张卡各且仅声明一个 owner，共 22 个执行 owner；领域事实仍分别归 accounts/content/media/comments/moderation/notifications/navigation/operations/exchange/analytics，authoring/administration/discovery 仅做架构允许的编排或读取投影。
- 追踪/页面：322 个需求段、322 行逐条追踪和 322 个 `REQ-Qnnn` 均唯一且一一覆盖；架构前端契约与页面矩阵各有 42 个唯一 URL name，集合差异为 0。
- Goal/文档：13 份提示词各只有一个主 Goal，复选框并集为 102 个唯一 Todo，0 缺失/额外；47 份原始文本文件名均在 Todo 包覆盖矩阵或任务来源中出现；本地相对链接 63 个，缺失 0。

## 10. 文档覆盖矩阵

| 来源文档 | 主要落点 |
| --- | --- |
| `planning/requirements-interview.md` | `DEC-001..005`、`FND-001..006`、`RUN-001..006`、全部领域任务、`QA-001..006` |
| `planning/project-plan.md` | `FND-001..006`、各阶段退出门禁、`QA-003..006` |
| `planning/implementation-readiness.md` | 全 13 阶段 DoR/DoD、跨域基础拆分、证据和停止条件 |
| `planning/requirements-todo-traceability.md` | Q001-Q322 → 102 Todo → `REQ-Qnnn` |
| `prototype/README.md` | `RUN-005`、`DSC-001..007`、`AUT-001..006`、`ADM-001..008`、`QA-003` |
| `prototype/index.html` | `RUN-005`、`DSC-001..007`、`CMT-002..011`、`AUT-001..006`、`ADM-001..008`、`QA-003` |
| `prototype/page-state-matrix.md` | 42 路由、S0-S7、四身份、390/768/1440、全部页面任务与 `QA-003` |
| `architecture/README.md` | `FND-002..006`、`RUN-001..006`、owner 分档、`QA-006` |
| `architecture/01-system-directory.md` | `FND-002..006`、`RUN-001`、各 app 文件/owner、`QA-006` |
| `architecture/02-data-security-lifecycle.md` | `ACC-001..011`、`CNT-001..011`、`MED-001..007`、`CMT-001..011`、`QA-001..002` |
| `architecture/03-frontend-design-system.md` | `RUN-005`、`DSC-001..007`、`OBS-002..003`、`AUT-001..006`、`ADM-001..008`、`QA-003` |
| `architecture/04-operations-testing.md` | `RUN-001..006`、`OBS-004..007`、`EXC-005..007`、`QA-004..005` |
| `architecture/05-architecture-study-guide.md` | 全任务卡固定字段/执行节奏、`QA-006` |
| `architecture/modules/01-platform-foundation.md` | `FND-002..006`、`RUN-001..005`、`OBS-005` |
| `architecture/modules/02-accounts-access.md` | `ACC-001..011`、`ADM-002..003`、`QA-002` |
| `architecture/modules/03-content-versioning.md` | `CNT-001..011`、`AUT-001..005`、`QA-001..002` |
| `architecture/modules/04-media-rendering.md` | `MED-001..007`、`DEC-005`、`QA-004` |
| `architecture/modules/05-discovery-reading.md` | `DSC-001..008`、`QA-002..003` |
| `architecture/modules/06-interactions-moderation.md` | `CMT-001..011`、`ADM-004`、`QA-002..003` |
| `architecture/modules/07-authoring-workbench.md` | `AUT-001..006`、`CNT-006..007`、`QA-003` |
| `architecture/modules/08-administration-navigation.md` | `ADM-001..008`、`DSC-001`、`QA-002..003` |
| `architecture/modules/09-notifications-observability.md` | `OBS-001..010`、`ADM-008`、`QA-004` |
| `architecture/modules/10-exchange-analytics-maintenance.md` | `EXC-001..007`、`RUN-006`、`ADM-008`、`QA-004..005` |
| `architecture/data/01-er-model.md` | `ACC-001`、`CNT-001`、`MED-001`、`CMT-001/008/011`、`OBS-001/004/006`、`EXC-001/004`、`QA-001` |
| `architecture/data/02-identity-content-fields.md` | `ACC-001/002/005/007/008`、`CNT-001/002/007/010/011`、`QA-001` |
| `architecture/data/03-interaction-operations-fields.md` | `MED-001..003`、`CMT-001/008..011`、`OBS-001/004..006`、`EXC-001/004/006`、`ADM-006/007` |
| `architecture/data/04-indexes-constraints.md` | `ACC-001/002/007`、`CNT-001/006/010/011`、`CMT-001/003/005/008`、`EXC-004`、`ADM-006`、`QA-001` |
| `architecture/data/05-storage-lifecycle.md` | `RUN-001/003`、`ACC-003/009`、`MED-001/002/004/006`、`DSC-008`、`OBS-007`、`EXC-005/006`、`QA-004` |
| `architecture/flows/01-account-access-state-machine.md` | `ACC-001..011`、`ADM-002..003`、`QA-002` |
| `architecture/flows/02-article-state-machine.md` | `CNT-001..011`、`AUT-003..005`、`CMT-011`、`QA-001..002` |
| `architecture/flows/03-comment-moderation-state-machine.md` | `CMT-001..011`、`OBS-001`、`ADM-004`、`QA-002..004` |
| `architecture/flows/04-import-export-sequences.md` | `RUN-006`、`EXC-001..006`、`AUT-006`、`QA-004..005` |
| `architecture/contracts/01-application-services.md` | `FND-005`、`ACC-002..011`、`CNT-002..011`、`MED-002..006`、`CMT-002..011`、`OBS-001..010`、`EXC-001..005` |
| `architecture/contracts/02-authorization-matrix.md` | `ACC-005/010/011`、`CNT-005/008/009`、`MED-003/004`、`CMT-002/003/006/008..011`、`OBS-002/003`、`ADM-001..008`、`QA-002` |
| `architecture/contracts/03-frontend-contract-map.md` | `DSC-001..007`、`OBS-002..003`、`AUT-001..006`、`ADM-001..008`、`QA-003` |
| `architecture/contracts/04-events-errors.md` | `FND-004/005`、所有跨域事件任务、`OBS-001/004/005/008/009`、`QA-004` |
| `architecture/contracts/05-background-tasks.md` | `CNT-004/008`、`MED-006`、`CMT-004`、`OBS-006/007/009/010`、`EXC-003/005/006/007`、`QA-004` |
| `architecture/adr/README.md` | `FND-001/002`、各 ADR 对应任务、`QA-006` |
| `architecture/adr/ADR-001-domain-modular-monolith.md` | `FND-002/006`、全部 owner 分档、`QA-006` |
| `architecture/adr/ADR-002-postgresql-immutable-revisions.md` | `CNT-001..008`、`EXC-003`、`QA-001` |
| `architecture/adr/ADR-003-server-rendered-htmx.md` | `FND-002`、`RUN-005`、所有页面任务、`QA-003` |
| `architecture/adr/ADR-004-redis-outbox.md` | `FND-005`、`ACC-003/009`、`OBS-001/006`、`QA-004` |
| `architecture/adr/ADR-005-admin-content-exception.md` | `CNT-005`、`CMT-011`、`ADM-004`、`QA-002` |
| `architecture/adr/ADR-006-filesystem-media.md` | `MED-001..006`、`EXC-005/006`、`QA-004` |
| `architecture/delivery/01-implementation-roadmap.md` | 领域能力簇关系；精确 13 阶段顺序只以本索引和 `implementation-readiness.md` 为准 |
| `architecture/delivery/02-module-verification-matrix.md` | 每张任务卡测试/验收、`QA-001..005` |
| `architecture/delivery/03-code-review-checklist.md` | 每张任务卡边界/风险、`FND-006`、`QA-006` |
| `architecture/reference/01-requirements-resolution.md` | `DEC-001..005`、`ACC-001/011`、`CNT-005/007/010`、`MED-002/007`、`CMT-009/010`、`QA-006` |
| `architecture/reference/02-glossary.md` | 任务卡术语、owner/幂等/遮罩/Saga/HTMX 约束、`QA-006` |
| `architecture/reference/03-requirements-traceability.md` | 架构行为簇；逐条任务映射见 `planning/requirements-todo-traceability.md`、`QA-006` |

原型 21 张图片只作为视觉参考；42 路由和缺失状态由页面状态矩阵补齐。截图不替代真实点击、权限、异步和数据读回。

## 11. 当前完成口径

- P0-P12 共 102 项全部完成；当前没有进行中、待处理或阻塞的 Todo，阶段编号保留为实施和证据索引顺序。
- 当前源码候选已完成隔离 Compose、数据库、媒体、任务、浏览器和部署沙箱验收，并通过最终结构、代码、测试和运维门禁；沙箱成功不等于生产部署。
- P0-P12 完成不表示存在生产数据库、真实备份/恢复演练、真实 Umami/流量、邮件身份、生产命令适配器、已运行的生产任务或已部署服务，也不授权 Git add/commit/push 或任何生产操作。
