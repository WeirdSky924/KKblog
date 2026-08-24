# ADR-008：Agent 结构化输出 Harness

状态：Implemented（Labs 真实 Endpoint capability、知识审核和题库生成已验收）

## 背景

`apps/agents` 当前把“结构化输出”实现为一条短链路：Provider 返回文本 → JSON 解析 → 注册的 Python validator → 最多一次修复请求。这个链路能拒绝坏结果，但不能可靠地保证模型一定沿着 schema 生成，也不能区分 Provider 拒绝、工具调用、截断、拒答、JSON 解析失败和领域语义失败。

现状还有三个具体缺口：

1. GPT/OpenAI-compatible 使用 `json_schema`，DeepSeek 使用 `json_object`，Anthropic 使用普通文本消息。三者的约束强度不同，却共用同一个“文本 JSON”解析假设。
2. 修复由一个 `repair` 布尔值控制，没有记录每次尝试的阶段、失败路径、校验错误摘要、Provider 终止原因和最终裁决，无法形成可观测、可测试的状态机。
3. Schema 只有 Provider JSON Schema 和 Python validator 两份松散对象，没有编译、能力检查、规范化、跨字段语义阶段，也没有在 Endpoint 检查时验证“这个 Endpoint 能否执行某个业务 schema”。

## 研究依据

以下结论来自截至 2026-08-19 可公开访问的资料；链接只作为设计证据，不把第三方实现当作本项目代码真值。

### DeepSeek API 与 DeepSeek Harness

- DeepSeek JSON Output 文档明确要求 `response_format: {"type":"json_object"}`，并要求 Prompt 中出现 JSON 相关指令和示例；文档同时说明接口偶尔可能返回空内容。JSON Output 只保证可解析 JSON，不等于满足某个 JSON Schema。
- DeepSeek Tool Calls 文档的 strict mode 要求函数 `strict: true`，服务端会校验函数 JSON Schema，并在工具参数上执行严格格式约束。该通道比 `json_object` 更接近 schema 输出，但仍必须在应用侧重新校验。
- DeepSeek Harness 的公开架构文档展示了另一类有价值的工程思想：工具 schema 由运行时注册表生成并校验；工具调用经过 pre-execute、单调安全 guard、execute、post-execute、外层 normalization、definition-owned finalize 的完整流水线；结果以不可变事件记录并供 UI 和后续上下文消费。它保证的是执行边界和结果生命周期，不是替模型完成业务 schema 校验。

来源：

- https://api-docs.deepseek.com/guides/json_mode
- https://api-docs.deepseek.com/guides/tool_calls
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/tool-execution-pipeline.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md

### Provider 原生结构化输出与 ToolStrategy

公开的 LangChain 结构化输出文档把策略分成 ProviderStrategy 和 ToolStrategy：优先使用 Provider 原生 schema 约束；没有原生能力时，将 schema 转成一个专用工具并校验工具参数；校验失败通过 ToolMessage 把具体错误反馈给模型，在有界次数内重试；多次结构化工具调用也是明确错误，而不是“取第一个”。这说明可靠性来自“策略选择 + 解析 + 校验 + 有界反馈循环”，不是来自一段更长的 Prompt。

来源：https://docs.langchain.com/oss/python/langchain/structured-output

### Claude Code 所谓泄露内容

Claude Code 是闭源产品。网络上以“泄露源码”或“内部 Prompt”名义流传的内容没有稳定的版本、真实性或授权证明，不能作为本项目的架构事实。可以借鉴的公开工程原则只有：工具 schema 由运行时注册、工具执行前后有 policy seam、事件日志是事实来源、结果经过统一 normalization 和 finalize；这些原则也能由 DeepSeek Harness 的公开仓库直接核验，因此不依赖泄露材料。

## 决策

新增一个由 `apps/agents` 独占的 **Structured Output Harness**。业务模块仍只调用 `invoke_structured`，不直接接触 Provider 差异。Provider 的 schema binding 和结果抽取使用声明版本的 LangChain `with_structured_output`；网络安全、配额、租约、重试和最终业务校验仍由本模块独占。Harness 必须把一次调用分成以下不可跳过的阶段：

```text
schema compile
  -> capability selection
  -> bounded provider call
  -> envelope extraction
  -> strict JSON decode
  -> structural schema validation
  -> normalization
  -> domain semantic validation
  -> accepted result OR bounded repair/retry OR terminal failure
```

### 1. Schema 成为可编译契约

把当前 `StructuredSchema` 扩展为不可变 `SchemaSpec`，至少包含：

- 稳定 key、版本、规范化后的 JSON Schema 和 schema 摘要；
- Provider 可用的 strict subset 编译结果；
- `decode`、`normalize`、`validate_structure`、`validate_semantics` 四个明确阶段；
- 最大输入/输出字节、数组/对象深度和候选结果数量上限；
- 允许的输出策略：`native`、`tool`、`json_best_effort`；业务 schema 可以禁止 best-effort；
- 安全的错误路径格式，例如 `volumes[1].questions[3].ordinal`，不保存原始模型正文。

注册时先编译并拒绝：未知类型、递归引用、缺少对象 `additionalProperties: false`、不支持的组合关键字、超大 schema、validator 与 provider schema 无法通过固定样例对齐的定义。不能等到真实调用才发现 schema 不可执行。

### 2. Provider 能力不是一个布尔值

每次 invocation 根据 Endpoint 协议、模型能力快照和 schema 编译结果选择策略：

| Provider/能力 | 首选通道 | 不能使用首选通道时 |
| --- | --- | --- |
| OpenAI-compatible strict JSON Schema | `response_format.json_schema` | 专用 output tool；没有严格通道则拒绝业务调用 |
| DeepSeek V3.2+ strict tool | 单一 output tool，`strict=true`，固定 `tool_choice` | 仅 `json_object` 只能标记 best-effort；审核/题库生成默认拒绝 |
| Anthropic tool use | 单一 output tool，`input_schema`，固定 `tool_choice` | 若 Endpoint 明确声明 native structured output 才使用 native；否则不能把文本 JSON 当严格输出 |
| 未知 OpenAI-compatible | Endpoint 检查后显式声明 | 未通过 capability check 时拒绝，不静默降级 |

连接检查与业务 schema 检查分开。管理员点击“检查 Endpoint”只使用 LangChain 普通消息调用证明网络、认证和模型可响应，不发送 `response_format` 或 `tools`；启用 profile 前还必须用该 profile 的真实 schema 做一次零业务数据的 capability probe，并保存支持的策略、模型响应终止类型和安全错误码。

### 3. 输出 Envelope 先于业务值

LangChain 只负责把 Provider 的原生 structured output/tool calling 绑定成可解析结果，不能直接成为业务事实。`apps/agents/providers/langchain_adapter.py` 将 LangChain 的 `AIMessage`、tool calls 和 usage 转为本项目的 `ProviderEnvelope`；它通过 `SafeProviderHttpClient` 的受控 httpx transport 发出请求，禁止默认客户端绕过 SSRF、DNS rebinding、重定向、响应上限和认证头策略。Gateway 继续负责有界重试、repair、token reservation、lease 和 `ValidatedOutput`。

Provider adapter 不再直接返回 `Mapping`，而返回统一 `ProviderEnvelope`：

- `finish_reason`、`refusal`、`incomplete`、`content_blocks`、`tool_calls`；
- 可信 usage；
- response 字节数、响应摘要和 adapter 版本；
- 不保存原始正文、Prompt、密钥或 Authorization Header。

Extractor 只接受以下结果：

1. native structured response 中唯一的结构化值；
2. 固定名称 output tool 的唯一一次调用及其 arguments。

拒答、截断、空内容、未知工具、多个 output tool 调用、工具参数不是对象、混合文本与工具结果均进入明确错误码。不能“取第一个看起来像 JSON 的片段”。

### 4. 校验是四段式且结果不可变

- `decode`：UTF-8/字节上限、重复 JSON key 拒绝、严格 JSON 解析；
- `validate_structure`：JSON Schema required、类型、枚举、边界、additional properties；
- `normalize`：只做声明过的空白、排序、默认值和稳定 ID 规范化，不改变语义；
- `validate_semantics`：业务跨字段规则，例如题型与 options/correct ids 一致、ordinal 唯一连续、volume 编号唯一、knowledge point 必须被覆盖或列入 omitted。

只有四段全部通过的不可变 `ValidatedOutput` 才能交给 learning 写入业务表。Provider 原始响应、repair 文本和中间候选永远不能成为业务事实。

### 5. 修复与重试是有界状态机

把当前 `repair` 布尔值改为显式尝试状态：

```text
PREPARE
  -> PROVIDER_RETRY (网络/429/5xx，指数退避，受 token/时间上限约束)
  -> EXTRACT_REPAIR (空、截断、未知/多工具、JSON 解析失败)
  -> SCHEMA_REPAIR (结构校验失败)
  -> SEMANTIC_REPAIR (领域校验失败)
  -> ACCEPTED | FAILED | REFUSED | INCOMPLETE
```

每种 repair 最多一次；transport retry 与 repair 次数分开计数，但共同受 invocation 的 token、总时限和最大尝试数约束。repair 消息只包含机器生成的字段路径、期望类型/范围和有限错误码，不回显完整模型输出，也不把不可信材料拼进管理员 Prompt。重试后仍失败则终止并保留可重试业务状态，禁止静默降级到部分结果。

### 6. 观测与持久化

新增受控的 `AgentInvocationAttempt` 事实或等价事件，记录：attempt sequence、phase、strategy、provider finish、safe error code、schema version、adapter version、input/output byte count、usage trust、开始/结束时间和摘要。它不记录正文、Prompt、密钥或原始 response。

Invocation 终态只能由 Harness 写入：`SUCCEEDED`、`FAILED`、`REFUSED`、`INCOMPLETE`、`CANCELLED`。成功 reservation 按可信 usage 结算；失败、拒答、结构化修复失败和租约失效统一以 `0` 结算，不占每日额度，安全错误码通过业务通知说明。重复执行、租约回收和任务重试继续沿用现有 `apps/operations` 契约。

## 实施前基线与目标实现的差异

| 能力 | 实施前状态 | Harness 目标 |
| --- | --- | --- |
| Provider schema 通道 | GPT strict、DeepSeek json mode、Claude 文本 | LangChain ProviderStrategy/ToolStrategy 语义，最终 Envelope 仍由本项目裁决 |
| Schema 定义 | JSON Schema + 单 callable validator | 可编译 SchemaSpec + normalize + semantic validator |
| 响应解析 | 只读单条文本 content | Envelope、拒答/截断/工具调用分类 |
| 修复 | 单次 repair 布尔值 | 分阶段、有界、可观测状态机 |
| Endpoint 检查 | `{ok:true}` 连通性 | 连通性 + profile/schema capability probe |
| 失败事实 | Invocation 安全错误码 | Attempt 事实 + 终态 + 安全摘要 |
| 业务落库 | schema validator 后写入 | 四段验证后的不可变 ValidatedOutput |

## 实施顺序

1. **契约切片**：定义 `SchemaSpec`、`ProviderEnvelope`、`ValidatedOutput`、phase/error 枚举和 provider capability matrix；为现有 review/generation schema 增加 semantic validator。
2. **编译与校验切片**：实现 schema subset compiler、规范化和结构/语义四段验证；现有 `StructuredSchema` 提供兼容 facade，但不再新增第二套注册表。
3. **Provider 切片**：OpenAI native、DeepSeek strict output tool、Anthropic output tool；adapter 测试覆盖拒答、截断、空内容、未知/多工具和 usage 不可信。
4. **Harness 状态机切片**：替换单一 repair flag，拆分 transport retry 与 repair，统一预算、租约、幂等和安全 attempt 记录。
5. **Capability probe 切片**：管理员 Endpoint 检查增加按 profile/schema 的能力结果；不支持严格策略的 Endpoint 不能启用关键 AGENT。
6. **领域迁移切片**：learning 只消费 `ValidatedOutput`；旧 Invocation 按 schema/adapter 版本回放，不能用新 schema 重解释历史结果。
7. **回归与灰度切片**：fake Provider、真实协议 envelope fixture、隔离 PostgreSQL 读回、失败重试矩阵和有限的 Labs 业务 smoke；不调用真实付费 Provider。

## 验收标准

- DeepSeek `json_object` 返回语法正确但字段错误时，不得发布题库；必须进入结构/语义修复或终态失败。
- DeepSeek strict tool、Anthropic output tool、OpenAI native 三种策略均能从唯一结构化通道读回相同 `ValidatedOutput`。
- 空内容、refusal、max-tokens、未知工具、多工具调用、重复 JSON key、额外字段、类型错误和跨字段错误都有独立安全错误码和测试。
- repair 不超过声明次数，token/时间/租约不被重试绕过；失败不会写半成品业务事实。
- Endpoint capability probe 能区分“网络可达”“JSON 可生成”“schema 严格可执行”。
- 现有业务模块不读取 Provider 原始 response，不拥有第二套 retry/schema/parser。

## 非目标

- 不实现任意 Prompt 让模型“自证符合 schema”的软约束。
- 不把未经证实的 Claude Code 内部实现当作依赖。
- 不把 LangChain 变成第二个 Provider Gateway；它只作为 `apps/agents/providers/langchain_adapter.py` 的 Provider binding/解析实现，所有权仍归 `apps/agents`。
- LangChain 运行依赖缺失必须显式失败，不得静默降级到旧自定义 Provider 请求；旧 adapter 仅用于协议 fixture 和迁移期解析契约测试。
- 不允许业务模块自行修复、截断、补默认字段或从文本中正则提取 JSON。
