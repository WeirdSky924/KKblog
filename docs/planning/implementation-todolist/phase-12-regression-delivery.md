# P12 跨模块回归与部署准备（6）

退出门禁：数据、权限、浏览器、无障碍、任务、缓存、文件、Compose 和部署沙箱证据全部新鲜。

### QA-001 执行 schema、migration、约束与并发总回归
- 元数据：状态 `完成`；阶段 P12；owner `tests-integration`；优先级 P0。
- 目标/行为：从空库完整migrate并验证所有约束/索引/外键/删除策略；覆盖邀请码、昵称、修订、标签、评论、导出等并发裁决和expand/migrate/contract兼容。
- 来源：`data/04-indexes-constraints.md` 全文；`delivery/02-module-verification-matrix.md` §数据并发；`delivery/03-code-review-checklist.md` §数据迁移。
- 依赖：前置 `ACC-001`、`MED-001`、`CNT-001`、`CNT-010`、`CNT-011`、`CMT-001`、`OBS-001`、`OBS-004`、`OBS-005`、`OBS-006`、`OBS-007`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-004`、`ADM-006`；后续 `QA-002`、`QA-004`、`QA-005`、`QA-006`。
- 文件：`tests/integration/migrations/`、constraint/concurrency suites、migration notes。
- 边界：只用隔离PostgreSQL；不对生产/共享库迁移；SQLite结果不作证；每个迁移记录锁/兼容/备份/回滚限制。
- 影响：数据：全schema；权限/审计/缓存/异步/媒体/通知仅验证关联约束。
- 测试/验收：RED至少包含双事务；`uv run pytest tests/integration/migrations tests/integration/concurrency -q`、`manage.py makemigrations --check`、迁移读回SQL。
- 风险/停止：迁移不向前兼容旧应用、约束只在表单或测试触碰生产连接即停止。
- 证据：在独立 `kaj-p12-postgres` PostgreSQL 16 容器和 loopback `kaj_test_p12` 数据库中执行。聚焦 RED 首轮退出 1，`4 failed, 7 passed`：迁移兼容说明确实缺失，另三项准确识别为新探针的迁移总数、表达式唯一索引分类和标签作者 fixture 假设错误，未据此修改产品。补齐 `docs/operations/migrations.md` 对 43 条 migration 的逐条锁/兼容/备份/回滚记录并修正探针后，目标套件退出 0，`11 passed in 22.84s`；其中每次从新建空 PostgreSQL 数据库完整 migrate 后读回全部 leaf、`pg_trgm` 与核心表，并在 finally 终止定向连接和删除临时库。六组真实双事务分别验证邀请码行锁、昵称 casefold 唯一、修订序号唯一、标签规范值、评论条件公开和 `RUNNING/CANCEL_REQUESTED` 导出部分唯一的单胜者/幂等终态。账户、内容、评论、媒体、通知、TaskRun 与新套件相关回归退出 0，`83 passed in 80.80s`；新测试 Ruff lint/format 均退出 0。`manage.py makemigrations --check --dry-run`、`manage.py check` 与 `git diff --check` 均退出 0；Django 仅报告未构建 `static/dist` 的已知 warning。隔离主库 SQL 读回 `43` 条 migration、`315` 个约束、`303` 个索引，确认同文章修订延迟外键、评论树延迟 trigger 和 TaskRun 幂等唯一；无残留 `kaj_test_p12_empty_*` 数据库。未执行生产/共享数据库 migration、生产备份、部署、服务重启、Git add/commit/push。
- 授权：隔离测试 `否`；生产 migration `是`。

### QA-002 执行四身份完整授权矩阵与存在性隐私回归
- 元数据：状态 `进行中`；阶段 P12；owner `tests-security`；优先级 P0。
- 目标/行为：访客、普通用户、对象作者、其他作者、唯一管理员对文章/评论/举报/账户/通知/设置/交换每个GET/POST/HTMX直接请求均符合矩阵；IP封禁覆盖有效会话。
- 来源：`contracts/02-authorization-matrix.md` 全文；ADR-005；`delivery/02-module-verification-matrix.md` §高风险权限。
- 依赖：前置 `ACC-010`、`ACC-011`、`CNT-005`、`CNT-008`、`CNT-009`、`MED-004`、`DSC-004`、`DSC-005`、`DSC-006`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-003`、`ADM-002`、`ADM-003`、`ADM-004`、`EXC-007`、`QA-001`；后续 `QA-003`、`QA-006`。
- 文件：parameterized policy/service tests、direct HTTP/browser security specs、fixtures。
- 边界：按钮隐藏不算证据；私人/草稿/软删统一404；管理员例外不得扩大；举报人/完整IP/收藏/会话严格隔离。
- 影响：数据：权限读回；权限核心；审计：admin写；缓存：命中后重判；异步：事件接收者；媒体：直接URL；通知：去重/隐私。
- 测试/验收：`uv run pytest tests/integration/authorization -q`；Playwright直接URL/伪造POST；核对HTTP差异、DB无副作用、通知/审计。
- 风险/停止：任一越权、对象存在性侧信道或不同入口策略漂移即阻断全部上线。
- 授权：`否`。

### QA-003 执行桌面/平板/手机全用户流、状态与无障碍验收
- 元数据：状态 `待处理`；阶段 P12；owner `tests-e2e`；优先级 P0。
- 目标/行为：按访客/用户/作者/管理员覆盖页面矩阵 42 个路由及适用身份，执行注册登录、阅读发现、评论审核、编辑发布、设置、管理和交换；1440/390 全页，密集管理页 768；三主题及 S0-S7。
- 来源：`project-plan.md` §3原型验收；`03-frontend-design-system.md` §视觉验收；`prototype/page-state-matrix.md` 全文；`delivery/02-module-verification-matrix.md` §页面视觉/手工验收；21张原型图。
- 依赖：前置 `ACC-002`、`ACC-003`、`ACC-004`、`ACC-005`、`ACC-006`、`ACC-007`、`ACC-008`、`ACC-009`、`ACC-010`、`ACC-011`、`MED-002`、`MED-003`、`MED-004`、`MED-005`、`MED-007`、`CNT-002`、`CNT-003`、`CNT-004`、`CNT-005`、`CNT-006`、`CNT-007`、`CNT-008`、`CNT-009`、`CNT-010`、`CNT-011`、`DSC-001`、`DSC-002`、`DSC-003`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`DSC-008`、`CMT-002`、`CMT-003`、`CMT-004`、`CMT-005`、`CMT-006`、`CMT-007`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-002`、`OBS-003`、`OBS-005`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-002`、`EXC-003`、`EXC-004`、`EXC-005`、`EXC-006`、`EXC-007`、`AUT-001`、`AUT-002`、`AUT-003`、`AUT-004`、`AUT-005`、`AUT-006`、`ADM-001`、`ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-002`；后续 `QA-005`、`QA-006`。
- 文件：`tests/e2e/`、视觉快照/证据索引（不放敏感数据）、a11y checks。
- 边界：截图只证布局；必须真实点击/请求/DB读回；不以原型假数据为验收；不创建与设计token冲突的第二视觉系统。
- 影响：数据：关键写读回；权限：四身份；审计/缓存/异步/媒体/通知：各流观察真实结果。
- 测试/验收：`npx playwright test` desktop/mobile/tablet；检查键盘、焦点锁/Escape/返回、WCAG AA、44px触控、reduced-motion、缩放、无横溢/遮挡。
- 风险/停止：文本/控件重叠、移动端关键动作不可达、错误态丢输入或页面成功与后台事实不一致即阻断。
- 授权：`否`；仅隔离测试数据。

### QA-004 执行 Outbox、Celery、缓存、文件 Saga 与故障回归
- 元数据：状态 `待处理`；阶段 P12；owner `tests-operational`；优先级 P0。
- 目标/行为：对每项任务验证首成/重复/双worker/2败1成/3败/提交前后崩溃/对象中变；验证Redis清空、缓存全失效、媒体/文章/导出清理与告警去重。
- 来源：`contracts/05-background-tasks.md` §任务目录/任务测试；`04-operations-testing.md`；`delivery/02-module-verification-matrix.md` §数据并发。
- 依赖：前置 `FND-005`、`MED-006`、`CNT-004`、`CNT-008`、`CMT-004`、`DSC-008`、`OBS-006`、`OBS-007`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-003`、`EXC-005`、`QA-001`；后续 `QA-005`、`QA-006`。
- 文件：worker integration tests、fault injection fixtures、temporary media/archive/cache assertions。
- 边界：不以Celery eager替代真实worker；不发送真实外部邮件；文件/DB测试在隔离命名空间；不手工重试失败TaskRun伪装成功。
- 影响：数据：TaskRun/业务终态；权限：任务重判；审计关联；缓存：Redis；异步核心；媒体：Saga；通知：最终失败一次。
- 测试/验收：启动隔离worker执行任务矩阵，核对DB/文件/Redis/通知/RuntimeError；Ruff/pytest相关回归。
- 风险/停止：重复副作用、孤儿文件可访问、最终失败无可追踪证据或缓存泄露私密内容即阻断。
- 授权：隔离容器 `是`（当前回合）；生产任务/清理 `是`。

### QA-005 执行 Compose、健康、备份与部署/回滚沙箱验收
- 元数据：状态 `待处理`；阶段 P12；owner `operations`；优先级 P0。
- 目标/行为：在隔离环境验证构建、依赖未就绪、自动重启、live/ready、内部端口、一次数据库+媒体备份、迁移检测、维护页、迁移失败中止、健康失败应用回滚。
- 来源：访谈 Q179-Q186、Q265-Q274、Q288；`flows/04-import-export-sequences.md` §部署门禁；`delivery/02-module-verification-matrix.md` §Operational。
- 依赖：前置 `RUN-001`、`RUN-002`、`RUN-003`、`RUN-004`、`RUN-005`、`RUN-006`、`OBS-007`、`EXC-006`、`EXC-007`、`QA-001`、`QA-003`、`QA-004`、`DEC-002`、`DEC-004`；后续 `QA-006`。
- 文件：Compose/health/deploy sandbox specs、backup evidence、port/secret checks、runbook。
- 边界：沙箱不等于生产部署；首版全部功能完成前不得增量部署；不自动回滚数据库；备份只声明命令成功；无生产域名时只验证 production 关闭失败与 localhost development/test HTTP；不重启现有服务。
- 影响：数据：隔离migration/backup；权限：端口/管理；审计：部署记录；缓存/异步/媒体/通知：全栈运维读回。
- 测试/验收：`docker compose config`、隔离up/health/故障注入/backup/deploy dry-run；备份额外核对 `Asia/Shanghai` 周一 03:00（`0 3 * * 1`）、仅 `local` 和一个周实例；记录命令、退出码、健康HTTP与回滚版本。
- 风险/停止：端口额外暴露、秘密进镜像/日志、旧应用不能读新schema或回滚脚本有破坏操作即阻断。
- 授权：运行容器/沙箱服务 `是`；生产部署/迁移/重启另行 `是`。

### QA-006 完成需求追踪、架构评审、交付记录与授权门禁
- 元数据：状态 `待处理`；阶段 P12；owner `project-governance`；优先级 P0。
- 目标/行为：逐条核对 Q001-Q322、47 份原始文档、3 份施工派生文档和 102 个任务证据；检查 owner/依赖/重复/遗漏；更新 README/运维/迁移/验证记录，形成可部署但未部署的最终交付说明。
- 来源：`reference/03-requirements-traceability.md` 全文；`planning/requirements-todo-traceability.md` 全文；`planning/implementation-readiness.md` 全文；`prototype/page-state-matrix.md` 全文；`05-architecture-study-guide.md` §文档维护；`delivery/03-code-review-checklist.md` 全文；本清单。
- 依赖：前置 `DEC-001`、`DEC-002`、`DEC-003`、`DEC-004`、`DEC-005`、`FND-001`、`FND-002`、`FND-003`、`FND-004`、`FND-005`、`FND-006`、`RUN-001`、`RUN-002`、`RUN-003`、`RUN-004`、`RUN-005`、`RUN-006`、`OBS-006`、`OBS-007`、`ACC-001`、`OBS-004`、`OBS-001`、`ACC-002`、`ACC-003`、`ACC-004`、`ACC-005`、`ACC-006`、`ACC-008`、`ACC-009`、`ACC-010`、`ACC-011`、`MED-001`、`MED-002`、`MED-003`、`MED-004`、`MED-005`、`MED-006`、`MED-007`、`ACC-007`、`CNT-001`、`CNT-002`、`CNT-010`、`CNT-011`、`CNT-003`、`CNT-004`、`CNT-005`、`CNT-006`、`CNT-007`、`CNT-008`、`CNT-009`、`DSC-001`、`DSC-002`、`DSC-003`、`DSC-004`、`DSC-005`、`DSC-006`、`DSC-007`、`DSC-008`、`CMT-001`、`CMT-002`、`CMT-003`、`CMT-004`、`CMT-005`、`CMT-006`、`CMT-007`、`CMT-008`、`CMT-009`、`CMT-010`、`CMT-011`、`OBS-002`、`OBS-003`、`OBS-005`、`OBS-008`、`OBS-009`、`OBS-010`、`EXC-001`、`EXC-002`、`EXC-003`、`EXC-004`、`EXC-005`、`EXC-006`、`EXC-007`、`AUT-001`、`AUT-002`、`AUT-003`、`AUT-004`、`AUT-005`、`AUT-006`、`ADM-001`、`ADM-002`、`ADM-003`、`ADM-004`、`ADM-005`、`ADM-006`、`ADM-007`、`ADM-008`、`QA-001`、`QA-002`、`QA-003`、`QA-004`、`QA-005`；后续 无其他 Todo。
- 文件：本Todo索引/阶段状态、README、operations runbook、migration/verification records、review findings。
- 边界：文档不能把未运行项写成完成；不自动git add/commit/push/部署；不修改需求真值来迁就实现；发现漂移先新决策/ADR。
- 影响：数据/权限/审计/缓存/异步/媒体/通知：仅核对全量证据与残余风险。
- 测试/验收：运行 ID/依赖/链接/322 行 coverage/页面矩阵/Goal 脚本、Ruff/pytest/Playwright/Operational 最终命令；代码评审先列发现，逐项关闭或标阻塞。
- 风险/停止：任一P0失败、需求无落点、owner重复、测试过期/缺失或生产值未确认即不得宣布完成/可部署。
- 授权：文档/审查 `否`；git add/commit/push、生产备份/迁移/部署/重启均 `是`。

[返回总索引](../implementation-todolist.md)
