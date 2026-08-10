# Kaj 富文本增强最终 Goal Prompt

来源：

- [语雀式富文本编辑能力规划](yuque-inspired-feature-plan.md)
- [富文本增强实施 Todo List](implementation-todolist.md)
- `docs/planning/implementation-readiness.md`

用途：在用户明确要求开始实现后，将下方提示词作为这个增强项目的唯一主 Goal。它覆盖 R0-R5 共 29 条 Todo，不为单条任务建立新的 Goal，不在本文件维护第二份进度。

## 可直接使用的最终提示词

```text
你正在 `/home/code/personal-blog` 实施 Kaj 的富文本编辑器增强项目。

Goal：在不破坏现有 Markdown、旧 TipTap 文章、ArticleRevision、草稿、冲突、版本、媒体和发布链路的前提下，按 `docs/planning/rich-editor/implementation-todolist.md` 依次完成 R0-R5 共 29 条 Todo，交付基于现有 TipTap 3 的安全 block 富文本编辑体验。完成时，所有新增 node/mark 必须在编辑、预览、保存、发布、历史版本、公开查看、搜索摘要和导出中语义一致；29 条 Todo 全部具有当前代码状态下的新鲜测试、持久化/文件读回和适用的真实浏览器证据。

范围内：
- R0：schema version、node/mark/attrs 契约、规范化、renderer/sanitizer、错误合同、command registry 和工具栏骨架。
- R1：段落、H1-H6、下划线、行内代码、安全链接、清除格式、Markdown 输入规则、快捷键和选区浮动工具条。
- R2：可搜索 Slash Menu、block handle、上下文菜单、稳定拖拽、任务列表、提示块、分隔线、代码语言/复制和 block 历史语义。
- R3：基础表格、表格安全约束、图片 block、附件卡片及统一上传 pending/progress/error/cancel/retry 生命周期。
- R4：标题大纲、稳定锚点、编辑/预览定位、可信来源嵌入和全部阅读/导出出口一致性。
- R5：block 变更摘要、草稿/冲突/版本/媒体闭环、粘贴/导入导出、性能容量门禁和跨层回归。

阶段任务（状态和决定性证据只回写 Todo 文件）：
R0：
- [ ] RE-001 固化节点、Mark 与属性契约
- [ ] RE-002 实现 schema version 与规范化序列化
- [ ] RE-003 对齐 renderer、sanitizer 与错误合同
- [ ] RE-004 建立 schema 兼容与安全回归基线
- [ ] RE-005 重构 command registry 与响应式工具栏骨架
R1：
- [ ] RE-101 扩展段落、H1-H6 与文字 Mark
- [ ] RE-102 实现安全链接编辑与移除
- [ ] RE-103 实现 Markdown 输入规则与键盘快捷键
- [ ] RE-104 实现选区浮动工具条
R2：
- [ ] RE-201 实现可搜索 Slash Menu
- [ ] RE-202 实现 block handle 与上下文菜单
- [ ] RE-203 实现稳定的 block 拖拽排序
- [ ] RE-204 实现任务列表、提示块与分隔线
- [ ] RE-205 增强代码块语言与复制能力
- [ ] RE-206 闭合 block 光标、事务与历史行为
R3：
- [ ] RE-301 实现基础表格编辑
- [ ] RE-302 建立表格约束与安全渲染
- [ ] RE-303 完善图片 block 工作流
- [ ] RE-304 实现附件卡片 block
- [ ] RE-305 统一上传临时状态与清理语义
R4：
- [ ] RE-401 实现标题大纲与稳定锚点
- [ ] RE-402 对齐编辑光标、预览和大纲定位
- [ ] RE-403 实现可信来源嵌入卡片
- [ ] RE-404 统一全部阅读与导出出口
R5：
- [ ] RE-501 实现 block 级复制、删除与变更摘要
- [ ] RE-502 闭合草稿、冲突、版本恢复与媒体生命周期
- [ ] RE-503 补齐粘贴、导入和导出语义
- [ ] RE-504 建立性能、容量与可观测性门禁
- [ ] RE-505 完成跨层回归与 Labs 候选验收

范围外：
- 实时多人协作、多人光标、AI 续写/改写、白板、思维导图、复杂数据库块、任意第三方插件、任意 iframe 和服务端无界抓取。
- 未经当前回合明确授权的 Git add/commit/push/merge、生产 migration、部署、服务重启、真实邮件、生产数据修改和不可逆清理。
- 将 TipTap JSON 改为任意 HTML，或新建第二套正文、revision、媒体、附件、权限、渲染、缓存和错误事实中心。

启动前必须：
1. 完整读取根 `AGENTS.md`、所有适用的 `/root/.codex/development-rules/` 规则、项目 README、富文本 feature plan、Todo、implementation-readiness、相关架构 owner/合同和页面状态矩阵。
2. 重新核对当前分支、远端默认分支、工作区、用户改动、Labs WorkingDirectory/服务状态、依赖锁文件、当前编辑器/renderer/sanitizer/Revision/media 调用链和相关测试；不得依赖旧摘要替代当前事实。
3. 遵守 Git 安全任务分支前置要求；保留所有非本任务改动。没有当前回合 Git 授权时只保留工作区修改，不提交、不推送。
4. 核验 29 个 ID 唯一、前置存在、依赖无环、阶段无反向边；任何时刻只把一条 Todo 设为 `进行中`。
5. 在引入或升级 TipTap 扩展前，核对现有依赖、锁文件、许可证、维护状态、包体积和服务端 schema 对应关系；没有必要不得新增大型依赖。
6. 若 schema version 需要 migration、共享数据变更或运行时迁移，先完成 expand/migrate/contract 设计，并在执行 migration 前取得当前回合明确授权。
7. 所有测试使用隔离 PostgreSQL、Redis、临时媒体和 Mailpit；不得连接生产数据库、正式媒体或共享数据。
8. 遵守低内存资源门禁：重型操作串行、单 worker，每个重型阶段前读取 MemAvailable/Swap 状态，Playwright 只使用 `/usr/local/bin/blog-playwright-cli`。

固定执行协议：
1. 严格按 R0 -> R5 和 Todo 前置顺序执行；每次只推进一个可观察行为闭环，不同时把多条任务标为进行中。
2. 每条任务先读取来源、调用方和复用点，明确 `reuse/extend/extract/new/review`；稳定能力只能有一个 owner。
3. 有意义的行为变更执行聚焦 RED，确认失败原因准确；然后实现最小但完整的产品行为，运行 GREEN 和相关回归。
4. 每增加一个 node/mark/attr，必须在同一切片内闭合：TipTap schema、JSON 规范化、command active/disabled、服务端校验、renderer、sanitizer、错误码、缓存版本、历史兼容和所有适用出口。
5. View、模板、前端菜单和 Task 只调用 owner 的稳定入口，不复制正文、权限、媒体、附件、revision、渲染或清理规则。
6. 预览与发布使用同一服务端 renderer/sanitizer；新节点未获服务端支持时阻断保存并返回明确 422，禁止静默删除、旧预览或假成功。
7. 媒体只保存并解析合法 `media:<ULID>`；图片和附件复用现有权限、归属、格式、大小、引用和清理语义。临时上传节点不得进入 revision。
8. 错误、日志、审计、通知、指标和截图不得包含正文、剪贴板原文、验证码、token、Cookie、连接串、原路径、带凭据 URL 或个人数据。
9. 前端保持现有本地化视觉语言：工具栏安静紧凑、按钮尺寸稳定、图标明确、无按钮挤压、无页面级横向溢出、无浮层遮挡。不要复制语雀商标、视觉资产或闭源实现。
10. 每完成一条 Todo，立即在 Todo 卡中回写状态、修改文件、RED/GREEN/回归命令和退出码、通过数、数据/文件/缓存读回、浏览器证据、未执行项和残余风险，再开始下一条。
11. 每个通过聚焦验证的运行时修改切片按项目规则定向同步 Labs：先读回 `kaj-labs.service` 的 WorkingDirectory/ActiveState/SubState，只同步本任务运行时文件及构建产物，保留目标无关改动，不同步 `.git`、环境、数据库、媒体、日志或凭据；同步后验证 active/running、`/health/live` 200 和直接受影响页面/安全用户流。
12. Labs 同步不扩大为容器重建、重启、迁移、数据修复或生产发布；这些动作仍需当前回合明确授权。

每条 Todo 的最低证据：
- static_guard：目标 Ruff/格式、Django check、migration drift（涉及模型时）和前端 build，均记录命令与退出码。
- logic_guard：准确 RED -> GREEN，覆盖正常、空、非法、超限、无权、冲突、撤销/恢复及与该任务直接相关的安全路径。
- data_guard：通过真实 owner 入口保存并从隔离 PostgreSQL 读回 revision JSON/schema version；涉及媒体时同时读回文件、引用和清理结果；缓存/任务适用时读回最终状态。
- customer_flow_guard：通过 `blog-playwright-cli` 执行真实编辑、保存、预览、发布/查看或恢复流程，不以 DOM 存在、静态截图或 mock 替代点击和持久化读回。
- visual/a11y：串行覆盖 390、768（适用时）、1440、三主题、键盘、焦点、Escape、触控目标、reduced-motion，以及默认、展开、上传中、失败、无权、空内容、长标题、长代码和宽表格状态。
- operational_guard：Labs 同步切片读回服务状态、live health 和直接受影响安全流；未授权的生产动作明确列为未执行。

阶段退出门禁：
- R0：旧 Markdown/旧 TipTap 文章可继续读写；未知 node/mark、非法 attrs、危险链接、越权媒体和超限文档明确拒绝；command registry 是所有工具入口唯一命令来源。
- R1：所有文字格式跨编辑、预览、保存、发布、历史和公开查看一致；链接协议与外链安全不可绕过；浮动工具条不丢 selection。
- R2：Slash、block handle、菜单和拖拽可用鼠标、键盘和触控完成；拖拽无 placeholder 闪烁/位置争夺；block 操作可撤销且不丢正文或光标。
- R3：表格受限且不撑破页面；图片/附件有完整权限、上传、引用、替换、删除、失败和清理闭环；UI 成功与数据库/文件事实一致。
- R4：大纲和预览定位无顶部空白或输入时页面滚动；可信嵌入不能绕过 allowlist/CSP；所有阅读/导出出口共享同一语义 owner。
- R5：本地/云草稿、409 冲突、版本恢复、发布、粘贴、导入导出和媒体生命周期通过跨层回归；性能与容量有明确上限；无正文泄露指标。

最终成功标准：
- `docs/planning/rich-editor/implementation-todolist.md` 的 29 条 Todo 全部为 `完成`，没有 `进行中`、`待处理` 或未解释的 `阻塞`。
- 29 个任务均有当前最终代码状态下的新鲜决定性证据；临时 RED 测试或探针按项目规则清理，已有受跟踪测试不得擅自删除。
- 旧 Markdown、旧 TipTap、新富文本节点在编辑、预览、保存、发布、历史版本、公开查看、搜索摘要和导出中均满足各自兼容合同。
- 未发现正文丢失、XSS、权限绕过、未知节点静默丢弃、媒体误删、假上传成功、预览/发布分叉、页面级横向溢出或浮层焦点陷阱。
- 390/768/1440、三主题、键盘/焦点和关键错误/恢复状态的真实浏览器矩阵通过，受影响 Labs 安全用户流通过且服务保持 active/running、live health 200。
- 完成报告列出完成/阻塞 ID、修改文件、关键架构决定、每类验证命令/退出码/通过数、数据和文件读回、Labs 读回、未授权未执行项、残余风险和推荐交付步骤。

立即停止并请求决策的条件：
- 规划、真实代码和更高优先级需求对 schema、正文格式、revision、媒体或权限存在会改变结果的冲突。
- 需要生产/共享数据 migration、不可逆历史 revision 改写、生产媒体清理、外部付费服务或新的敏感数据采集，但当前回合没有明确授权。
- renderer/sanitizer、content revision 或 media lifecycle 出现第二实现中心且不能安全合并到现有 owner。
- 发现秘密或正文进入日志/通知/审计/指标，发现 XSS、越权、正文丢失、媒体误删，或旧文章不能安全兼容。
- 同一行为连续三次独立修复仍失败，或资源门禁进入橙色/红色且无法安全恢复。

不得仅因完成代码或局部测试就宣称 Goal 完成。只有 29 条 Todo 和上述最终成功标准全部满足，且所有未执行动作被准确说明后，才可以结束 Goal；Goal 完成不自动授权 Git 交付或生产发布。
```

## 使用说明

1. 只有用户明确要求开始富文本增强实施时才启动这个 Goal；本提示词本身不授权实现或外部写操作。
2. Goal objective 应使用提示词首段的单一 `Goal` 句，不设置 token budget，除非用户明确指定。
3. 一个 Goal 覆盖全部 29 条 Todo；会话计划可以拆步骤，但不得为每条 Todo 创建第二套永久目标或状态账本。
4. 如果用户只授权首期 R0-R2，应从本提示词裁剪范围与最终成功标准后创建独立首期 Goal，不能把 R3-R5 伪标为完成。
