# L. AGENT 运行时

所有者：`apps/agents`。本模块独占 Endpoint、Provider adapter、AGENT profile、Prompt 修订、调用事实和 token ledger；业务模块只能用稳定 profile key 发起结构化调用。

## 责任与非责任

负责管理员配置的多 Endpoint、不可变 Prompt 修订、统一 Provider Gateway、调用快照、双层 token 预留/结算、租约回收和安全错误。首版协议为 GPT/OpenAI-compatible、DeepSeek/OpenAI-compatible 与 Claude Messages。

不拥有知识文档、题库、答题、媒体、通知、TaskRun 或审计表；不允许业务用户选择模型、覆盖 Prompt、读取 Endpoint 配置或取得密钥。Provider 输出不是业务事实，只有调用方完成 schema 与领域校验后才可写入自己的聚合。

## 内部目录

```text
apps/agents/
  models/{checks,configuration,invocation,usage}.py
  services/{checks,configuration,prompts,invocations,runtime,usage}.py
  providers/{adapters,http,langchain_adapter,fake}.py
  gateway.py
  schemas.py
  queries.py
  public.py
  tasks.py
```

目录只随真实职责建立；T04 已落地显式连接检查及其 TaskRun/Celery 入口，其他业务 Task 在 T07/T10 前不预建空目录。跨 app 入口只从 `apps.agents.public` 导出。

## 公共端口

- `create_agent_invocation(profile_key, caller_type, caller_id, idempotency_key, estimated_input_tokens)`：从启用 profile 创建幂等 Invocation，并固化 Prompt、Endpoint、认证别名和全部运行参数；不返回或保存真实密钥。
- `invoke_structured(invocation_id, input_blocks, prompt_variables, output_validator)`：只使用 Invocation 快照，首次外呼前完成防御性快照校验和全站/Endpoint 原子预留；调用方的动态领域校验在 Harness 内参与 schema repair 后，再返回不可变 `ValidatedOutput`；兼容性的 `result.value` 只读视图不得作为新的业务入口。
- `settle_token_reservation(...)` 与 `recover_expired_token_reservations(...)`：成功调用按可信 usage 结算差额；失败、拒答、结构化修复失败和运行中租约过期以 `0` 结算，不占每日额度，失败原因保留在 invocation/通知事实中；重复结算与重复恢复幂等。
- `request_agent_endpoint_check(...)` 与 `execute_agent_endpoint_check(...)`：管理员显式请求后固化 Endpoint 快照，提交事务后进入统一 TaskRun/Celery 入口，并复用相同双层 token ledger；连接检查不修改 Endpoint 配置。
- capability probe 只能从已启用 Endpoint 下、已有当前 Prompt 的 profile 中选择 schema；profile 本身可以处于待启用状态，以闭合“先探测、后启用”。检查结果保存 Endpoint row version、schema、策略、adapter version 和安全错误码，并区分连通性与严格 schema 支持；启用 profile 时必须读到当前 Endpoint 版本、同一 schema 的成功严格探测。
- `CONNECTIVITY_ONLY` 检查通过 LangChain 普通消息路径执行，不带 schema/tool 约束；只有指定 `schema_key` 时才进入 structured-output capability probe。两者共享 `SafeProviderHttpClient`、认证快照和 token reservation，但不能用连接成功替代 schema 能力成功。
- 管理命令负责 Endpoint/AGENT/Prompt、全站与 Endpoint 上限、连接检查和 adjustment；全部重新校验管理员权限、row version 与审计 schema。
- `task_run_metadata(run_ids)` 只返回任务列表所需的安全用量 DTO；administration 在组合任务页面时显式传给 operations 查询，operations 不反向导入 agents 私有模型。

## 默认 AGENT 与 Prompt

系统提供两个稳定的业务 profile 定义，由
`apps.agents.management.commands.seed_default_agent_profiles` 创建，不在应用启动时
自动写库，也不调用 Provider。命令需要管理员 ID 和目标 Endpoint ID；创建后 profile 默认关闭，
管理员确认 Endpoint 已启用且 capability probe 成功后，再通过现有管理入口启用。

| profile key | 用途 | schema | Prompt 变量 |
| --- | --- | --- | --- |
| `knowledge-review` | 知识文档安全审核 | `knowledge-review.v1` | `document_block`、`block_index`、`block_count` |
| `question-generation` | 知识点分析与题库生成 | `question-generation.v1` | `document_block`、`knowledge_points`、`question_types`、`question_limit`、`tag_candidates` |

Prompt 只表达业务目标、资料不可信边界和输出意图；schema、tool choice、材料隔离、错误反馈、
重试和终态均由 Harness 强制执行。命令不会把 Prompt 原文写入审计或运行日志以外的额外事实表，
Prompt revision 仍由 `AgentPromptRevision` 不可变 owner 管理。

`input_blocks` 是有界、不含账户资料的值对象；不能传 ORM、文件路径、请求对象或任意工具描述。模块禁止 Provider tool call。

## 数据与用量边界

- `AgentEndpoint` 支持服务器秘密别名或加密保存的自定义 API Key；任何 API Key 都不以明文进入数据库、审计或页面。运行参数使用统一范围与交叉约束；推理强度由 Provider/model capability registry 映射，未知自定义模型默认不发送推理参数。旧版 Claude 的 `thinking.budget_tokens` 与现代 effort 独立校验，不能任意混用。
- `AgentPromptRevision` 不可变；profile 只有一个当前 Prompt 指针，并发切换使用 row version。
- `AgentInvocation` 固化 Endpoint、模型、认证别名、Prompt、运行参数、推理配置、调用方与 schema 版本，只保存摘要、计量、起止时间和安全错误码，不保存知识正文、完整 Prompt、真实密钥或原始响应。Gateway 不读取当前 Endpoint 配置，配置变更不会漂移在途调用。
- PostgreSQL ledger/reservation/adjustment/reset operation 是额度事实。每次首次外呼前原子预留全站与 Endpoint 上海自然日额度；Redis 不能成为费用裁决。
- reset 追加 adjustment，不删除 ledger，也不释放活跃 reservation。

## Provider 与威胁边界

- 连接形状使用 LangChain `ChatOpenAI` / `ChatAnthropic` 的声明版本：Provider、Model、可选 Base URL、服务器 API Key、输出上限、超时和模型匹配的推理参数。OpenAI 使用顶层 `reasoning_effort`，DeepSeek 使用 `reasoning_effort` 加 `thinking` 扩展，现代 Claude 使用 `output_config.effort`/adaptive thinking，旧版 Claude 使用 `thinking.budget_tokens`。OpenAI/DeepSeek 的根域名 Base URL 自动补 `/v1`，显式版本或自定义路径保持不变；OpenAI 使用现代 `max_completion_tokens`，DeepSeek/Anthropic 保持各自协议字段。启用思考模式时不发送上游禁止的 `temperature` 等参数。LangChain 通过 `langchain_adapter.py` 接入，但请求必须经由 `SafeProviderHttpClient`，不改变 `apps/agents` 对安全 transport、配额、租约、重试和最终校验的 owner 责任。
- LangChain 是运行时必需依赖；缺失时返回明确的 `agents.langchain_unavailable.v1`，不静默回退到旧 Provider adapter。`providers/adapters.py` 只保留协议 fixture/兼容解析契约，不作为 Gateway 的第二调用中心。
- 公网 Endpoint 只允许 HTTPS；loopback/内网 HTTP 必须命中服务器网络 allowlist。云元数据、链路本地、凭据 URL、query、fragment、控制字符始终拒绝。
- DNS 解析前后复核、重定向逐跳复核，并限制连接、读取、总超时和响应体；防止 SSRF、DNS rebinding、慢响应与大响应。
- 真实密钥只从 `KAJ_AGENT_SECRET_*` 专用注册表解析；内网例外只读取精确 `KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST` 的 `host:port`。页面、审计、事件、日志、异常和连接检查均不得回显密钥。
- 调用方文档作为带边界的“不可信资料”；系统安全包裹、禁止执行资料内指令、schema 和工具禁用不能被管理员 Prompt 覆盖。
- token 业务上限、全站/Endpoint 日上限、并发租约和有限重试共同约束费用；额度不足必须零外呼。Gateway 预留完整 per-run 上限，并按 `estimated_input + max_output` 的单次最坏值把外呼总数限制为最多三次且不超过 per-run；租约至少覆盖全部允许请求、退避和安全余量，避免正常慢调用被提前回收。
- 模型输出依次经过字节上限、JSON 解析、注册 schema 和调用方领域校验。坏 schema 只允许一次受限修复请求，不能落为半成品业务事实。
- 知识文档的 `estimated_tokens` 使用保守 UTF-8 文本估算，不把原始字节数直接当 token；Provider read timeout 遵守 Endpoint 的请求总预算（最大 1800 秒），避免复杂题库生成被固定的 30 秒首字节窗口误杀。
- 成功调用的多次外呼按可信 usage 累加并结算；失败调用即使存在不完整 usage 也不计入每日 ledger。调用终态、`0` 结算和安全错误码在同一事务完成，终止时间使用终态时钟而不是开始时间。

## 依赖方向

`agents -> accounts public / operations public / core`。accounts 只提供管理员身份裁决；operations 只提供 Audit/TaskRun/RuntimeError 端口。`agents` 不依赖 `learning`、`media` 或 `notifications`，这些模块也不得读取 agents 私有模型。

## 验证

Endpoint 参数边界与快照、Prompt 不可变和并发 409；恶意 URL、DNS rebinding、重定向、超时、大响应、坏 JSON/schema；秘密脱敏；双层额度不足零外呼、并发预留、重复结算、租约回收、reset adjustment；三个 adapter 与确定性 fake Provider 契约一致。

施工依据：`contracts/01-application-services.md`、`contracts/04-events-errors.md`、`contracts/05-background-tasks.md`、`data/04-indexes-constraints.md`。
