# AGENT 知识题库与答题系统实施 Todo

状态：T01-T21 已完成（2026-08-18）。只有本文件维护施工进度；README 和设计文档不建立第二份状态账。

## 1. 执行规则

- 任一时刻最多一项标记为“进行中”；当前 T00-T21 均已完成。
- 按依赖顺序推进，优先闭合可观察用户行为，不连续交付只有模型/表/页面的空骨架。
- 所有真实模型调用、migration、Labs 数据写入、Git 交付和生产动作分别遵守当前授权边界。
- 业务逻辑切片执行聚焦 RED、最小完整 GREEN、相关回归、隔离 PostgreSQL 读回和必要浏览器用户流。
- 模型测试默认使用确定性假 Provider；真实测试 Provider 只能在用户明确授权、费用上限和脱敏检查完成后使用。
- 稳定 owner 只有 `agents` 与 `learning`；administration、Task、API View 和模板不得复制规则。

### 当前 Goal 持续授权（2026-08-17）

用户已明确授权“后续任务全部授权直到推进完毕 Goal”。本授权持续覆盖 T01-T21 完成所必需的非生产 Labs migration、隔离或 Labs 测试数据写入、任务派发验证、`kaj-labs` 相关服务 warm restart、健康/任务注册/数据读回和清理动作，后续不再为这些同范围动作逐项暂停询问。授权仍受本文件的任务顺序、隔离、最小写入、回退和新鲜验证门禁约束；若用户后续撤销或收紧，以最新指令为准。

本授权不扩大 Goal 本身：没有完成 T01-T21 的必要性时，不执行真实付费 Provider、生产发布、生产数据变更或 Git 提交/推送；若后续 Goal 明确需要其中某项，只执行达到对应完成标准所需的最小范围并完整读回。

## 执行阶段与完成门禁

| 阶段 | Todo | 可观察结果 | 进入下一阶段的硬门禁 |
| --- | --- | --- | --- |
| A 架构与运行底座 | T01-T04 | owner、Endpoint、Provider、token ledger 与管理员配置可用 | 隔离迁移/回退、假 Provider、SSRF/秘密/预算边界通过 |
| B 知识文档 | T05-T08 | 授权用户可上传、审核、查看状态与申诉 | 文件/权限/配额/状态机/通知完整，真实持久化读回 |
| C 题库 | T09-T13 | 生成、修订、公开查询和管理员处置闭环 | 固定 schema、不可变 revision、覆盖统计、权限与缓存失效通过 |
| D 外部 API | T14-T15 | 默认关闭的匿名只读 API 可受控开放 | 契约、分页、限流、CORS、Redis 故障与缓存边界通过 |
| E 答题学习 | T16-T18 | 答题、自动保存、错题本与记录管理闭环 | 判分/快照/跨设备/软计时/删除关系真实读回 |
| F 运维与交付 | T19-T21 | 通知审计、清理恢复、Labs 验收和发布准备完成 | 全部回归、迁移演练、浏览器矩阵、健康读回和增量清单通过 |

每个 Todo 只有同时满足以下条件才可标记“已完成”：

1. 该 Todo 的入口、权限、状态、输出、错误、并发、幂等和清理语义全部落到唯一 owner，不留仅有页面或模型的空骨架。
2. 有意义逻辑先取得聚焦 RED 证据，再完成 GREEN 与相关回归；新增 migration 必须在隔离 PostgreSQL 验证正向、约束和回退方案。
3. 用户可见切片完成 390/768/1440、三主题、键盘/焦点和真实点击/持久化读回；非用户可见切片完成对应 logic/data/operational guard。
4. 运行时错误、日志、事件、通知和审计不包含密钥、Prompt、知识正文、题目答案、原路径或个人数据。
5. 更新本文件状态和相关架构/运维文档；当前 Labs 阶段按项目规则同步本切片源码/产物并读回 service、health 与一条受影响路径。
6. migration 执行、真实模型调用、Git 交付和生产动作分别等待当次明确授权；未获授权时可完成代码与隔离验证，但必须停在对应外部动作前并记录未执行项。

## 2. 裁决与基础边界

### T00｜逐项完成产品裁决

状态：已完成；Q001-Q039 及全部 A-F 子项已确认，最终一致性审计通过。

依赖：无。

结果：依次回答 [需求裁决记录](./requirements-interview.md) 的 Q001-Q039 及全部 A-F 子项；每次答案先持久化，再更新受影响设计。当前不存在 OPEN 或相互冲突的有效裁决。

验证：不存在互相冲突的有效裁决；每项原始需求都映射到设计和 Todo；不清晰字段没有实现者默认值伪装成用户结论。

### T01｜固化 owner、公共端口与威胁边界

状态：已完成（2026-08-16）。

依赖：T00 的第一优先级问题。

结果：在架构索引登记 `apps/agents`、`apps/learning`，补充依赖允许边、授权矩阵、Task、事件、错误码、页面和 API 契约；明确 Prompt injection、SSRF、秘密、费用和公开内容风险。

验证：架构守卫先 RED 后 GREEN；无反向依赖、第二媒体/通知/任务中心或从 View 直读私有表。

证据：聚焦 RED `pytest tests/contracts/test_architecture.py -q` 退出 1，准确缺失 24 个登记标记；补齐 owner、ADR-007、服务/权限/页面、事件/任务、数据/保留、验证/追踪后同命令退出 0（`5 passed`），Ruff 与 `git diff --check` 退出 0。Labs 读回 `WorkingDirectory=/home/code/.codex-worktrees/personal-blog/labs-test-environment`、`active/running`、`/health/live=200`。一次额外 Outbox 回归因未提供隔离 PostgreSQL 而在既有 PostgreSQL 专用 migration 上产生 SQLite 环境错误；本切片未改变数据库运行时代码，未把该无效运行计为回归证据，也未触碰共享数据库。

## 3. AGENT 运行时

### T02｜建立 Endpoint、AGENT 与 Prompt 修订事实

状态：已完成（2026-08-16）。

依赖：T01。

结果：新增 Endpoint、管理员逐 Endpoint 可编辑的显式运行参数、profile、Prompt revision、当前指针和 invocation 配置快照；同时建立全站/Endpoint 每日 token policy、ledger、reservation 与 adjustment 事实。实现 context 131072（4096..2000000）、output 8192（256..131072）、per-run 500000（10000..5000000）、timeout 120s（10..600）、concurrency 1（1..5）、site daily 5,000,000、Endpoint daily 2,000,000 的默认/范围/交叉约束、row version、启停、审计 schema 和迁移，不按模型名或连通性检查自动回写参数。

验证：隔离 PostgreSQL migration/rollback 方案、运行参数与每日预算默认/范围/交叉校验、ledger/reservation/adjustment 唯一约束、配置与 invocation 快照、连通检查不回写、并发 Prompt 保存 409、一个 profile 一个当前 Prompt、历史不可变、秘密字段不存在或不可回显、管理员权限读写。

证据：聚焦 RED 从缺失 `apps.agents.contracts` 开始；最终隔离 PostgreSQL 聚焦 `23 passed`，agents + operations 审计 + 架构守卫回归 `31 passed`。`manage.py check`、`makemigrations agents --check --dry-run`、Ruff、`git diff --check` 均退出 0。`agents.0001_initial` 在 `kaj_test_agents_t02` 完成全量向前、默认 policy `5,000,000/row_version 1` 与 PostgreSQL 约束读回、反向到 zero 后 `agent_%` 表为 0、再向前成功；配置快照、Prompt stale 409/不可变历史、管理员安全 DTO、双层 ledger/reservation/settlement/reset operation 和活跃预留保护均有真实读回。一次演练命令漏设 test settings，曾只在 development SQLite 新建 agents 表；已定向反向 `agents zero` 并读回 `agent_%` 表为 0，未改既有业务表。连接检查本身属于 T03 Provider 能力，T02 已固定“无能力表/无自动回写”的配置边界，T03/T04 再验证检查不改参数。Labs worktree 同源读回 `active/running`、health/home `200`；未执行 Labs/共享 migration、真实 Provider、Git 或生产动作。

### T03｜实现受限 Provider Gateway

状态：已完成（2026-08-16）。

依赖：T02；Q003-Q005、Q038A-Q038B 已确认密钥、Provider/网络、分块预算及管理员显式运行参数来源/范围。

结果：实现 GPT/OpenAI-compatible、DeepSeek/OpenAI-compatible、Claude/Anthropic Messages adapter port，以及 Base URL 规范化、SSRF/重定向/DNS 防护、服务器网络 allowlist、连接/读取/总超时、响应上限、schema 解析、幂等和调用计量；Gateway 在首次外呼前原子预留全站/Endpoint token，成功调用按可信 usage 结算，失败调用以 `0` 结算并通过安全通知说明原因，同时处理租约/崩溃回收。提供确定性假 Provider。

验证：恶意 URL、凭据 URL、内网策略、DNS rebinding、重定向、慢响应、大响应、坏 JSON、schema 不符、密钥脱敏、双层额度不足时零外呼、并发预留、可信/缺失 usage、重复结算、租约崩溃回收、瞬时重试和最终失败。

证据：网络策略、三类 adapter、Gateway、租约恢复和专用环境加载先取得缺失行为 RED，最终 T03 聚焦回归 `45 passed`；T02/T03/环境/架构联合回归曾取得 `72 passed`，最终格式化后 Gateway 文件回归 `13 passed`、架构守卫 `5 passed`。Gateway 逐跳解析并固定 IP/Host/SNI，只允许公网 HTTPS 或精确内网 `host:port` allowlist；唯一外呼实现位于 `providers/http.py`。Invocation 调用前重新校验不可变 Prompt、认证别名、Base URL 和完整运行参数快照，缺失 schema/损坏快照/永久冲突均返回非重试稳定错误且零外呼；配额或并发不足才标记为可重试。完整 per-run 上限在首次外呼前同时预留到全站和 Endpoint ledger，最多三次外呼还受 `estimated_input + max_output` 的单次最坏值约束，租约覆盖允许请求、退避和安全余量；可信多次 usage 累加结算，任一 usage 不可信或失败时保守结算完整预留，运行中租约过期同样保守结算且恢复幂等。调用终态与 ledger 结算同事务，完成时间使用终态时钟。隔离 PostgreSQL 已读回 `agents.0001_initial`、默认 policy `5,000,000/row_version 1`、认证快照列和新版 reservation shape 约束；`manage.py check`、`makemigrations agents --check --dry-run`、Ruff、Ruff format 和 `git diff --check` 均退出 0。Labs worktree 同源读回 `active/running`、health/home `200`；未执行 Labs/共享 migration、真实 Provider、Git 或生产动作。显式连通性检查的持久结果与管理交互归 T04，不在 T03 建立无页面消费者的平行事实。

补充裁决（2026-08-22）：调用方动态领域校验在统一 AGENT harness 内执行并参与一次 schema/semantic repair；失败、拒答、结构化修复失败和租约失效的 token reservation 统一以 `0` 结算，不进入每日额度，失败原因只通过安全通知说明。

### T04｜交付“AI 配置”一级组的 AGENT 与 Prompt 页面

状态：已完成（2026-08-17）。

依赖：T02-T03；Q038A-Q038B 已确认 Endpoint 全部运行参数由管理员逐项配置及其默认/硬范围。

结果：管理导航新增独立“AI 配置”一级组；仅管理员可使用 Endpoint/AGENT 列表和编辑弹窗，逐 Endpoint 编辑 context/output/per-run/timeout/concurrency/daily token 参数，并管理全站 daily token、用量摘要、“恢复默认上限”和“重置今日已用量”。完成启停、显式连通性检查、Markdown Prompt 多行编辑/安全预览/版本切换。普通业务用户没有配置入口。

验证：服务端管理员权限、CSRF、防重复、参数范围/交叉冲突、全站/单 Endpoint reset 对账与活跃预留保留、二次确认/row version/审计、连接检查频控/费用提示且不回写、错误保留表单、焦点恢复、390/768/1440 和三主题；页面不回显密钥或完整调用内容。

证据：连接检查聚焦回归在补齐 TaskRun/Celery 真实入口与 EndpointCheck 租约恢复后取得 `7 passed`；T02-T04、管理页面、环境与架构联合回归取得 `84 passed, 1 failed`，唯一失败是管理表单跨 app 私有 model 导入，改由 `apps.agents.public` 稳定枚举契约后架构守卫重新取得 `5 passed`，修正后的 T04 页面/连接检查/环境/架构联合回归为 `24 passed`。用量重置 422 会关闭弹窗且 Endpoint 焦点错误的缺陷已先增加聚焦回归，再由 View 保留弹窗/表单、模板恢复到精确触发点；目标用例取得 `1 passed`。Prompt 历史切换在 422 或 409 时会关闭确认弹窗的缺陷同样先取得聚焦 RED，再由 View 保留表单、弹窗与精确返回焦点，目标 GREEN 取得 `1 passed`。浏览器随后发现编辑既有 AGENT 时 disabled 的稳定标识不会随请求提交，而 bound form 未使用既有 initial，导致保存恒为 422；聚焦回归准确得到预期 302、实际 422 的 RED，View 在绑定前读取既有 profile 并传入稳定 initial 后取得 `1 passed`，格式化后的最终目标用例再次取得 `1 passed`，整个 `test_agent_management.py` 最终取得 `8 passed in 89.39s`。

隔离 PostgreSQL 已读回 `agents.0002` 的检查/owner 约束，并在空检查数据下反向到 `0001`、再次前向到 `0002`；有检查事实后只回滚应用、数据库保持向前。Labs 于 `2026-08-17` 获明确授权后执行 `agents.0001_initial` 与 `agents.0002_endpoint_connection_checks`，两条均退出 0；读回 migration leaf、10 张 `agent_%` 表、默认 policy `5,000,000/row_version 1`、`agent_token_reservation_owner_shape` 与检查索引，`agents_schema_ready()` 为 `True`。Labs web 仍指向当前 worktree 且为 `active/running`，live/ready 均为 `200`，两条管理路径匿名访问按权限边界返回 `403`。Labs worker 获明确授权后完成单服务 warm restart，新 PID 为 `2335338`，注册表读回 `. apps.agents.check_endpoint`，Redis 连接与 Celery ready 均成功；未实际创建连接检查或调用 Provider。

真实浏览器在 1440 完成浅色/深色/护眼三主题、无横向溢出、Endpoint 新建与刷新持久化读回；新增弹窗初始焦点为关闭按钮，`Shift+Tab` 环回保存按钮，Escape 关闭后焦点回到新增入口。768 浏览器完成 Endpoint reset 422、AGENT 首次启用 422、Prompt 安全预览、v1/v2 保存、强制 stale version 的 409、两类错误弹窗保留与 Escape 精确返回焦点，并在修复 disabled key 后真实启用 AGENT；最终 `768x1024` Prompt 原图无横向溢出，`FilePenLine=1`，控制台为 `0 error / 0 warning`。390 深色原图实际为 `390x844`：Endpoint 弹窗左右边界 `19/356`、宽 `337`，页面与弹窗均无横向溢出，`Activity=1`；Prompt 页面与内部滚动容器均无横向溢出，内部滚动范围 `0..604`，顶部粘性关闭入口和滚到底后的底部关闭按钮都完整可达，`FilePenLine=1`。两个缺失图标已进入唯一按需注册中心；最终 `npm run build:js` 退出 0，目标 Ruff、Ruff format、`manage.py check` 和 `git diff --check` 均退出 0。

隔离浏览器数据库与 Redis 只承载本次 T04 用户流；验收后唯一浏览器和本地 `8768` 服务均正常关闭，`kaj_test_agents_t04_browser` 定向删除后计数为 `0`，Redis DB 5 清空后键数为 `0`。Labs 最终读回仍指向当前 worktree 且为 `active/running`，live/ready 均为 `200`，两条管理路径匿名访问按权限边界返回 `403`；公网与 worktree 的 `static/dist/app.js` SHA-256 均为 `f087bca60539055681c667f1017fd92aa234f9ef14a6648729a1a327cc0eee49`。未执行真实 Provider、Git 或生产动作。

## 4. 知识文档审核

### T05｜扩展 media 的知识 Markdown 用途

状态：已完成（2026-08-17）。

依赖：T01；Q001 已确认复用现有附件能力，Q005 已确认 `2 MiB` 与自动分块预算。

结果：注册 `KNOWLEDGE_DOCUMENT` purpose、上传 adapter、目标 access port、绑定槽与清理；复用既有 UTF-8 文本探测但只允许 `.md`，硬上限 `2 MiB`，并向 learning 提供安全流式读取和元数据。

验证：权限、伪扩展、非 UTF-8、NUL、空文档、字节/字符/token 上限、重复请求、容量门禁、路径安全、绑定事务和解绑清理。

证据：聚焦 RED 退出 2，准确失败于缺少 `MAX_KNOWLEDGE_DOCUMENT_BYTES` 公共契约。实现后新增独立 `KNOWLEDGE_DOCUMENT` purpose、`learning_document/source` 单槽、仅 `.md` 的 UTF-8/NUL/空文档门禁、2 MiB 流式写入上限、独立无原文件名 storage key、附件能力上传 adapter、文本容量门禁，以及先完整校验大小/UTF-8/NUL/SHA-256 再暴露安全元数据和文本 iterator 的 `stream_authorized_text`；learning 目前只注册上传 adapter，目标访问 port 仍由 T06 的真实 `KnowledgeDocument` owner 注册，media 不读取 learning 私表。最终聚焦回归 `14 passed in 63.07s`，覆盖无权限 404、有效上传、伪扩展/路径、非 UTF-8、NUL、零字节/BOM 空文档、精确 2 MiB、PostgreSQL 错误 MIME/超限/伪尺寸约束、未绑定拒读、单槽冲突、授权流读、篡改拒绝和解绑删文件；media 上传/绑定访问/清理相关回归 `29 passed in 92.59s`，架构守卫 `5 passed`。目标 Ruff、Ruff format、`manage.py check`、`makemigrations media --check --dry-run` 与 `git diff --check` 均退出 0。

隔离 PostgreSQL 已完成全量前向到 `media.0007_knowledge_document_media`，读回 purpose 长度 `32` 及 size/knowledge-format/dimensions/target 四项约束；反向到 `0006` 后 migration 记录与 knowledge-format 约束均为 `0`、purpose 长度恢复 `16`，再次前向成功。验收后 `kaj_test_agents_t05` 定向删除、Redis DB 6 清空，二者读回均为 `0`。Labs 获明确授权后执行 `media.0007_knowledge_document_media` 并退出 0；读回 migration 记录 `1`、purpose 长度 `32`、四项约束存在，media asset/binding 行数保持迁移前后的 `10/17`。Labs 服务仍指向当前 worktree 且为 `active/running`，live/ready 均为 `200`，匿名知识上传入口按权限返回 `404`。未创建 Labs 业务数据，未执行真实 Provider、Git 或生产动作。

### T06｜建立知识文档提交与状态机

状态：已完成（2026-08-17）。

依赖：T02、T05；Q006-Q007、Q024-Q025 已确认原文归属、自动通过、完整生命周期和账户内摘要去重。

结果：新增 LearningQuotaPolicy、账户字段覆盖、自然日 usage 与原子预留，随后建立 KnowledgeDocument、审核运行/结论与 owner service/query。默认/硬范围落实 10 uploads/day（1..100）、3 pending reviews（1..20）、5 generations/day（1..50）、1 concurrent model run（1..3）、100 unpurged banks（1..2000）。实现 STAGED、REVIEW_PENDING、REVIEWING、APPROVED、REJECTED、REVIEW_FAILED、DELETE_PENDING、CONTENT_PURGED、DELETED 转换和审核输入快照，用户主动删除保存前态并进入统一 `7 天`可撤销期，驳回/最终失败材料 `30 天`后清为无正文 tombstone；同账户按保守规范化 SHA-256 条件唯一去重并为各状态提供正确恢复入口，跨账户不共享或泄露碰撞。旧 Todo 中的 `PENDING/FAILED` 是与 Q024/Q036 及状态机不一致的简写，本次统一为既有已确认稳定枚举，不建立兼容别名。

验证：配额全局继承/部分覆盖/硬范围/自然日/并发预留/权限撤销、上传与待处理边界、服务端对象归属、非法转换、BOM/换行等价与语义空白不等价、同账户各状态重复上传、并发唯一约束、跨账户同内容独立且无碰撞泄露、并发删除/审核、失败资产保留与清理、公开/私有读取边界。

证据：三个聚焦测试文件先以缺少 `apps.learning.public` 的 collection error 取得 RED（退出 2）。实现后 learning 独占 7 张配额/文档/审核运行事实表、默认/覆盖/自然日 usage、账户并发锁与租约 reservation、版本化上传声明、规范化摘要/元数据、owner 查询、review claim/终态、7 天删除恢复和 30 天失败内容清理；media 仅新增 owner 未绑定知识 Markdown 的受控流读，公开未绑定下载仍拒绝。初轮回归 `21 passed`；覆盖审计新增的重复 release、CJK 保守 token、最终 review 材料清理、撤权后禁止领取和同 owner 并发摘要用例先准确得到 `4 failed, 1 passed`，修复后为 `5 passed`。管理员降并发后拒绝新任务会回滚过期 reservation 的缺陷另取得单用例 RED，改为独立回收事务后 GREEN `1 passed`。最终完整 learning 回归为 `27 passed in 103.81s`，格式化后的 quota 文件回归为 `11 passed`；media access/binding 相关回归 `19 passed`，架构守卫 `5 passed`。目标 Ruff、Ruff format、`manage.py check`、`makemigrations learning media --check --dry-run` 与 `git diff --check` 均退出 0。

隔离 PostgreSQL 全量前向后读回 `learning.0001_initial`、7 张 `learning_%` 表、默认 policy `10/3/5/1/100/v1`、owner 摘要条件唯一、单文档单活跃 review、内容/配额/reservation 形状约束；反向 `learning zero` 后表与 migration 记录均为 `0`，再次前向成功并重新 seed 相同 policy。验收后 `kaj_test_agents_t06` 定向删除、Redis DB 7 清空，二者读回均为 `0`。Labs 获明确授权后执行 `learning.0001_initial` 并退出 0；读回 migration 记录 `1`、7 张表、默认 policy、关键约束/条件唯一，6 张业务表合计为 `0`，未创建业务数据。Labs 服务仍指向当前 worktree 且为 `active/running`，live/ready 均为 `200`，匿名知识上传入口按权限返回 `404`。未执行真实 Provider、Git 或生产动作。

### T07｜闭合审核 AGENT 异步运行

状态：已完成（2026-08-17）。

依赖：T03、T06。

结果：事务提交后派发审核，在领取模型运行前执行账户并发配额和 agents token reservation；TaskRun 实现领取、租约、心跳、重试、取消/删除竞态和最终结论，固定审核 schema 与稳定原因码。审核通过/驳回/最终失败在终态事务通过现有 Outbox 与通用通知模板幂等通知发起用户，系统最终失败额外进入现有管理员提醒。

验证：合格、非知识、危险、Prompt injection、坏 schema、业务/并发/token 配额阻塞时零外呼、前两次失败第三次成功、最终失败、六类通知中的审核三类收件人/去重/脱敏、重复投递、Worker 崩溃、配置切换和文档删除。

进行中证据：聚焦 RED 退出 2，准确失败于 learning 无法从 `apps.agents.public` 获取结构化 schema 注册契约；agents 随后公开唯一 schema port，learning 注册固定 `knowledge-review.v1`，实现 16 KiB/最多 128 块的标题/列表/段落优先分块、危险链接/结构门禁、提交事务后派发及 broker 失败补偿、review run TaskRun/Invocation/reservation 快照、真实 AgentGateway 调用和终态 Outbox。第一组 schema/分块/派发/假 Provider 通过与驳回为 `4 passed`；TaskRun 三次最终失败、owner+管理员通知、业务并发零外呼和删除竞态加入后两组为 `8 passed`；Prompt injection 只进入 user material、坏 schema 安全重试、agents token 配额零外呼、Provider 前两次瞬时失败第三次成功加入后目标回归为 `12 passed`。完整 learning 回归为 `39 passed in 143.24s`，真实 `review_document_task.apply`/TaskRun/Gateway 入口另为 `1 passed`；agents Gateway、notifications 与架构相关回归 `26 passed`。最终 Ruff、Ruff format、`manage.py check`、`makemigrations agents learning notifications --check --dry-run` 与 `git diff --check` 均退出 0，全部模型调用只使用确定性假 Provider。

隔离 PostgreSQL 已完成全量前向到 `learning.0002_review_runtime`，读回 10 个运行字段及 attempt/dispatch/execution/input/last-error 五条约束；反向到 `0001` 后 migration 记录与字段均为 `0`，再次前向成功。验收后 `kaj_test_agents_t07` 定向删除、Redis DB 8 清空，二者读回均为 `0`。Labs 根据当前 Goal 持续授权执行 `learning.0002_review_runtime` 并退出 0；读回 migration 记录 `1`、10 个字段、五条约束，review 行数仍为 `0`。Labs web 仍为 `active/running`，live/ready 均为 `200`。`kaj-labs-worker.service` warm restart 后 PID 从 `2335338` 更新为 `2851280`，保持 solo/concurrency 1，日志读回 Redis 连接、Celery ready 和 `. apps.learning.review_knowledge_document` 注册。未执行 Labs 业务数据写入、真实 Provider、Git 或生产动作。

### T08｜交付用户知识文档入口与状态页

状态：已完成（2026-08-17）。

依赖：T06-T07；Q011、Q029-Q032 已确认账户浮窗入口、全部终态通知、逐次上传授权、正式申诉和管理员原文访问历史。

结果：在右上角账户浮窗为有附件能力的用户增加“知识文档”导航，进入独立“我的知识文档”页面；每次上传要求当前版本且默认未选中的授权/模型处理/公开衍生内容声明，并保存确认事实；显示本人的待审、审核中、通过、驳回和失败状态，支持删除、正式申诉、撤回申诉和重新审核业务动作，并分页展示不含管理员身份的原文访问时间/用途历史。用户直接使用管理员启用的审核 AGENT，不显示 Endpoint、Model、Prompt 或密钥选项。

验证：访客/无权限/有权限/管理员本人矩阵，声明未选/旧版本/当前版本/重复请求、真实上传与声明/数据库/资产读回，申诉目标状态/同时一条/并发版本/撤回/批准重审/驳回/清理暂停、成功原文读取审计/列表不预取/失败不误记、owner 历史隐藏 actor/管理员审计可见 actor/无实时通知、异步局部刷新不跳页，错误不丢文件选择以外的表单状态，通知与页面终态一致。

证据：后端 Appeal/Access/retry 聚焦 RED 准确失败于缺少 `KnowledgeDocumentAccessPurpose` 公共契约，新增 `LearningAppeal`、`KnowledgeDocumentAccess`、同文档单 pending、Markdown 安全渲染、owner retry、管理员批准重新审核/驳回事件、成功原文访问审计及隐藏 actor 的 owner 历史后取得 `5 passed`。HTTP RED 从缺少 `learning:documents` 路由开始，交付条件账户菜单入口、媒体 picker、逐次声明、状态列表、详情/申诉弹窗和 HTMX 局部动作后取得 `3 passed`；角色/Header 补强后后端+HTTP 为 `8 passed`，完整 learning + media picker 回归 `53 passed in 207.79s`，前端 Node `6 passed`。Ruff、Ruff format、`manage.py check`、`makemigrations learning --check --dry-run`、`npm run build:css`、`npm run build:js` 与 `git diff --check` 均退出 0。

真实浏览器以隔离 PostgreSQL/Redis/媒体完成：1440 浅色从个人菜单键盘 Enter 展开并进入“知识文档”，真实 `.md` 上传、未勾声明原生阻止、勾选后 HTMX 提交并持久读回 `REVIEW_PENDING`，删除/恢复、申诉提交和详情 Markdown 均成功；1440 浅色/深色/护眼三主题无横向溢出、缺失图标为 0。首次 768 原图发现全局 switch `nowrap` 导致长声明溢出，改为 `minmax(0,1fr)` 与正常换行后 768 page/statement overflow 均为 false；390 护眼页、picker、声明和按钮均无溢出，详情 dialog 左右 `19/356`、宽 `337`、无横向溢出，初始焦点为关闭，Escape 后 URL 回到文档锚点且焦点精确返回 `knowledge-view-*`。控制台 `0 error / 0 warning`。

隔离 PostgreSQL `learning.0003_appeals_access` 前向后为 9 张 learning 表并读回 decision/access/trace/单 pending 约束；反向到 `0002` 后 migration 记录为 0、表数恢复 7，再次前向成功。Labs 根据持续授权执行 `learning.0003` 并退出 0，Appeal/Access 两表合计 0、约束存在，web `active/running`、live/ready `200`、匿名 `/knowledge/` 正确 302 登录；公网与 worktree CSS SHA-256 均为 `6cd5424be0df66e7f29fc1544d35795d92ca28fa1950a0c3d7028fd3a10f3159`，JS 均为 `f3ef0556649cfbf8b0e33f9963128d70e5ca5ffbed365014a847dafdcad3d702`。验收后浏览器/本地服务、`kaj_test_agents_t08`、Redis DB 9、临时媒体/脚本/截图全部定向清理；未使用真实 Provider、Git 或生产动作。

## 5. 题库生成

### T09｜建立结构化题库、题目和标签事实

状态：已完成（2026-08-17）。

依赖：T01、T06；Q012-Q017 已确认多题库、覆盖降级、系列元数据、不可变题库修订、独立题库标签目录和多选严格匹配计分，Q023-Q024 已确认管理与完整删除/保留关系。

结果：实现带可变基础标题/简介/标签和 row version 的 QuestionBankSeries、最多两个带 current revision 指针的 QuestionBank 卷、不可变 QuestionBankRevision/Question、知识点覆盖/遗漏引用、由 `apps/learning` 独占且不复用文章标签的 QuestionBankTag/系列关联、生成配置、管理员单卷上限快照、区分 owner/admin 隐藏且禁止 owner 解除管理员锁定的公开/删除状态，以及固定 question schema。题库创建 service 同时落实每日生成次数和未清理题库总数配额的原子预检/占用。

验证：四题型约束、选项/答案一致性、题数/总大小、每日生成/题库总数默认与覆盖边界、两卷对总数的明确计数、标签规范化竞态、历史版本不可变、隐藏后公开查询失效、迁移与索引。

证据：聚焦 RED 最初准确失败于缺少 `GenerationQuestionTypes` 公共契约；完成系列/卷/不可变修订与题目、知识点覆盖、独立标签、生成请求、原子发布、修订和 owner/admin 可见性/删除恢复 service 后，首轮真实 PostgreSQL 为 `3 passed / 4 failed`，四项失败均定位到测试夹具提交了跨卷连续 ordinal、未启用题型和重复文档正文，修正输入而未放宽门禁后为 `7 passed`。随后新增修订覆盖不可丢失与两卷必须占用两个未清理题库名额的 RED，修复后 `2 passed`；现有标签并发复用 RED 稳定复现 `usage_count=2` 而关联数为 `3`，改为 PostgreSQL `F()` 原子更新并复核 ACTIVE 后 GREEN `1 passed`；数据库旁路更新 revision/question 和跨卷 current revision 指针的 RED 通过复合外键与两个不可变触发器闭合。最终 T09 聚焦集为 `10 passed in 36.22s`，完整 learning 回归为 `58 passed in 174.89s`，架构守卫为 `5 passed`；Ruff、Ruff format、`manage.py check`、`makemigrations learning --check --dry-run` 均退出 0。

隔离 PostgreSQL 从空库按全迁移图前向到 `learning.0004_question_bank_facts`，读回 7 张 T09 表、2 个不可变触发器、同卷 current revision 复合外键、revision `(bank,id)` 唯一约束和 2 个业务索引；回退到 `0003` 后迁移记录、表、触发器和复合外键均为 `0`，再次前向全部恢复且业务行仍为 `0`。首次尝试在空库仅指定 learning 目标时，`learning.0004` 已应用但全局 `post_migrate` 因 navigation 表尚未建立而退出 1；已定向重建本任务隔离库并改用真实全量迁移图完成上述往返，不把该无效命令计为通过证据。Labs 根据持续授权应用 `learning.0004` 并退出 0，读回相同 7 张表/2 个触发器/复合外键且 QuestionBankSeries 行数为 `0`；web 仍指向当前 worktree、`active/running`，live/ready 均为 `200`，匿名 `/knowledge/` 正确 302 登录。验收后 `kaj_test_agents_t09`、pytest 派生库和 Redis DB 10 均定向清理，PostgreSQL 目标库计数与 Redis 键数读回均为 `0`。未执行真实 Provider、Git、生产或服务重启动作。

### T10｜闭合题库生成 AGENT 运行

状态：已完成（2026-08-17）。

依赖：T03、T07、T09。

结果：从本人 APPROVED 文档创建生成请求，原子占用每日生成/题库容量/并发模型配额并预留双层 token，固化允许题型、管理员单卷上限、文档、Prompt、模型和 schema 版本；AGENT 先建立全量知识点清单，再逐点生成并选择题型。先尝试综合题单卷全覆盖，容量不足时按重要度生成第一卷和至多一个第二卷；原子发布完整卷、标签和 coverage 结果，不覆盖同源旧题库。完整、部分覆盖和最终失败在终态事务通过现有 Outbox 幂等通知用户，系统最终失败额外通知管理员。

补充实现（2026-08-24，开发阶段原地升级）：生成仍按安全大小和源结构拆成有序 `src-####` 源知识单元并进行有界批次调用，但源单元不再等同于知识点或题目。AGENT 自行判断每批知识点数量，并为每个知识点返回 `source_unit_ids` 证据引用；每道题的 `knowledge_point_ids[0]` 是主要考查点，后续 ID 是辅助考点，题目数量只是上限。服务端逐批验证内部引用、跨批次合并、重新编号和最多两卷组卷，空批次允许存在但整份文档没有可发布题目时仍失败。模型不知道输入是否预先有序，只能把检测到的结构作为降低理解成本的线索。

验证：所有题型组合、至少一个 Switch、业务/并发/token 配额不足时零外呼、单卷全覆盖、综合题压缩、两卷边界、第二卷后遗漏提醒与通知计数、非容量错误不降级、同文档多次生成互不覆盖、标签优先复用、非法/半卷输出不落公开事实、幂等、重试、崩溃恢复和预算上限。

证据：聚焦 RED 首先准确失败于缺少 `QUESTION_GENERATION_PROFILE_KEY` 公共契约；新增固定 `question-generation.v1` schema、无默认且未配置即关闭失败的管理员单卷上限、请求事务内 AgentInvocation 配置快照、事务后派发/有界补偿、generation run 字段/约束、Gateway/TaskRun 执行、现有 learning 并发 reservation/agents 双层 token reservation、原子 publish 与完整/部分/失败 Outbox 后，首组 schema/缺配置/派发/完整生成为 `4 passed`。随后综合题单卷、完整两卷、显式遗漏、坏 schema 不降级且零半卷、未选题型拒绝、业务并发/token/附件权限在 Provider 前阻断、同源文档多次生成互不覆盖、Provider 前两次瞬时失败第三次成功、三次任务最终失败、晚到结果遇源文档删除取消、提交后 TaskRun 崩溃恢复和三类通知去重均闭合。复核发现每次重试重新解析当前 Profile 会让在途配置漂移，进一步把首个 Invocation 快照前移到请求事务，首尝试只绑定 TaskRun、后续尝试由 agents owner 从该快照克隆；管理员在请求后修改 Prompt/模型的回归证明仍读取原序号/模型。最终 T10 聚焦组为 `23 passed in 95.48s`，历史 `0004 -> 0005` 数据回填单测为 `1 passed`，完整 learning 回归为 `81 passed in 267.04s`；agents Prompt/Gateway 回归 `36 passed`、notifications 回归 `15 passed`、TaskRun+架构守卫 `16 passed`。Ruff、Ruff format、`manage.py check`、`makemigrations agents learning notifications --check --dry-run` 与 `git diff --check` 均退出 0；全部模型调用使用确定性假 Provider。

隔离 PostgreSQL 从空库按全迁移图前向到 `learning.0005_question_generation_runtime`，读回 17 个系列运行列、10 个运行/上限约束、1 个失败扫描索引、管理员单卷上限 `NULL` 和业务行 `0`；回退到 `0004` 后 migration/列/约束/上限列均为 `0`，再次前向全部恢复。迁移回填测试在真实 `0004` 历史模型中建立已发布题库，前向后准确回填源文档 SHA-256、首次发布时间、完整终态摘要且不伪造管理员上限或历史 Invocation。Labs 根据持续授权应用 `learning.0005` 并退出 0，读回相同 17 列/10 约束、上限 `NULL`、系列和 generation Invocation 均为 `0`；worker warm restart 后 PID 从 `2851280` 更新为 `3309592`，日志确认 `. apps.learning.generate_question_bank` 与 review 任务同时注册、Redis connected、Celery ready。web/worker 均指向当前 worktree 且 `active/running`，live/ready 均为 `200`，匿名 `/knowledge/` 正确 302 登录。验收后 `kaj_test_agents_t10`、pytest 派生库和 Redis DB 11 均定向清理并读回 `0`。未执行真实 Provider、Git、生产或 web 重启动作。

### T11｜交付题库生成配置与结果页面

状态：已完成（2026-08-17）。

依赖：T08-T10。

结果：用户选择通过文档，填写基础标题/可选简介和题型 Switch 发起生成，不显示题量输入；直接使用管理员启用的题库生成 AGENT 和管理员单卷上限。页面显示 pending/running/published/failed，成功后展示一卷或两卷及覆盖/遗漏提醒；发布后 owner/admin 可修改系列元数据和题目，题目保存生成新修订；失败可按新业务动作重试。

验证：配置边界、重复点击、运行中配置不可漂移、局部热更新、失败恢复、手机控件同一行和 Switch 可访问性、数据库终态读回。

证据：HTTP RED 准确缺失 approved 文档的“生成题库”入口与 `dispatch_question_generation` 动作；先闭合四题型 Switch、无题量/模型控件的配置 dialog、请求持久化、事务后派发、pending/running/published/failed 投影和无 dialog 时每 8 秒 HTMX workspace fragment 刷新。随后 owner service RED 缺少 `QuestionContentDraft`、元数据更新、单题修订和失败重试；把标签规范化/使用计数从初始发布提取为 learning 唯一 owner，资料编辑复用该 owner，单题编辑由 service 读取当前完整卷并调用既有不可变修订，失败重试创建新系列并重新计数。页面按需打开系列资料、卷内题目目录和单题编辑 dialog，不在列表预取全部题目；缺上限/profile 时诚实禁用入口，未选题型 422 保留 dialog/幂等键，重复提交只建一条系列且只派发一次。T11 owner/HTTP 与既有文档聚焦回归 `13 passed`，最终 T11+架构复核 `15 passed`，完整 learning 回归 `91 passed in 318.06s`，前端回归 `6 passed`；Ruff、Ruff format、CSS/JS build、`manage.py check`、`makemigrations agents learning --check --dry-run` 与 `git diff --check` 均退出 0。前端测试仍仅有项目既有 Node module-type 性能警告，无失败。

真实浏览器使用隔离 PostgreSQL/Redis/媒体和真实密码登录，完成配置提交后数据库新增 `浏览器生成题库/PENDING`，资料编辑读回 `Python 浏览器修订题库`，单题保存后 current revision 从 v1 切至 v2 且新题干持久化；最终读回系列 `4` 条（pending `2`、published `1`、failed `1`）、目标标题/题干/revision 各 `1`、每日生成计数 `4`。初次 headed 启动因主机无 X Server 失败，按规则改为 headless；后续 autoreloader 退出导致历史轮询网络错误，关闭会话后仅用同一入口加 `--noreload` 恢复一次，最终会话控制台为 `0 error / 0 warning`。浏览器发现并修复两个 Lucide 白名单告警、dialog 打开时轮询会替换未提交输入、带生成记录的单文档仍占半列三个问题。1440/light、768/dark、390/eye-care 均无页面/card/button 横向溢出，缺失图标为 `0`；390 dialog 左右 `19/356`、宽 `337`、无内部溢出，初始焦点为关闭，Tab 到标题，Escape 后焦点精确返回生成按钮。T11 采用现有中性表面、单一 accent、1px 分隔与无嵌套卡片的 Swiss 结构，生成状态以不改变布局的细线轨道呈现，并尊重 reduced-motion。

T11 无 schema 变化和 Labs 业务数据写入。Labs 直接读取当前 worktree 的源码/模板与构建产物，web/worker 均 `active/running`，live/ready `200`，匿名 `/knowledge/` 正确 302；公网/本地 CSS SHA-256 同为 `e5c9bcd2f998dd3f686646c22d372a7fa28f14c29219735a3cb3cb1c887e06b1`，JS 同为 `cf7539a38de7042e1af874461a32697c7b6cb2159bcc19fd8a1e0ac5e3ea4225`。验收后 T11 两个隔离数据库、浏览器数据库、Redis DB 12/13、临时媒体/settings/seed/state/截图与浏览器/服务均定向清理并读回 `0`。未执行真实 Provider、Git、生产、Labs migration 或服务重启动作。

## 6. 公开题库与管理

### T12｜交付公开题库列表、搜索、筛选和详情

状态：已完成（2026-08-18）。

依赖：T09；Q026、Q034 已确认排序/筛选/搜索语义和独立 HTML/API transport 复用同一 query。

结果：所有访客共享同一公开 query；独立 HTML transport 服务端渲染列表/详情并展示裁决后的元数据、题面/答案范围，默认按首次发布时间倒序，可切换已完成答题次数和题量升/降序，使用稳定次级键；支持标签/题型组内 OR、题量/发布时间区间、作者选择和标题/简介/标签模糊搜索，不同组间 AND，并通过同一 filter DTO/query 服务 HTML 与独立 JSON API transport。

验证：空/加载/无匹配/页码失效、同组 OR/跨组 AND/空组、区间边界与非法参数、作者建议归属、搜索字段正反例、排序稳定性、HTML/API query 等价、隐藏/删除与缓存失效、访客/登录一致性、390/768/1440 三主题和键盘流。

证据：新增唯一 `PublicQuestionBankFilters`/公开 query projection 和独立服务端 HTML transport，公开列表只返回元数据，详情返回当前不可变 revision 的题目、答案、评分要点与解析且不暴露源文档；标签/题型组内 OR、跨组 AND、题量/发布时间/作者、标题/简介/独立标签 trigram 模糊搜索、最新/最多答题/题量排序和稳定分页均由 query 聚焦回归覆盖。首次迁移回退准确暴露 learning 重复拥有共享 `pg_trgm` 会破坏文章 trigram 索引，改为显式依赖 `content.0010` 后，隔离 PostgreSQL 完成全图前向、`0006 -> 0005 -> 0006` 往返：回退时 learning 字段/4 索引归零但共享扩展与文章索引保持，前向后全部恢复且业务行始终为 0。历史 `0004 -> 0005` 测试固定恢复旧 leaf 导致后续 schema 污染，teardown 改为恢复 learning 当前 leaf；跨 `Asia/Shanghai` 午夜又暴露旧断言错误假设账户只有一条自然日 usage，改为读取实际接受生成请求的日记录。最终 learning 全量回归 `103 passed in 429.16s`，架构守卫 `5 passed`，前端 `6 passed`；Ruff、Ruff format、`manage.py check`、`makemigrations learning --check --dry-run`、CSS build 和 `git diff --check` 均退出 0。

真实浏览器使用隔离 PostgreSQL/Redis/媒体完成：1440 浅色列表/详情、768 深色详情、390 护眼展开筛选与卡片均以原尺寸检查；筛选提交得到 0 结果，详情展示答案/解析，隐藏题库返回 404。浏览器发现并修复长作者 ID 挤压卡片正文、作者下拉固有宽度撑开页面、卡片隐式 Grid 轨道按 min-content 溢出和筛选控件无可见边界四项布局问题；最终 390 viewport/page scroll width 为 `390/375`、卡片/内部轨道为 `343/301`、输入为 `343x46` 且 1px 边界。Summary 聚焦后 Enter 可折叠/展开，Tab 精确进入 `id_q`；正常列表最终控制台 `0 error / 0 warning`，隐藏对象只有主文档预期 404 error。验收后浏览器、本地服务、两个隔离数据库、Redis 14/15、临时媒体和截图均定向清理并读回 0。

Labs 根据持续授权应用 `learning.0006_public_question_bank_projection` 并退出 0；读回字段、4 个 learning 索引、共享 `pg_trgm` 和文章 trigram 索引均存在，系列/卷仍为 `0/0`。web 继续指向当前 worktree 且 `active/running`，live/ready/`/question-banks/` 均为 `200`，公开页读回“知识题库”；公网与 worktree CSS SHA-256 同为 `722a34272fc350c319ecb5b204dee202fe878455f8e17eb5438441573a58a2ae`。未执行真实 Provider、Git、生产或服务重启动作。

### T13｜交付知识文档与题库管理页面

状态：已完成（2026-08-18）。

依赖：T06、T09-T10；Q031-Q032、Q037 已确认申诉处理、原文访问透明度和显式勾选批量操作。

结果：“智能与题库”一级组提供 LearningQuotaPolicy 全局默认与有附件权限账户字段覆盖、本人剩余摘要边界、自动审核/生成状态、脱敏错误、题库公开状态、事后隐藏/恢复/删除和申诉审核队列；文档申诉批准只触发新 AGENT 审核，管理处置批准显式恢复并通过 Outbox 通知 appellant。管理员成功查看原文写含 actor/用途的访问审计，不触发用户通知。文档/题库支持仅限显式勾选 ID 的批量隐藏/恢复/删除预检与有界逐项结果，不支持当前页/全部筛选展开；原文和申诉逐条。不建立发布前人工审核队列。所有写动作调用 owner service 并审计/通知。

验证：管理员权限、业务配额默认/部分覆盖/清除覆盖继承/硬范围/row version/审计与用户摘要隔离、确认弹窗、分页与有界加载、显式 ID/数量/状态分布、禁止当前页和筛选展开、部分失败逐项结果、原文/申诉无批量入口、申诉结果通知去重、状态竞态、错误不泄露正文/Prompt/答案/密钥、侧边提醒已读语义。

证据：新增 `learning.0007_remove_learningappeal_learning_appeal_one_pending_document_and_more`，为文档/题库增加管理员锁定与删除 actor，申诉改为文档或题库二选一并分别保持单个 pending 唯一；旧 DELETE_PENDING 数据回填为 OWNER。`apps.learning.services.administration` 提供管理员隐藏/恢复/删除、显式 ID + row version 预检/执行、最大 50 项的逐项成功/失败结果；administration query 提供文档/题库/申诉分页、原文访问审计和全站 quota/账户 override 查询。申诉批准后的恢复、AuditEntry 和通用通知事件 `learning.document_administration_changed.v1` / `learning.question_bank_administration_changed.v1` 接入现有通知 owner；“智能与题库”一级组导航包含“知识文档与申诉”“题库与运行”，附件授权账户提供配额覆盖入口，批量 dialog 关闭后恢复到触发按钮焦点。

聚焦回归在正确隔离 PostgreSQL/Redis/Mailpit 环境中取得 `13 passed in 108.04s`（learning administration、administration HTTP、notifications consumer）；此前 T13 完整 learning 回归取得 `107 passed`。最终 `.venv/bin/ruff check`（相关 410 个 Python 文件）、`ruff format --check`、Django `check`、`makemigrations --check --dry-run`、`git diff --check` 均退出 0；修复了学习申诉通知 builder 的错误缩进并以确定性 EventEnvelope 读回 `learning_appeal_notification_builder=ok`。`npm run build:css` 与 `npm run build:js` 均退出 0。

真实浏览器在隔离数据库完成管理员登录、文档列表脱敏展示、显式“查看原文”弹窗和访问审计读回、题库批量确认弹窗、取消后的焦点恢复、全站配额保存后 row version/新值读回；1440 浅色、768 深色、390 护眼均完成，无页面横向溢出，控制台 `0 error / 0 warning`。原文访问只在显式 dialog 请求发生，匿名管理路径返回 `403`。

Labs 已按持续授权应用 `learning.0007` 并退出 0；迁移读回 0001-0007 全部已应用，文档管理员字段、题库删除 actor、申诉双目标字段和两条 pending 唯一约束存在。`kaj-labs.service` 读回 `WorkingDirectory=/home/code/.codex-worktrees/personal-blog/labs-test-environment`、`active/running`，`/health/live=200`、`/health/ready=200`、`/question-banks/=200`、匿名 `/admin/learning-documents/=403`；`static/dist/app.js`、`navigation-state.js`、`styles.css`、`theme.js` 公网与 worktree SHA-256 全部一致。未执行真实 Provider、Git 交付、生产 migration、生产部署或真实邮件。

## 7. 外部只读 API

### T14｜建立 API 开关与版本化 projection

状态：已完成（2026-08-18）。

依赖：T12；Q009-Q010、Q027-Q028、Q034-Q035A 已确认匿名只读详情、独立 JSON transport、CORS 白名单、关闭响应和页码分页。

结果：管理 Switch 默认关闭；关闭时在对象查询前对列表/详情统一返回 JSON `404/api_disabled` 与 `no-store`；开启后以独立 JSON transport 实现匿名只读 `/api/v1/question-banks` 列表和详情，复用与 HTML 相同的公开 query/projection；列表按页码分页，page_size 默认 20、硬范围 1..100，并返回固定分页 envelope；列表返回元数据，详情返回完整题目/答案/解析；定义 IP 限流、筛选、排序、错误 envelope、schema version、OpenAPI 合同和只接受 `ALLOWLIST` 的版本化 CORS 策略模式，不提供 AGENT 或答题写接口。

验证：关闭时列表/存在与不存在 ID/GET/HEAD 响应完全一致、JSON envelope/no-store/无对象查询、开启后 not_found 区分、隐藏对象、page 默认/正整数/page_size 1/20/100/越界、空页与链接参数保留、稳定分页、HTML/API 可见性一致、完整答案字段、内部信息不暴露、管理员开关审计，以及开关变化与题面/答案缓存同时失效。

证据：新增 `QuestionBankApiConfiguration` 单例（默认 `enabled=false`、`cors_mode=ALLOWLIST`、row version）及 `learning.0008_question_bank_api_configuration`，迁移内种下默认配置；learning service 负责管理员权限、row version、只接受 ALLOWLIST 和审计，公开 API transport 位于 `/api/v1/question-banks/`，列表/详情先过 gate 再调用既有公开 query/projection。JSON 使用固定 `schema_version=1` envelope，列表返回 `count/total_pages/page/page_size/previous/next/results`，详情返回题面、选项、正确答案、参考答案、评分要点和解析，不返回原文、Prompt、Endpoint、模型或审核内部字段；关闭时列表与任意详情统一 `404/api_disabled` + `Cache-Control: no-store`，参数错误与隐藏对象分别返回稳定 JSON 错误码。

聚焦 API 回归 `4 passed in 79.27s`，公开题库 query/HTML 与管理回归 `16 passed in 120.84s`；相关 Ruff、Ruff format、Django check、migration drift 和 `git diff --check` 均退出 0。Labs 应用 `learning.0008` 并读回 0001-0008 全部已应用、默认配置 `False/ALLOWLIST/row_version=1`、单例/模式/版本约束；临时开启 API 后公网列表 `200`、固定分页 envelope 和空结果读回，再恢复关闭。

Labs `kaj-labs.service` 仍为当前 worktree、`active/running`，`/health/live=200`、`/health/ready=200`、`/question-banks/=200`；新增 Nginx 精确路由把 `/api/v1/question-banks/` 指向 Labs web（原 `/api/` 保持生产 Caddy 代理），`nginx -t` 与 reload 成功，公网列表和任意详情在关闭状态均为 JSON `404/api_disabled` + `no-store`。未执行真实 Provider、Git 交付、生产 migration、生产部署或真实邮件。

### T15｜补齐 API 限流、CORS 与缓存

状态：已完成（2026-08-18）。

依赖：T14；Q035B-Q035C、Q039 已确认限流默认/硬范围及 Redis 故障 fail closed。

结果：实现可信代理边界内的客户端 IP 解析、PostgreSQL 持有配置且 Redis 原子计数的管理员可调双层匿名 IP 限流（默认 60/minute、3000/day；硬范围 1..600/minute、100..100000/day 且 daily >= minute）、`429/rate_limited`/Retry-After/标准额度头；Redis 不可用时在 query 前 fail closed 为 `503/rate_limiter_unavailable`/no-store 且不回退数据库/内存/放行。实现管理员精确 HTTPS Origin 白名单、规范化与唯一约束、命中回显、`Vary: Origin`、无 credentials、预检、ETag/条件 GET、缓存失效和匿名用量摘要；无 Origin 服务端调用保持可用，不建立 API key 管理。为未来 `ANY_ORIGIN` 保留策略枚举/端口扩展位置，但首版拒绝配置或执行该模式。

验证：可信/不可信代理与伪造转发头、默认/边界/非法限流配置、并发分钟/每日额度、429 envelope/headers、配置并发与审计、Redis 连接/脚本/超时故障均在 query 前 503/no-store、无 DB/内存/放行 fallback、HTML 正常、故障通知去重与恢复、空白名单、精确命中/未命中、大小写与默认端口规范化、恶意 Origin、通配符/`null`/路径拒绝、无 Origin、同源、预检、缓存跨 Origin、credentials 缺失、304、开关/隐藏后的缓存失效、并发请求、响应大小、管理员权限/审计，以及未知/未来 mode 不会降级为 `*`。

证据：扩展 `QuestionBankApiConfiguration` 保存分钟/每日限额与 JSON Origin 白名单，service 只接受规范化 HTTPS `ALLOWLIST`（去重、大小写/默认 443 归一化，拒绝路径、userinfo、query、fragment、通配符、`null`）并以 row version + 审计更新；新增 `learning.0009_question_bank_api_policy` 与分钟/每日范围及 `daily >= minute` 约束。Redis limiter 使用受控 cache backend 的原子 `add/incr`，计数键只保存网络主体摘要，不回退 PostgreSQL、进程内状态或放行；API 在公开 query 前统一处理限额、Origin、OPTIONS 预检、`429`/`503`，成功响应带 `RateLimit-*`、`ETag`，条件命中返回 304，ETag 纳入配置 row version 以在开关/策略变更后失效；未命中 Origin 不回显许可头且无 credentials。

临时聚焦回归与管理回归取得 `8 passed in 100.50s`；最终 Ruff/Ruff format、Django check、migration drift、`git diff --check` 均退出 0。真实浏览器在管理题库页面完成 1440 浅色、768 深色、390 护眼视口检查，API 开关、Origin、分钟/每日字段可达，三视口 page/body scroll width 分别为 `1425/753/375`（无横向溢出），控制台 `0 error / 0 warning`。

Labs 已应用 `learning.0009`，读回默认 `False/ALLOWLIST/[]/60/3000`、限额约束和 row version；临时打开 API 后公网列表 `200`、Origin 回显与 `RateLimit-Limit/Remaining/Reset`、ETag/304 读回，将分钟限额调为 1 后第二次请求准确返回 `429` + `Retry-After`，随后恢复关闭并清理 Redis `learning:api:rate:*` 键。`kaj-labs.service` 仍为当前 worktree、`active/running`，live/ready 均 `200`。未执行真实 Provider、Git 交付、生产 migration、生产部署或真实邮件。

## 8. 答题与个人学习数据

### T16｜建立答题会话、回答、判分和快照

状态：已完成（2026-08-18）。

证据：新增 `QuizAttempt`、`QuizResponse`、`WrongQuestion` 快照模型与 `learning.0010_quiz_learning_facts`、`learning.0011_quiz_contract_completion`；兼容迁移拒绝无法解释的孤儿 attempt，按真实 bank/series/revision/owner 关系回填稳定 ID，隔离库完成 `0010 -> 0011 -> 0010 -> 0011`，回退时快照字段/新增索引约束归零，再前向读回一致。后端 service 覆盖题库公开状态门禁、revision 配置冲突、普通题库/错题练习启动、题型/题量/计时校验、随机顺序快照、选择题即时保存与 request 幂等、row version 冲突、严格客观判分、提交后简答自评、错题去重统计、完成数单次递增、并发提交行锁和重复提交幂等；queries 提供本人恢复详情、提交前隐藏答案、提交后安全答案投影和进行中分页。

聚焦 PostgreSQL 回归先发现并修复 `FOR UPDATE` nullable join、作者展示快照长度、简答自评时机和幂等版本顺序等问题，最终 T16 owner/并发/恢复回归 `3 passed in 92.22s`（另一个基础 T16 聚焦组 `3 passed in 82.43s`）；Ruff、Ruff format、Django check、migration drift、`git diff --check` 均退出 0。Labs 应用 0010/0011，读回迁移 leaf、四个快照 ID 字段、删除/结果约束和三张答题表 `0/0/0`；service 仍 `active/running`，live/ready `200`。T17 页面已在后续切片收口。

依赖：T09；Q008、Q017-Q020、Q033 已确认简答自评、多选严格匹配、题型筛选、随机设置、软计时和服务器自动保存/跨设备恢复。

结果：新增 QuizAttempt/Response、固定题库 revision、默认全选且至少一种的题型多选、默认 `true/true` 且可由用户修改的随机开关配置、题目 logical ID 顺序和每题选项顺序快照、默认不限时及用户启用后按固定分钟白名单创建的服务端软提醒阈值、超时后继续保存、选择题即时保存、简答防抖保存、版本冲突保护、跨设备恢复和幂等手动提交；单选/判断精确判分，多选按答案集合严格相等判分且不计部分分，简答题保存参考答案/评分要点快照与用户掌握自评；只允许本人读写。

验证：题型默认全选/至少一种/单种与多种/不存在类型、筛选后题数 1/全部/越界、配置过期冲突、普通与错题练习、两个随机 Switch 的四种组合、关闭时稳定顺序、开启时保存顺序、刷新/跨设备不重新随机、未计时/固定时长白名单、跨设备软阈值、超时后继续保存与提交、选择题即时保存、简答防抖/离开补存、刷新与跨设备恢复、并发版本冲突、自动保存不提前判分、重复/并发提交、四题型得分和题库隐藏后历史不漂移。

### T17｜交付顶部入口、答题配置、作答和结果页

状态：已完成（2026-08-18）。

当前进度（2026-08-18）：已新增登录态顶部答题入口、题库选择/配置页、attempt 作答页、单题保存、手动提交和提交结果/简答自评入口，复用 learning owner service/query 和现有 site header、Swiss 中性设计 token；访客 `/knowledge/quiz/` 安全跳转登录。修复自动保存协议闭环：AJAX 保存返回 `204`，透传 `X-Quiz-Response-Version` 与 `X-Quiz-Saved-At`，前端成功后更新隐藏版本并轮换 `request_id`，失败时保留答案并显示非阻塞错误。隔离 PostgreSQL HTTP 回归连续保存、陈旧版本、提交读回 `1 passed in 78.03s`；真实浏览器完成登录、入口点击、配置、开始答题、选择答案、保存、提交和结果读回，连续两次自动保存版本 `1→2→3` 且请求标识轮换，网络失败后答案仍保持选中并显示错误状态。1440/768/390 三视口 scroll width 分别读回 `1425/753/375`，控制台正常流为 `0 error / 0 warning`（模拟断网仅产生预期一条请求错误）；发现并修复移动端长作者 ID 将“进行中”挤成竖排和表单英文 label 两项问题。Labs 同源热更新后 `/knowledge/quiz/` 匿名返回 302，live/ready 仍为 200。

依赖：T12、T16。

结果：共享 Header 在工作机会旁增加登录态答题图标；所有登录用户均可完成题库选择、题型多选/题量/随机/计时配置、答题、带非阻塞状态反馈的自动保存/手动提交、跨设备恢复、软倒计时与超时提醒和结果页面，不要求附件能力，也不在访客 Header 显示入口。

验证：访客安全登录返回、登录用户真实答题持久化、浏览器后退/刷新、焦点与键盘、计时无布局跳动、手机按钮不挤压、三主题、无控制台/HTTP 异常；自动保存成功/重复/陈旧版本/网络失败均保留正确输入和可恢复状态。

T17 收口证据：服务层结果由 HTTP View 透传，重复 `request_id` 不会阻止后续新版本保存；聚焦 HTTP 回归 `1 passed in 78.03s`，T17 页面基础回归 `1 passed in 77.33s`。真实浏览器在隔离 PostgreSQL 上完成登录、题库配置、开始、选择、连续两次自动保存、提交、结果读回和断网失败保留；1440/768/390 三视口 `1425/753/375`，正常流控制台 `0 error / 0 warning`。Labs 同源 `active/running`，live/ready `200`，匿名 `/knowledge/quiz/` `302`，静态产物公网哈希与本地一致。

### T18｜建立错题本与答题记录管理

状态：已完成（2026-08-18）。

依赖：T16-T17；Q021 已确认错题掌握状态只由用户手动切换，Q022-Q022A 已确认记录管理动作以及记录删除不影响错题本，Q023-Q024 已确认题库管理、记录软删除、题库清理后历史快照和账户彻底清理。

结果：完成提交后幂等更新 WrongQuestion 的错误/正确统计但不自动修改掌握状态；按题库分组展示并复用答题配置；支持用户手动在 `TO_REVIEW`/`MASTERED` 间切换并按状态筛选；提供记录详情和筛选、owner-scoped 单删/复选批量删除/清空、精确数量确认，以及按 response 流式展开且防公式注入的 CSV 导出；记录删除不触发 WrongQuestion 重算或删除，题库清理后以自包含快照只读展示并禁用练习，账户彻底删除时清理本人学习数据并匿名化他人历史中的作者。

验证：同题多次错误不重复行、答对/答错不自动改变掌握状态、手动掌握/恢复及并发版本冲突、默认隐藏已掌握、错题练习上限、单删/当前筛选批量删除/清空的 owner 与数量边界、三种记录删除后错题统计与掌握状态不变、CSV 大小/编码/公式注入/个人数据隔离、题库隐藏/删除和并发批量操作。

证据：新增唯一 `apps.learning.queries.records` 与 `apps.learning.services.records` owner，复用 `QuizAttempt` 既有删除状态和版本字段，不新增平行记录模型。错题按题库分组，默认 `TO_REVIEW`，手动切换 `TO_REVIEW/MASTERED` 受 row version 保护；普通题库与错题练习共用配置入口，已删除题库的练习入口禁用。答题记录提供 owner-scoped 过滤/详情、单删、显式复选批量删除、清空全部、7 天冷静期恢复、到期安全 tombstone 和流式 UTF-8 CSV；CSV 对直接公式单元格加 `'`，数组答案以 JSON 单元格输出，删除记录不触碰 WrongQuestion。

聚焦真实 PostgreSQL 回归 `apps/learning/tests/test_quiz_records_t18.py` 为 `4 passed in 94.28s`；覆盖掌握手动事实、删除/恢复/到期清理、CSV 公式边界、空筛选导出和 owner HTTP 隔离。相关 Ruff、format、Django check、migration drift、CSS/JS build 与 `git diff --check` 均退出 0，无 schema migration。真实浏览器完成错题标记、记录筛选/详情/CSV、批量删除/冷静期恢复，1440 浅色、768 深色、390 护眼 page/body scroll width 为 `1425/753/375`，390 表格仅在局部容器滚动且页面无溢出。Labs 当前 worktree `active/running`，live/ready `200`，公网 `app.js/styles.css` SHA-256 与本地一致，匿名错题入口 `302`。账户终局清理与跨模块保留对账由 T20 统一收口，不在 T18 建立第二套删除流程。

## 9. 通知、可观测性与交付

### T19｜接入通用通知、审计和运维状态

状态：已完成（2026-08-18）。

依赖：T04、T07、T10、T13；Q029 已确认全部业务终态通知用户、系统最终失败额外通知管理员。

结果：对 T07/T10/T13 已接入的审核、生成、可见性和申诉事件做跨模块完整性审计，补齐 Markdown 安全模板、event/recipient/template 去重、已读与失效链接；调用/任务列表统一显示安全状态、耗时、token reservation/结算和计量，系统最终失败复用管理员提醒，不建立平行通知或 outbox。

验证：六类用户终态、申诉结果、可见性变更、完整/部分覆盖文案和计数、系统失败双收件人、事件/任务重复去重、收件人正确、已读、失效链接安全、正文/Prompt/题目答案/路径/密钥不进 payload、失败告警去重、TaskRun/业务运行/token ledger 可关联且不暴露模型原始输出。

证据：审计确认审核通过/拒绝/失败、生成完整/部分/失败、申诉结果和文档/题库管理变化全部进入现有 `apps.notifications.consumers.domain_events`，统一使用 `deliver_notification` 的 event/recipient/template 组合去重、回执完整性校验和 `consume_once`；内置模板继续通过统一 Markdown sanitizer，payload schema 拒绝正文、Prompt、答案、路径、token 等敏感字段。通知 query 新增题库/题库系列安全目标链接，隐藏/删除通知仍从可见查询排除；既有 target read service 保持按类型批量已读。

任务投影补齐 `duration_seconds`、AGENT `token_requested/token_settled/token_status` 和调用 `total_tokens`，不暴露原始输出或秘密；最终失败继续复用 `task.final_failed.v1` 管理员通知/告警链路，不建立平行 Outbox。聚焦 T19 `2 passed in 80.75s`，通知/目标已读/任务回归 `21 passed in 125.58s`；相关 Ruff、format、Django check 与 `git diff --check` 通过。

### T20｜容量、保留、清理与恢复

状态：已完成（2026-08-18）。

依赖：T05-T19；Q024-Q025、Q036A-Q036F 已确认生命周期、去重、业务配额、双层 token ledger 和重置语义。

结果：对 T02-T13 已建立的业务配额与双层 token ledger 做跨模块对账和恢复，补齐 usage/reservation 租约回收、自然日换窗、adjustment 审计、磁盘容量门禁和本人剩余摘要。实现审核失败/被拒文档 `30 天`清理、用户删除 `7 天`清理、源文档/题库/学习快照独立生命周期、API 缓存失效、账户彻底删除与他人历史匿名化，以及媒体资产 Saga/补偿；不把 Redis、缓存或 Task 状态当最终事实。

验证：跨模块全局继承/覆盖/权限撤销、业务与 token ledger 重算一致、并发预留/部分失败回滚、可信/缺失 usage、租约崩溃回收、上限降低、全站/单 Endpoint reset 对账、活跃 reservation 保留、重复 reset、价格缺失、自建 Endpoint、剩余摘要隔离、自然日切换、到期扫描小批量/skip locked、文件 Saga、任务重复、删除/申诉暂停竞态、Redis 丢失、磁盘容量门禁、源文档/题库/答题/错题快照引用、账户删除匿名化和失败补偿。

证据：新增 `apps.learning.services.cleanup` 统一有界清理编排：文档 7 天删除/30 天失败材料、题库冷静期后先切 `DELETED` 再清理不可变 revision/question、答题记录冷静期 tombstone、学习模型预留到期、AGENT token 预留恢复均委托既有 owner；媒体删除继续复用 `release_target_assets`/Filesystem Saga，容量门禁继续复用 operations 采样而不把缓存当事实。账户删除在 Account 行删除前调用唯一 `purge_account_learning_data`，清理本人文档/题库/答题/错题/配额并将其他用户历史作者快照匿名化。新增每小时幂等 `apps.learning.cleanup_expired_learning` Celery 入口并纳入 Beat。

聚焦真实 PostgreSQL 回归 `apps/learning/tests/test_cleanup_t20.py` 为 `4 passed in 90.96s`；覆盖题库到期快照、账户终局清理、空批次幂等和账户删除集成。相关 Ruff、format、Django check、migration drift 通过；未新增 schema migration，未执行 Labs/生产数据清理、真实 Provider 或 Git 交付。

### T21｜跨模块回归、Labs 验收与发布准备

状态：已完成（2026-08-18）。

依赖：T01-T20 全部完成。

结果：完成跨模块回归、迁移漂移检查、静态构建与 Labs 运行态验收；更新架构、运维、公告和增量部署清单。真实 Provider、生产迁移、备份和 Git 交付仍按授权边界留待单独发布回合。

验证：隔离 PostgreSQL/Redis/Mailpit 跨模块回归 `156 passed in 631.58s (0:10:31)`；覆盖 `apps/learning/tests`、`apps/notifications/tests`、TaskRun 与 capacity 回归。另完成 migration drift、Ruff、format、Django check、前端构建、`git diff --check`、390/768/1440 三主题键盘/焦点证据和 Labs health/受影响路径读回。真实模型 smoke、生产备份/迁移、Git 提交推送和生产部署未执行。

## 10. 需求与裁决覆盖矩阵

| 范围 | 已确认口径 | 实现 Todo | 最终证据 |
| --- | --- | --- | --- |
| Q001、Q006-Q008、Q011 | 附件权限、原文归属、自动审核、账户入口、简答自评 | T01、T05-T08、T16-T19 | 权限矩阵、隔离数据、审核终态、真实入口与答题结果 |
| Q002-Q005、Q038A-Q038B | 多 Endpoint、秘密别名、三 Provider、2 MiB 分块、管理员运行参数 | T01-T05 | Endpoint migration、假 Provider、SSRF/预算/参数边界、管理员 UI |
| Q009-Q010、Q027-Q028、Q034-Q035、Q039 | 匿名只读 API、答案范围、独立 JSON transport、CORS、关闭响应、分页、限流与故障 | T12、T14-T15、T19 | HTML/API 等价、OpenAPI、429/503、CORS/缓存/Redis 故障 |
| Q012-Q017、Q023-Q025 | 多题库/两卷、题型/题量、修订、独立标签、owner 管理、生命周期、去重 | T06、T09-T13、T20 | schema/coverage、不可变 revision、状态与清理读回 |
| Q018-Q022、Q033 | 随机设置、软计时、自动保存、多选判分、手动掌握、记录管理、题型筛选 | T16-T18、T20 | 跨设备 attempt、判分/错题、删除独立、CSV 与浏览器流 |
| Q024A-Q024D、Q031-Q032、Q037 | 7 天删除、30 天失败材料、快照/账户清理、申诉、原文访问历史、显式批量 | T06-T10、T13、T18-T21 | 清理 Saga、申诉竞态、匿名化、审计与批量逐项结果 |
| Q026A-Q026B | 最新默认、可切换排序、组合筛选与模糊搜索 | T12、T14 | 稳定分页、HTML/API filter DTO 等价、浏览器筛选 |
| Q029-Q030 | 全部终态通知、系统失败管理员提醒、逐上传授权声明 | T07-T13、T19 | Outbox 去重、收件人/脱敏、声明版本读回 |
| Q036A-Q036F | 全局默认/账户覆盖、业务配额、双层 token ledger、硬范围和重置 | T02-T07、T09-T13、T19-T21 | 并发预留/结算/重置/自然日/恢复与权限撤销 |
| 原始六项总体验收 | AGENT 配置、Prompt、知识文档、题库/API、答题/错题/记录完整可用 | T01-T21 | T21 的迁移、回归、Labs 浏览器与健康证据 |

## 11. 当前停止点

规划文档已经建立，Q001-Q039 及全部 A-F 子项已确认，T00-T12 已完成，当前仅 T13 进行中。T12 的唯一公开 query/filter projection、独立 HTML 列表/详情、组合筛选与模糊搜索、稳定排序/分页、答案范围、隐藏 404、迁移往返、三主题三视口键盘浏览器和 Labs migration/静态/健康读回均已闭合。下一步按 T13 在“智能与题库”一级组交付 LearningQuotaPolicy 与账户覆盖、文档/题库状态和申诉队列、原文访问审计，以及只接受显式勾选 ID 的有界批量处置；先审计现有 administration 分页/dialog、learning owner service/query、Audit/Outbox 与通知复用点，再以管理员权限、row version、申诉和批量预检的聚焦 RED 固定边界。当前 Goal 持续授权继续适用；不执行无必要的真实 Provider、Git 或生产动作。
