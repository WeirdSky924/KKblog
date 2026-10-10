# AGENT 知识题库与答题系统详细设计

状态：需求裁决与设计规划完成；实施进度只见 [实施 Todo](./implementation-todolist.md)。Q001-Q039 及全部 A-F 子项已经确认，最终口径以 [需求裁决记录](./requirements-interview.md) 为准。

## 1. 目标与成功条件

建立一条从“安全配置模型”到“上传知识文档、审核、生成题库、公开检索、外部读取、登录答题、错题复习和记录管理”的完整链路。

成功不是页面上出现按钮，而是同时满足：

1. 模型端点、Prompt、凭据和调用记录有唯一 owner，其他模块只按稳定 AGENT ID 调用。
2. 未授权用户不能上传；不合格文档不会进入已通过文档库；失败不会伪装成成功。
3. 题目可由服务端确定性解析、校验、判分并长期读回，历史答题不会因题库后来变化而漂移。
4. 公开浏览、登录答题、个人记录、管理员配置和外部 API 各自有服务端权限边界。
5. 模型调用有超时、大小、并发、费用、重试、取消、脱敏和可观测性上限。

## 2. 现状与复用结论

| 能力 | 当前 owner | 本轮策略 |
| --- | --- | --- |
| 账户、作者角色、附件能力 | `apps/accounts` | `reuse/extend`；不在 learning 内复制权限字段 |
| Markdown 文件探测、暂存、绑定、清理 | `apps/media` | `extend` 新增知识文档用途与 access port；只接受 UTF-8 `.md` |
| Markdown 安全渲染 | `apps/media/rendering` | `reuse`；Prompt 预览、知识文档预览和题目正文共用 sanitizer |
| 标签 | `apps/content` 拥有文章标签；`apps/learning` 拥有题库标签 | 两套标签目录独立；不跨域共享审核、删除、统计或使用计数 |
| 异步任务、租约、重试、错误 | `apps/operations` | `reuse` TaskRun 与 RuntimeError，不建立独立任务表替代它 |
| 通知 | `apps/notifications` | `reuse` 通用事件模板与回执，不直接拼通知行 |
| 审计与 Outbox | `apps/operations`、`apps/core` | `reuse`；管理员配置和状态操作必须审计，提交后派发副作用 |
| 管理页面 | `apps/administration` | 只编排；AI 配置一级组承载共用 Endpoint/AGENT/Prompt，智能与题库一级组承载 learning 管理入口 |
| 顶部入口与站点壳 | 共享 navigation template | `extend` 一个登录态答题快捷入口，不创建第二个 Header |

当前项目没有模型/AGENT 调用中心，也没有公共 JSON API。二者都是本轮新增稳定边界。

## 3. 领域与依赖方向

### 3.1 `apps/agents`

唯一负责：

- 模型端点配置、端点启停和连通性检查；
- AGENT 身份、用途、所选端点和唯一当前 Prompt；
- Prompt 不可变修订、当前指针和回滚；
- 统一请求 DTO、结构化响应、超时、重试与提供商适配；
- 调用运行、用量、耗时和安全错误码；
- 输出 JSON Schema 校验和禁止工具调用。

它不知道知识文档、题库或答案的业务表，只接收调用方提供的受限输入和 schema，并返回已校验的结构化结果。

### 3.2 `apps/learning`

唯一负责：

- 知识文档提交、审核结论和已通过文档库；
- 题库生成请求、题库、题目和题库标签；
- 题库公开查询、搜索、筛选和版本化只读 API；
- 答题会话、答案、计时、判分、错题本和个人记录；
- 该领域的权限、状态、事件、幂等和保留策略。

它只能通过 `apps.agents.public` 使用 AGENT，通过 `apps.media.public` 使用文件，通过通用事件接入通知和运维。

### 3.3 页面层

- `apps/administration`：AGENT、Prompt、知识文档、题库与 API 开关管理。
- `apps/learning.presentation`：公开题库页、登录答题页、错题本、答题记录和 API View。
- View、Template、Task 不直接访问另一 owner 的私有模型。

## 4. AGENT 配置模块

### 4.1 建议数据结构

已确认采用多 Endpoint 模式：管理员可以维护多个 Endpoint；每个 AGENT profile 选择一个 Endpoint；同一 Endpoint 可以被多个 AGENT 复用。审核与题库生成因此可以选择不同模型，也可以按需共享同一模型配置。

`AgentEndpoint`：显示名称、协议、规范化 Base URL、模型名、服务器秘密引用别名或加密 API Key、启用状态、超时、最大输入/输出预算、单业务运行 token 预算、Endpoint 每日 token 上限、并发上限、可空价格估算元数据、row version、创建/更新时间。数据库只保存 API Key 密文，不保存明文。

上下文窗口、单次输出上限、单业务运行 token 预算、总请求超时和并发上限均由管理员在每个 Endpoint 的新增/编辑表单中显式配置，保存时使用同一运行参数 schema 和交叉校验。默认/硬范围分别为：context `131072` / `4096..2000000`，max output `8192` / `256..131072`，per-run token `500000` / `10000..5000000`，timeout `120` / `10..1800` 秒，concurrency `1` / `1..5`。默认值只用于新建初值，不锁死配置；管理员可在范围内逐项修改。同时要求 max_output < context、每次估算 input + max_output <= context、per_run >= max_output 且 per_run <= endpoint_daily。系统不维护按模型名自动变化的能力表，也不调用 Provider 探测后覆盖管理员值；连通性检查只产生独立检查结果。每次 invocation 固化 Endpoint row version 与全部运行参数，后续编辑不改变在途运行；Gateway 调用前对快照再防御性校验。

`AgentProfile`：稳定 key、显示名称、用途、endpoint ID、当前 Prompt revision ID、启用状态、结构化输出 schema key、row version。

`AgentPromptRevision`：profile ID、递增版本、Markdown source、内容摘要、创建管理员、创建时间。一个 profile 只有一个当前指针，但历史修订不可变，以便回放和审计。

`AgentInvocation`：profile/prompt/endpoint/model 快照、调用方类型和稳定目标 ID、幂等键、状态、输入/输出摘要、token/费用计量（提供商返回时）、耗时、安全错误码、TaskRun 引用。禁止保存知识正文、完整 Prompt 组装结果、模型原始响应、密钥或 Authorization Header。

### 4.2 首版 Provider 与协议

- 已确认首版支持 GPT、Claude、DeepSeek 三类 Provider。GPT 与 DeepSeek 使用各自 Base URL 下的 OpenAI-compatible structured chat/completions adapter；Claude 使用 Anthropic Messages adapter。上层只消费统一的结构化请求/响应 port，不按业务模块分叉 Provider 逻辑。
- Base URL 只保存 scheme/host/port/path 前缀，不允许用户名、密码、query、fragment 或控制字符。
- Endpoint 支持“无需认证”、服务器秘密别名和管理员录入的自定义 API Key 三种认证模式。自定义 API Key 只以服务端加密密文保存，管理页面编辑时不回显；空提交保持原值，显式清除才删除。调用和连接检查使用加密凭据快照，明文不进入数据库、审计、错误、通知、日志或 DTO。服务器秘密别名仍从 `KAJ_AGENT_SECRET_*` 专用注册项解析，不能通过任意环境变量名读取。
- 每个业务用途绑定稳定 profile，例如 `knowledge-review` 和 `question-generation`；业务代码不硬编码具体 Base URL 或模型。
- 已确认 Endpoint、Model、AGENT 和 Prompt 只由管理员配置。有附件能力的用户不选择 Provider、不填写认证信息，也不能覆盖 Prompt；上传审核和题库生成 service 按稳定用途解析管理员启用的 profile 后直接执行。缺少可用 profile 时诚实显示功能暂不可用，不回退到任意模型。
- 连通性检查是管理员显式动作，使用最小请求、明确费用提示和独立频率限制；检查成功不等于业务 schema 可用。

### 4.3 Prompt 编辑

- 管理界面延续现有 Markdown 多行编辑与安全预览，不引入另一套编辑器。
- 保存生成新修订并原子切换当前指针；并发编辑使用 row version 返回 409，不后写覆盖前写。
- Prompt 可以声明输入占位符，但变量必须来自注册表；未知变量保存失败，不能运行时猜测。
- Prompt 只定义业务指令。系统级安全约束、数据分隔、禁止执行文档内指令和 JSON Schema 由运行时强制包裹，管理员 Prompt 不能覆盖。

### 4.4 外部调用安全

- Base URL 必须通过 SSRF 策略：解析后地址复核、重定向限制、响应体上限、连接/读取总超时和 DNS rebinding 防护。
- 已确认公网 Endpoint 默认只允许 HTTPS。loopback 或内网自建端点必须先在服务器 `.env` allowlist 中登记，登记后才允许 HTTP；云元数据、链路本地等保留地址始终拒绝。自签名 TLS 不由普通 Endpoint 表单关闭证书校验，后续确有需要时再设计受控 CA 配置。
- 不向模型发送账户邮箱、IP、Cookie、token、服务器路径或不必要的对象信息。
- 模型输出始终是不可信输入：先限制字节，再 JSON 解析，再 schema/业务约束校验，最后才写业务表。
- 旧版规划中的“一次 schema 修复请求”只描述了当前基线，不再作为目标实现；结构化输出目标以 [ADR-008 Agent 结构化输出 Harness](../../architecture/adr/ADR-008-agent-structured-output-harness.md) 为准，采用 Provider/Tool strategy、Envelope 提取、四段校验和有界阶段状态机。

## 5. 知识文档提交与审核

### 5.1 权限与入口

- 已确认：只允许“有附件权限”的登录用户上传 Markdown。
- 已确认：这里直接复用现有 `attachment_upload_enabled`，不新建知识文档专用权限；因此目标账户必须仍有作者角色，服务端在上传和提交审核时都要复核。撤销作者角色时沿用现有账户服务同步撤销附件能力。
- 已确认附件能力同时门禁知识文档上传、文档整理写操作和文档转题库；三类 service 在执行时都重新检查当前 capability。仅浏览公开题库和登录答题不要求该能力。
- 有附件能力的用户直接使用管理员已经配置并启用的审核/生成 AGENT，不获得 Endpoint、Model、Prompt 或密钥的读取和选择权限。
- 已确认在现有右上角账户浮窗中增加“知识文档”菜单项，仅对当前有附件能力的用户显示；点击进入独立“我的知识文档”页面。上传、整理和转题库在独立页面完成，账户浮窗只负责导航，不内嵌复杂表单。
- 管理员不获得代替他人上传的例外；管理员若自己具备相同能力，可作为本人上传。

### 5.2 文件与事实

- `media` 新增 `KNOWLEDGE_DOCUMENT` purpose，只接受扩展名和探测内容均为 UTF-8 Markdown；拒绝 NUL、无效 UTF-8、路径和伪装格式。
- 已确认知识 Markdown 最大 `2 MiB`。系统按 Markdown 标题、列表和段落边界自动分块；Endpoint 配置上下文窗口和单次业务任务总 token 预算。上传后、首次模型调用前使用保守 token 估算完成全量预检，整份文档超过总预算则拒绝，不发送部分内容。
- `KnowledgeDocument` 保存 owner、媒体绑定、原始文件名的安全显示值、标题、摘要、SHA-256、字符/行/token 估算、状态、审核运行和时间戳。
- 原始字节由 media 保存；用于审核/生成的规范化文本由 learning 通过授权读取，不复制到日志或事件。
- 内容摘要采用通过 UTF-8/控制字符门禁后的保守规范化字节：去除允许的 UTF-8 BOM，并只把 `CRLF/CR` 统一为 `LF`；不裁剪空白、不做 Unicode 兼容折叠，避免改变代码块或知识语义。数据库对同一 owner 的未清理 `content_sha256` 建立条件唯一约束，service 在写入前查询并以约束处理并发竞态。
- 同一账户命中未清理文档时不创建新对象、不重复审核：有效状态跳转原记录，`DELETE_PENDING` 提示恢复，`REJECTED/REVIEW_FAILED` 提示查看原因或重试。`CONTENT_PURGED/DELETED` 不再占用摘要，可重新上传。查询严格限定 owner；不同账户允许相同内容并各自建立文档、审核和媒体绑定，不能通过错误文案、对象 ID 或可观察 API 暴露跨账户碰撞。
- 上传表单每次显示默认未勾选的版本化授权声明，说明用户确认有权上传、允许内容由站点配置的模型服务处理、衍生题库/答案/解析将公开，并承诺不上传无权处理的隐私、机密或侵权内容。提交 DTO 必须带当前 statement version 和显式 `accepted=true`；服务端验证后在 KnowledgeDocument 保存声明版本、确认时间和确认账户，不接受仅由前端默认补齐。声明版本更新只约束新上传，不追溯篡改既有文档事实。
- `LearningAppeal` 由 learning 独占，关联 KnowledgeDocument 或 QuestionBank，保存 appellant、目标处置版本、Markdown 理由的安全渲染、`PENDING/APPROVED/REJECTED/WITHDRAWN` 状态、管理员决定摘要、row version 和时间。条件唯一约束保证每个对象同时至多一条 `PENDING`；用户可撤回，已决后可按频率限制再次申诉，不能覆盖历史。
- 允许申诉 `REJECTED` 文档及管理员强制隐藏/删除的文档或题库，不允许用申诉绕过 owner 自己的删除、附件权限或管理员锁。文档申诉批准只创建新的审核运行，读取当前启用 AGENT/Prompt 并重新经过全部确定性门禁；管理员不能直接把文档改为 `APPROVED`。管理处置申诉批准由管理员在同一决定事务中显式恢复目标状态。针对待清理的管理员删除，`PENDING` 申诉暂停最终 purge，驳回后从原剩余期限继续。
- 申诉创建、撤回和决定走 owner service、CSRF、对象归属、状态/版本校验与现有 Outbox。结果通过通用通知中心告知 appellant；事件和通知不包含申诉 Markdown、文档正文或题目内容。管理员使用安全多行 Markdown 查看理由和填写决定摘要，不能在单行输入中截断。
- 已确认原始知识文档只允许上传者和管理员查看全文，只有上传者可以用自己的 APPROVED 文档生成题库；其他用户和访客不能查看或下载原始 Markdown。源文档与已生成题库是独立生命周期：删除源文档只清理原文和生成入口，不隐藏或删除已经发布的题库；题库保留无正文的来源对象 ID/owner 快照用于追溯。重复上传遵循上述账户内摘要去重规则。
- 管理员正文访问必须走 learning 的授权详情 query，列表和搜索不批量加载正文。每次成功返回原文时写不可变 `KnowledgeDocumentAccess` 事件，保存 document、administrator actor、用途枚举、时间和安全 request correlation ID，不保存正文、摘要片段或原始路径；失败授权和列表预取不能伪装成成功读取。
- 上传者在文档详情看到访问时间与用途（审核、申诉、管理处置等），不显示管理员身份且不发送实时通知。具体 actor 只在管理员审计权限下可见。访问历史 owner query 分页、有界且仅限本人文档；账户彻底删除时按 Q024D 清理可识别关联。

### 5.3 状态机

```text
STAGED -> REVIEW_PENDING -> REVIEWING -> APPROVED
                                  |-> REJECTED
                                  |-> REVIEW_FAILED
STAGED/REJECTED/REVIEW_FAILED -> DELETED
```

- 上传成功只代表文件通过确定性校验，不显示“知识文档已保存”。
- 创建提交记录与绑定资产在同一事务内完成；提交后派发审核任务。
- 审核 AGENT 至少输出 `verdict`、稳定原因码、可显示摘要和风险类别。自由文本理由不进入日志/通知 payload。
- `APPROVED` 才进入可供生成选择的文档库。`REJECTED` 显示安全、可操作原因；`REVIEW_FAILED` 表示系统失败，可通过新业务动作重新审核。
- 已确认审核 AGENT 的通过结论在确定性门禁和全量分块汇总均成功后直接写入 `APPROVED`，不再进入管理员发布前审核队列。管理员保留事后查看、隐藏和删除的管理能力。
- `REJECTED` 与最终 `REVIEW_FAILED` 的原始文档、可显示失败详情和受控重试材料自终态起保留 `30 天`。期间可重试或进入用户主动删除流程；到期后转为不可重试的内容已清理状态，解除 media 绑定并只保留无正文 tombstone（稳定对象 ID、owner、终态、原因码和时间）。
- 用户主动删除进入统一 `7 天`软删除期：对象保存删除前状态、`deletion_requested_at` 和 `purge_after`，立即退出正常列表与业务选择，期间 owner 可撤销。期满后由有界清理任务调用 owner service 和 media 解绑/清理状态机，不由 Celery Task 直接删任意路径。

### 5.4 审核双层门禁

确定性门禁先检查编码、大小、空文档、极端重复、控制字符、Markdown 结构上限和危险链接表示；AGENT 再判断是否包含可提炼知识、是否明显为垃圾/指令注入/违法或不适合公开。AGENT 通过不能放宽确定性门禁。

文档正文必须作为明确分隔的“不可信资料”传入；文档内要求泄露 Prompt、改变角色、调用工具或访问链接的文字一律只作为被审内容。

审核任务必须覆盖全部分块并生成一次全局汇总结论；任一分块命中拒绝条件，整份文档进入 REJECTED。题库生成同样处理全部分块，再执行跨分块重复题消除和整库 schema 校验，不能把预算耗尽前的部分结果发布为完整题库。

## 6. 题库生成

### 6.1 生成入口

用户只能从本人 `APPROVED` 文档发起生成，填写必填基础标题和可选简介，再勾选单选、多选、判断、简答 Switch；至少选择一种，不填写题量。管理员可以查看文档全文但不能代替上传者发起生成。已确认同一文档可以按不同配置生成多个独立题库；初次结果和后续修正都通过不可变修订保存。

生成流水线对所有文档使用同一规则：先由 learning 按标题/编号/列表等可观察结构拆成有序源知识单元；没有结构时按段落和安全大小切分。源知识单元只是受限证据片段，不等于知识点，也不规定题目数量。AGENT 不预先知道文档是否有序，只把检测到的结构作为降低理解成本的线索，并自行判断每个批次内有多少个可考的原子知识点；一个知识点可以由多个源单元共同支撑，一个源单元也可以支撑多个知识点，输出必须在 `source_unit_ids` 中保留证据引用。每道题必须有且只有一个主要考查知识点，题干可以引用零个或多个辅助知识点；题目数量是上限而不是目标。服务端按固定且可验证的批次计划逐批调用，批次通过统一输出校验后立即保存 checkpoint；重试时跳过已成功批次，从第一个未完成批次继续，全部批次完成后才合并、去重、重新编号和组卷并原子发布，不能发布半成品或重复调用已成功批次。每个 checkpoint 同时保存源单元身份与内容摘要，源文档发生变化时拒绝沿用旧批次；如果整个运行最终失败，则在失败终态事务中删除所有已成功的批次结果，避免遗留不可发布的半成品。

单卷最大题数只由管理员在“智能与题库”一级组设置，业务用户不能覆盖。生成运行固化当时的上限、知识点清单摘要和最终题数。

知识点超过单卷上限时采用固定降级顺序：

1. 先把相关知识点合并为综合题，尝试在单卷上限内覆盖全部知识点。
2. 若覆盖容量仍不足，创建题库系列：第一卷按重要程度选择上限内知识点，第二卷承接剩余知识点，最多只增加这一卷。
3. 第二卷达到上限后仍未覆盖的知识点允许舍弃，但必须持久化 total/covered/omitted 计数和遗漏知识点引用，并在生成结果页明确提醒。
4. 该降级只处理“有效知识点超过容量”。Provider 超时、调用失败、安全拒绝、坏 JSON 或 schema 不合法继续走重试/失败，不能发布部分题库。

生成是异步业务运行：

```text
CONFIGURING -> GENERATION_PENDING -> GENERATING -> PUBLISHED
                                      |-> GENERATION_FAILED
```

Task 读取固定的文档摘要、AGENT profile、Prompt revision、生成配置和 schema 版本。运行期间配置变更不影响该次结果；再次生成使用新快照和新幂等键。已确认整库通过 schema、业务约束和安全渲染校验后直接进入 `PUBLISHED`，不增加发布前管理员审核。

### 6.2 题库事实

已确认每次生成创建独立题库和不可变 revision 1；同一文档允许生成多个题库。发布后上传者和管理员都可以修正题目，但每次保存必须创建新的完整不可变修订并原子切换 current revision，不覆盖旧修订。管理员修订写审计，owner/admin 都记录 editor 与修订原因。

`QuestionBankSeries`：一次生成请求的稳定系列 ID、owner、source document、用户填写的基础标题/可选简介、管理员单卷上限快照、total/covered/omitted knowledge-point counts、coverage state、生成运行和时间戳。普通单卷也是只有 volume 1 的系列。

`QuestionBank`：series、volume number（1 或 2）、current revision ID、状态、生成配置、公开状态、管理员锁定原因码、删除请求和时间戳；同一系列最多两个卷且 volume number 唯一。展示标题由 series 基础标题加可选“第一卷/第二卷”确定，不让两个卷的标题漂移。

公开状态至少区分 `PUBLISHED`、`OWNER_HIDDEN`、`ADMIN_HIDDEN` 和 `DELETE_PENDING`。owner 可以把自己的 `PUBLISHED` 题库隐藏为 `OWNER_HIDDEN`，并原样恢复；也可以发起删除。进入 `DELETE_PENDING` 后立即退出 HTML/API 公共查询和新答题入口，`7 天`内撤销时恢复删除前状态；原状态为 `ADMIN_HIDDEN` 时仍保持管理员锁定。管理员可以强制隐藏、恢复或删除，但 owner 不能把 `ADMIN_HIDDEN` 改回公开，也不能通过编辑新 revision 绕过锁定。每次状态转换使用 row version；管理员动作写审计并通过通用通知告知 owner。

`QuestionBankRevision`：bank、递增 sequence、知识点覆盖/遗漏快照、题目数量、题型计数、schema version、editor、revision reason 和创建时间。每个 revision 不可变；发布指针只在新修订整卷校验成功后切换。

`Question`：revision、跨修订稳定 logical ID、ordinal、type、stem Markdown、options、correct answer、reference answer、explanation Markdown 和校验摘要。同一修订内 logical ID/ordinal 唯一。

`QuestionBankTag` 与 series assignment：由 `apps/learning` 独占的题库标签目录，保存规范化名称、来源（复用/AGENT 建议/owner 修改/管理员）、状态和使用计数。AGENT 自动生成标签并只在现有题库标签中优先复用；发布后 owner 和管理员可以修改系列标题、简介及标签，所有卷同步读取同一元数据。题库标签不引用 `apps/content` 的文章标签主键，也不共享审核、删除、统计或使用计数生命周期。

### 6.3 固定题型 schema

| 题型 | 必须字段 | 确定性约束 |
| --- | --- | --- |
| 单选 | stem、2-8 个选项、一个正确 option ID、解析 | option ID 唯一，正确项存在 |
| 多选 | stem、2-8 个选项、正确 option ID 集、解析 | 至少两个正确且不能全选；作答集合与正确集合完全相同才得分 |
| 判断 | stem、布尔答案、解析 | 不接受“看情况”等第三值 |
| 简答 | stem、参考答案、评分要点、解析 | 不自动计数值分；提交后由用户自评掌握状态 |

每个批次的模型响应必须是固定 JSON document，服务端校验源单元 ID、逐点一题、题型开关、选项和答案一致性、Markdown 安全性及总大小；所有批次通过后再按源顺序合并，执行管理员单卷题数上限、最多两卷、重复题和总覆盖校验，最终事务同时发布一个或两个完整卷与 coverage 结果，不保存半卷。覆盖不完整是显式 `PARTIAL` coverage，而不是静默冒充完整。

结构化 PostgreSQL 是判分和 API 的事实；可以从同一 projection 生成规范化 Markdown 文档供阅读/导出，但不反向解析自由格式 Markdown 作为运行时题目。

### 6.4 标签生成

运行前把有界的已有题库标签候选（名称和稳定 ID）提供给 AGENT；模型优先返回候选 ID，确实没有时返回新名称建议。服务端只在题库标签目录内规范化、去重、检查冲突后再创建或关联，不能让模型直接写标签表，也不能退回文章标签目录匹配。发布后 owner 与管理员修改元数据使用独立 row version，不改变题目或历史答题；题目修正通过新的 QuestionBankRevision 完成。

## 7. 题库浏览、搜索与外部 API

### 7.1 站内公开查询

- 已确认：所有人可以看到所有公开题库，并支持筛选和搜索。
- 建议列表展示题库名、题型构成、题量、标签、来源作者公开 ID、生成时间和可用状态；不展示原始文档正文或模型内部信息。
- 搜索复用项目现有 PostgreSQL 查询模式，模糊匹配题库系列标题、简介和独立题库标签；作者必须通过公开 ID/显示名建议选择稳定 account ID，不能把任意模糊作者文本直接混入主查询。所有字符串先规范化、限制长度并参数化；不匹配原始文档或题目正文。
- 默认排序是 `published_at DESC, id DESC`。`published_at` 是首次成功公开时间，修订、owner 隐藏后恢复或管理员恢复都不重写，防止通过状态切换顶到列表首位。用户可切换：最多答题（只计 `submitted_at` 非空且有效完成的 QuizAttempt，计数降序）、题量降序和题量升序；每种排序都追加 `published_at DESC, id DESC` 稳定次级键。未完成草稿、软删除记录和重复提交不计入答题次数。
- 筛选包括题库标签多选、题型多选、题量闭区间、首次发布时间闭区间和作者搜索选择。标签组内 OR，题型组内 OR，不同组与区间/作者/文本搜索之间 AND；空组不施加条件。选择数量、搜索长度和区间跨度使用有界 schema，非法 ID/倒置区间返回可操作参数错误。HTML 和外部 API 列表都调用 learning 的同一公开 query/filter DTO；API 开关关闭不影响站内页面。
- 题库被隐藏或进入删除流程后立即退出公共 HTML/API 查询和新答题入口，并使相关缓存/ETag 失效。删除冷静期结束后可以清理题库 series、revision、question 和标签关联本体，但既有 QuizAttempt/QuizResponse/WrongQuestion 必须依靠自己的不可变展示快照继续可读，不能通过已删除题库发起普通或错题练习。

### 7.2 API 边界

建议版本化只读路由：

```text
GET /api/v1/question-banks
GET /api/v1/question-banks/{public_id}
```

两条 API 与站内列表/详情调用同一个 `apps.learning.public` query/filter DTO/projection，不复制搜索、可见性、答案或标签规则，但保持独立 transport：站内 `/question-banks...`（最终按项目路由命名）返回服务端 HTML，`/api/v1/question-banks...` 只返回版本化 JSON，不做 `Accept` 内容协商，也不要求站内浏览器调用外部 API 后才能渲染。API enable gate、CORS、匿名 IP 限流、JSON error envelope 和 OpenAPI 只包裹 API transport；关闭 API 不影响 HTML query。

全局 `QuestionBankApiConfiguration` 默认 `enabled=false`，由“智能与题库”一级组中的 Switch 修改并审计。关闭时所有题库数据路由先于对象查询统一返回 JSON `404`，错误 envelope 使用稳定 code `api_disabled` 和 `Cache-Control: no-store`；列表、任意详情 ID、GET/HEAD 使用同一 gate，不能根据对象存在性分支。切换开关后使题库 API response/ETag 缓存整体失效。已确认开启后允许匿名只读 GET，并使用客户端 IP 进入服务端限流；首版 API 不提供知识文档上传、整理、题库生成或答题写入。

CORS 由 API 配置 owner 的独立策略端口处理。首版唯一可配置模式是 `ALLOWLIST`：默认列表为空，管理员维护精确 Origin。生产 Origin 必须是规范化 `https://host[:port]`，拒绝路径、query、fragment、userinfo、通配符、`null` 和重复项；隔离开发/测试 Origin 由环境专用配置提供，不能混入生产列表。命中时回显精确 Origin、发送 `Vary: Origin`，不发送 `Access-Control-Allow-Credentials`；未命中时仍可按普通匿名 API 处理请求，但不返回 CORS 许可头。无 `Origin` 的服务端请求和本站同源访问不受 CORS 限制。

策略接口保留版本化 mode 边界，未来可以新增 `ANY_ORIGIN`，但首版 schema/service/UI 都只接受 `ALLOWLIST`，未知模式拒绝启动或保存，不能静默解释为 `*`。未来全来源模式需单独裁决和迁移；即使启用也不得与 credentials 组合。

API 必须补全：

- 请求身份：已确认匿名公开，不签发 API key；所有请求仍经过网络策略、IP 限流和公开可见性 query；
- 列表使用页码分页：`page` 默认 `1` 且必须为正整数，`page_size` 默认 `20`、允许 `1..100`，越界返回统一参数错误而非静默截断。响应 envelope 返回 `count/total_pages/page/page_size/previous/next/results`；previous/next 保留规范化筛选和排序参数。稳定排序沿用 Q026A，站内 HTML 可以复用分页 query 但自行渲染页面链接；
- 已确认列表只返回题库元数据；详情返回完整题目、客观题正确答案、简答参考答案/评分要点和解析。任何响应都不返回原始知识文档、Prompt、Endpoint、Model、审核结论或内部运行信息；
- 通过项目可信代理边界解析客户端 IP，按 IP 应用管理员可调的分钟/每日双层限流，默认 `60/minute` 与 `3000/day`。分钟范围 `1..600`，每日范围 `100..100000`，且 daily >= minute；配置 UI 和 service 使用相同 schema，`0`、负数、越界或不一致组合保存失败。配置是 PostgreSQL 事实、变更使用 row version 和管理员审计；计数可用 Redis 原子操作优化。超限统一返回 JSON `429/rate_limited`、最短等待窗口的 `Retry-After` 及 `RateLimit-Limit/Remaining/Reset`，不查询或返回题库数据；
- 匿名分钟/每日计数依赖 Redis 原子操作；Redis 连接、脚本或超时失败时 API transport 必须 fail closed，在进入 public query 前返回 JSON `503/rate_limiter_unavailable`、`Cache-Control: no-store` 和短 `Retry-After`。不回退 PostgreSQL、进程内计数或临时放行，避免压垮持久层或多进程绕限。站内 HTML 不经过该 API limiter；持续故障通过现有运维最终失败/去重提醒管理员，恢复后自动继续正常限流。
- CORS 首版只允许管理员精确 HTTPS Origin 白名单，规范化、`Vary: Origin`、缓存键和拒绝语义一致；服务端调用不需要 CORS，浏览器跨域才需要；
- 统一错误 envelope、schema version、弃用窗口和 OpenAPI 文档；关闭时固定 `404/api_disabled` 且不返回 HTML 错误页；
- 只读 GET，首版不提供外部上传、生成、答题或管理写接口。

答案与题面属于同一公开题库 projection。题库隐藏、删除、API 开关关闭或缓存失效时，两者必须同时不可读取，不能留下独立答案缓存；API 输出继续经过 Markdown 安全投影和响应大小上限。

## 8. 答题、计时与判分

### 8.1 入口和前置配置

- 顶部共享 Header 在工作机会按钮相邻位置增加答题图标入口，仅登录用户渲染；所有登录用户均可使用，不要求作者角色或附件能力。
- 访客仍可浏览公开题库；访问答题路由时服务端跳转登录并使用安全 `next` 返回。
- 用户选择题库后进入配置页：题型多选、默认关闭的计时 Switch、开启后显示的固定时长菜单、抽题数量，并提供相互独立且默认开启的“随机题目”和“随机选项”Switch。题型只展示当前 revision 实际包含的类型，默认全选且至少选择一种；抽题数量范围为 `1..筛选后题数`。时长菜单只允许 `10、20、30、60、90、120` 分钟，初始选中 `30` 分钟；前后端都按白名单校验，不接受任意分钟数。计时关闭时服务端忽略隐藏时间值并保存 `deadline_at = null`，不能因客户端漏传配置而隐式开启。随机题目关闭时按不可变 revision 的 ordinal 从所选题型取前 N 题；开启时从所选题型随机抽取 N 题并随机排列。随机选项只作用于单选和多选；关闭时按 revision 中的选项顺序展示，开启时随机排列。用户可以在每次开始前分别关闭两个随机开关。
- 补充（D016，2026-10-09）：配置页增加答题模式选择，默认考试模式。两种模式共用相同的题型、题量、随机与计时配置；模式不改变抽题数或题序快照。
- 错题本按题库归组并复用同一配置页，题型多选默认覆盖当前可练错题实际类型；可抽数量上限改为所选题型下的当前可练错题数。创建 attempt 时在事务内锁定/读取 current revision 和错题集合，重新校验题型白名单与题数；配置页数据过期时返回冲突并刷新，不静默改选。

### 8.2 持久化建议

`QuizAttempt`：account、可空 bank/revision 引用、bank/series/title/owner 展示快照、来源（题库/错题本）、模式（`EXAM`/`PRACTICE`）、所选题型/计时/随机设置等配置快照、题目 logical ID 与顺序、每题选项顺序、状态、started/soft deadline/submitted 时间、得分和题型汇总。模式缺省为 `EXAM`，兼容历史记录与既有调用。创建 attempt 时一次性计算并保存筛选和随机结果；刷新、跨设备续答和重复读取都复用同一顺序。开始答题时固定 current revision，之后的题库修订不改变本次题面或答案；题库最终清理后以快照读取历史。

`QuizResponse`：attempt、可空 question 引用、题型/题干/选项/正确答案/参考答案/解析的安全快照、logical ID、答案 schema、row version、last saved time、客观题正确性/得分、简答题自评掌握状态、提交时间。选择题答案变更后立即保存；简答题在停止输入后防抖保存，并在离开题目或页面前补发尚未确认的保存。刷新、退出或跨设备从服务器恢复，不以浏览器本地状态作为最终事实。历史记录始终读取保存时快照，不从后来变更或已删除的题目重新判分。

自动保存请求携带当前 response row version 和幂等 request ID；过期版本返回冲突与最新服务端值，界面明确提示并重新加载，不能用“最后到达服务器的请求”静默覆盖另一设备的新答案。已提交 attempt 拒绝继续修改。自动保存只更新草稿答案，不提前判分、不写错题本，也不暴露正确答案。

刷题模式的单题提交是独立的登录用户命令，携带本人 attempt/response、row version 与 request ID，在同一事务中保存最后答案、判客观题、记录该题提交时间并更新错题本；重复提交幂等，已揭晓响应不可改写。query 仅在该响应已提交时返回对应答案/解析，其他响应仍隐藏。简答题不自动判分，逐题揭晓参考答案/评分要点后复用自评命令。最终提交仅判分/记入尚未逐题提交的响应，保留既有单题结果并聚合整套 objective/short-answer 结果，避免重复累计错题统计。

`WrongQuestion`：account、可空 bank/question 引用、bank/title/题目/答案/解析的安全快照、question identity、首次/最近答错时间、错误次数、答对次数、最近答对时间、手动掌握状态、状态修改时间和 row version。唯一约束防止同一用户同一题重复行。首次答错或简答自评“未掌握”时创建为 `TO_REVIEW`；此后作答只更新统计，不自动改变掌握状态。题库删除后错题快照仍可查看和手动管理，但练习入口禁用。

所有时间以服务端 UTC 事实计算并按上海时间展示。计时 attempt 的 `duration_minutes` 只能取固定白名单值，软提醒阈值 `deadline_at` 在创建时写入；刷新或换设备继续使用同一阈值，客户端倒计时不能延长。到达阈值只切换为超时提示并继续正向显示超出时长，服务端仍接受答案保存和手动提交，不自动提交或转终态。最终结果由 `submitted_at - started_at` 计算实际用时，并可判断是否超过软阈值。

### 8.3 判分

- 单选、判断：服务端精确判分。
- 多选：服务端对答案集合做顺序无关的严格相等判断；必须选中全部正确项且没有任何错选才得满分，否则为 `0` 分，不提供部分分或负分。
- 简答：已确认提交后展示参考答案和评分要点，由用户选择“已掌握”或“未掌握”。简答题不折算自动数值分，也不调用评分 AGENT；自评结果写入回答记录并决定错题本。
- 结果页把单选、多选、判断的客观题自动得分，与简答题“已掌握数 / 已作答数”分开显示，不能用一个百分比分数掩盖两种不同判定来源。
- 考试模式只有用户最终手动提交才判分、更新错题本并产生完成结果；刷题模式在每题手动提交时产生该题结果，最终手动提交仍将 attempt 转为完成并生成整套汇总。
- 软计时超时不改变两种模式的判分、错题本或简答自评规则。
- 提交使用 attempt row lock 与幂等 token；重复提交返回同一结果，不重复累计错题或分数。
- 自动保存的答案不产生正确/错误事实；考试模式在整套手动提交后判分，刷题模式在单题手动提交后只记录该题结果，最终提交仅补判尚未逐题提交的响应。

### 8.4 记录管理

用户只能查看和管理自己的答题记录及错题本，管理员不获得代看答案的默认例外。错题本默认展示 `TO_REVIEW`，用户可以显式标记为 `MASTERED` 并从默认列表隐藏，也可以从已掌握筛选中手动恢复；答对、答错和简答自评都不触发这两个状态之间的自动转换。

答题记录支持详情、题库/时间/完成状态/来源筛选、单条删除、当前筛选结果内的复选批量删除、清空全部和 CSV 导出。批量删除和清空必须在服务端再次按 owner 限定作用域，并显示将影响的精确记录数后确认；删除后立即退出默认记录查询并进入统一 `7 天`可撤销软删除期，期满才受控清理。答题记录和 WrongQuestion 是独立学习事实：删除记录不重算、不删除错题统计，也不改变手动掌握状态；账户级彻底清除仍服从 Q024D 的统一个人数据生命周期。

CSV 导出按每个 QuizResponse 一行展开并重复必要的 attempt 元数据，使用稳定 UTF-8 表头和流式分页，避免一次加载全部记录。导出只包含当前账户可见的答题快照，不包含原始知识文档、Prompt、模型配置或其他账户数据；所有以 `=、+、-、@` 开头的单元格按 CSV 公式注入规则转义。

题库后来隐藏时，记录仍显示当次标题、题目和答案；公共题库链接标记为不可用。题库最终清理后历史和错题通过自包含快照读取，外键允许安全置空；相关错题不再提供练习入口。账户级清理执行下述已确认终局规则。

账户达到 accounts owner 定义的彻底删除点时，learning 必须通过单一账户清理 service 幂等清除该账户的 KnowledgeDocument/media 绑定、失败材料、所拥有 QuestionBank、本人 QuizAttempt/QuizResponse 和 WrongQuestion，并使公共/API 缓存同步失效。该终局清理不再为每个子对象叠加新的 `7 天`冷静期。其他账户已产生的答题/错题快照保留，但清空可识别作者快照并固定显示“已注销用户”，置空 owner/bank/question 引用并禁用练习入口。

账户清理后的安全审计只允许保留不含账户 ID、公开 ID、邮箱、显示名、原文、题目、答案、路径或调用内容的事件类型、结果、计数和时间桶；不能用“最小审计”保留可反向关联的个人标识。账户清理必须有可重试游标和完成回执，不能因部分表失败而报告完成。

## 9. 权限矩阵草案

| 动作 | 访客 | 登录用户 | 有附件能力用户 | 管理员 |
| --- | --- | --- | --- | --- |
| 浏览公开题库 | Y | Y | Y | Y |
| 搜索/筛选公开题库 | Y | Y | Y | Y |
| 上传/整理知识文档 | N | N | Own | Own 且需附件能力；不代传 |
| 查看知识文档 | N | N | Own full text | Y full text；受控详情访问 |
| 发起题库生成 | N | N | Own approved document | 仅本人文档；不能代替他人 |
| 开始答题/写记录 | N | Own；无需附件能力 | Own | Own；不代看 |
| 管理本人错题/记录 | N | Own；无需附件能力 | Own | Own；不代看 |
| 配置 Endpoint/AGENT/Prompt | N | N | N | Y + 审计 |
| 查看调用状态/安全错误 | N | N | 仅本人业务状态摘要 | Y，仍不见秘密/正文 |
| 开关外部 API | N | N | N | Y + 审计 |
| 隐藏/恢复/发起删除题库 | N | N | Own；不能解除管理员强制隐藏 | Y + 审计/通知/强制管理 |

隐藏入口不替代服务授权。每次 upload、review、generate、attempt、record query 和 API query 都在服务端重算身份、能力、对象归属、状态、容量和频率策略。

## 10. 事件、任务与通知

建议领域事件：

- `agents.endpoint_configuration_changed.v1`
- `learning.knowledge_review_completed.v1`（verdict 为 approved/rejected）
- `learning.knowledge_review_failed.v1`
- `learning.question_bank_generated.v1`（coverage 为 complete/partial）
- `learning.question_bank_generation_failed.v1`
- `learning.question_bank_visibility_changed.v1`

建议任务：`review_knowledge_document`、`generate_question_bank`。二者都使用 TaskRun，幂等键包含业务对象与配置版本，瞬时错误最多按通用策略重试三次。业务状态原子进入终态后通过现有 Outbox 发布一次领域事件，通用通知消费者以 event ID + recipient + template key 去重：审核通过、驳回、审核系统失败、题库完整生成、部分覆盖生成、生成系统失败都通知发起用户。系统级最终失败同时遵循现有运维失败规则通知管理员，不创建第二套 outbox 或直接在 Task 内拼通知。

用户通知只包含安全标题、终态、稳定原因/覆盖计数摘要和本人可访问的内部对象链接；不包含知识正文、Prompt、题目/答案、模型原始输出、文件路径或秘密。部分覆盖必须明确 total/covered/omitted，不能用普通成功文案掩盖遗漏。最终失败写脱敏 RuntimeError；失败运行的受控输入快照和详细诊断保留 `30 天`后清理，只留下对象 ID、终态、稳定原因码、计数与时间。生成失败运行的到期清理不得级联删除仍有效的 `APPROVED` 源文档。

模型调用发生在数据库事务外。推荐流程是：事务内领取业务运行并固化输入快照，提交后调用模型，再以行锁验证仍是同一运行后原子落结果。Worker 崩溃、租约过期、配置禁用、文档被删除和重复投递都有明确幂等终态。

管理员配置、Prompt 切换、API 开关、题库强制隐藏/恢复/删除必须审计。审计只记录稳定 ID、版本、状态和安全计数，不记录 Prompt 正文、知识文档、题目正文、答案、Base URL query 或密钥。owner 的题库可见性动作保存业务状态事件，但不伪装成管理员审计动作。

## 11. 页面与交互状态

管理侧栏拆分为两个独立一级组：

1. AI 配置：Endpoint 运行参数、用量与连接检查；AGENT 用途、启停和 Prompt Markdown 版本。
2. 智能与题库：知识文档审核、题库生成/公开状态、题库运行配额和接口设置。

知识文档和题库列表允许管理员明确勾选稳定 ID 后批量隐藏、恢复或进入删除流程；不提供“当前页全部”或“全部筛选结果”隐式扩展选择。确认弹窗从服务端预检返回精确总数、当前状态分布、不可执行项和 row version token；执行 service 再按同一 actor/ID 集/版本校验，采用有界批次并返回逐项结果，不能因部分失败伪装成全部成功。原文访问和申诉决定始终逐条，禁止批量读取正文或批量批准/驳回申诉。

用户侧页面：公开题库列表/详情；由账户浮窗进入的“我的知识文档”及生成配置；由顶部答题快捷入口进入的答题配置、答题会话、结果、按题库错题本和答题记录详情。

所有异步页面覆盖 pending、running、success、rejected、failed、disabled、deleted 和恢复状态；轮询/HTMX 只刷新局部数据，不闪烁整页或改变滚动位置。按钮提交期间禁用并保持尺寸，错误保留用户配置，成功使用现有非阻塞浮窗反馈。

## 12. 容量、隐私与滥用边界

- `LearningQuotaPolicy` 由 learning 独占，保存全站默认的上传、待处理、生成、并发、题库数量及模型用量限制和 row version；`LearningAccountQuotaOverride` 对有附件权限账户按字段可空覆盖，空值继承全局。管理员在“智能与题库”一级组维护并审计，普通用户只能看到自己的剩余摘要，不能查看其他账户或全站费用。
- 全站默认单账户配额：每日成功新建知识文档 `10`，`REVIEW_PENDING/REVIEWING` 合计 `3`，每日接受题库生成请求 `5`，审核与生成合计同时模型运行 `1`，未最终清理 QuestionBank `100`。每日窗口按站点时区自然日；重复摘要拒绝和幂等重投不重复计数，同一业务运行的内部重试不新增次数。生成请求一旦被接受即计每日额度，最终系统失败也不回退已可能消耗的调用；`DELETE_PENDING` 仍占题库总量直到最终清理。管理员可在全站配额配置处二次确认重置当天所有账户的生成计数，配额上限和进行中任务保持不变。
- 账户覆盖硬范围：每日上传 `1..100`、同时待处理 `1..20`、每日生成 `1..50`、同时模型运行 `1..3`、未最终清理题库 `1..2000`。全局默认与账户覆盖写入都使用同一 schema；不接受 0、负数或越界值，完全禁用通过撤销 `attachment_upload_enabled` 完成，避免把配额变成第二权限系统。
- 全站配置和每个启用 Endpoint 都必须有每日 token 上限，且单业务运行仍受 Endpoint 上下文和单运行预算约束。运行在第一次 Provider 调用前，根据全部分块、最大输出和重试策略计算保守最坏用量，以同一 reservation ID 原子预留全站与 Endpoint 两个站点时区自然日 ledger；任一层不足都不调用模型，运行进入可重试的配额阻塞状态。
- 成功 Provider 调用返回可信 usage 时按实际输入/输出 token 结算并释放差额；失败、拒答、schema 修复失败或租约失效即使 usage 缺失/不可信也以 `0` 结算，不占每日额度，安全错误码仅在通知中说明。reservation 仍有租约、心跳和幂等结算，不能重复扣减或提前释放仍可能执行的任务。管理员降低上限不取消已预留运行，但阻止新预留。价格元数据可空，仅计算管理员可见估算，不成为自建模型必填项或授权事实。
- 全站每日 token 上限默认 `5,000,000`、硬范围 `100,000..100,000,000`；每个 Endpoint 默认 `2,000,000`、硬范围 `50,000..50,000,000`，并要求 endpoint_daily <= site_daily。创建/更新 Endpoint 和全站配置都执行单字段与交叉字段校验；降低全站上限导致现有 Endpoint 越界时整次保存失败并列出冲突对象，不静默改写 Endpoint。
- 模型用量设置提供两个独立管理员动作：“恢复默认上限”和“重置今日 token 已用量”。前者按作用域把全站恢复为 `5,000,000`、Endpoint 恢复为 `2,000,000`，仍执行 endpoint <= site 交叉校验；后者只重置已结算 usage，不清除活跃 reservation，也不重置账户上传/生成次数。两者都显示作用域、当前值/用量、活跃预留和变更后结果，二次确认并使用 row version。
- 今日用量重置不删除原始 ledger 行，而是追加包含管理员、原因、前后计数和时间的不可变 adjustment。全站重置同步归零全站及所有 Endpoint 的当日已结算贡献；单 Endpoint 重置同时冲减该 Endpoint 和其对应的全站贡献，保持两层汇总一致。活跃预留仍计入可用额度，重复 reset 使用幂等键不产生额外负数。
- upload/review/generate service 在写业务对象和领取模型任务前分别读取一次有效业务配额并原子预留用量，不能只由前端禁用按钮。配置变更从后续新请求/新领取生效，不取消已领取运行；撤销附件权限仍优先阻止新操作。缺少有效上限时不能开放真实调用。
- 文档和题目可能包含版权、隐私或机密信息。每次上传已要求版本化、默认未选中的授权/模型处理/公开衍生内容声明，并提供上述正式申诉入口；审核模型不能保证合法授权，声明和申诉也不能替代服务端权限、确定性门禁和管理员处置。
- 已确认原文只向 owner 和管理员开放，公开题库不提供原文下载；管理员正文访问不能通过列表批量预取或进入普通日志。
- 不自动访问 Markdown 内外部 URL、图片或嵌入，不把链接内容作为知识补充；是否支持站内媒体引用留待后续版本。
- 用户主动删除的知识文档、题库和答题记录统一采用 `7 天`软删除期，失败材料采用 `30 天`完整保留后转无正文 tombstone；源文档、题库与学习历史独立删除，题库清理后历史依赖自包含快照且禁止新练习。账户彻底删除时清理本人全部数据并匿名化其他用户的历史作者快照，只留不可识别的最小安全审计。
- 模型端点失败、配额不足、schema 不兼容和内容拒绝使用不同安全错误码，用户只见可操作摘要。

## 13. 验收方向

### 13.1 AGENT 运行时

Base URL SSRF、重定向、DNS 重绑定、超时、大响应、坏 JSON、schema 错误、Prompt 并发、端点禁用、密钥脱敏、幂等、三次失败和连接检查费用提示。

### 13.2 文档与题库

伪扩展、非 UTF-8、NUL、空文档、超限、无权限、权限中途撤销、指令注入、审核拒绝/失败/恢复、生成四题型组合、重复选项、非法答案、标签竞态、整库原子发布和资产清理。

### 13.3 浏览与 API

访客/登录/owner/admin 权限；搜索筛选分页；API 开关、限流、CORS、ETag、schema version、答案字段边界、隐藏后缓存失效和 HTML/API 查询一致性。

### 13.4 答题

抽题边界、刷新续答、跨设备软计时阈值、超时提醒后继续保存与手动提交、重复提交、并发提交、四题型判分、错题去重/掌握、题库隐藏后的记录、个人数据隔离和手机/键盘/三主题用户流。

## 14. 实施顺序与停止条件

1. Q001-Q039 及全部 A-F 子项已经确认；实施按 Todo 依赖顺序推进，发现新 schema、权限、外部暴露或评分歧义时重新进入 T00 补充裁决，不能静默猜测。
2. 建立 `agents` owner 和隔离假 Provider，先证明秘密、SSRF、schema 与调用状态。
3. 建立 `learning` 文档审核闭环，再做题库生成；不能先做假页面。
4. 完成结构化题库和公开查询后再开放 API；完成稳定题目版本后再做答题与错题本。
5. 每个切片先隔离 RED/GREEN，再在 Labs 使用假 Provider 或明确授权的测试模型；没有用户授权不得调用真实付费模型。

任一未决问题会改变数据 schema、权限、外部暴露或评分事实时，对应 Todo 保持“等待裁决”，不得以实现者偏好继续。
