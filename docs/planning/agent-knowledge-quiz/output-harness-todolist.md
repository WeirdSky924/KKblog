# Output Harness 实施 Todo

依据：[ADR-008：Agent 结构化输出 Harness](../../architecture/adr/ADR-008-agent-structured-output-harness.md)。

状态：进行中。代码、隔离验证、Labs migration、默认 profile seed、LangChain Provider 接入和运行时依赖安装已完成；Labs Endpoint 的严格 probe 仍连续返回 `agents.provider_transient.v1`，两个 profile 暂不能安全启用。一次只允许一个 Todo 处于“进行中”；本文件记录施工顺序，不替代 ADR 的设计裁决。

## 目标与边界

目标是让审核、题库生成和后续 AGENT 业务只接收经过确定性验证的 `ValidatedOutput`。Provider 原始文本、Prompt、工具参数中间态和 repair 内容不能成为业务事实。

本轮包含：schema 编译、Provider 能力选择、native/tool 输出、Envelope 提取、四段校验、分阶段有限修复、Endpoint capability probe、invocation attempt 事实、审核/生成 AGENT 与 Prompt 接线、隔离回归和 Labs 读回。

本轮不包含：真实付费 Provider 调用、生产或共享数据库 migration/写入、任意 Prompt 让模型自证、业务模块各自创建 parser/retry、Git 提交推送。

## T00｜基线与契约冻结

- [x] 读取 ADR-008、agents/learning 架构和当前测试入口，确认 `StructuredSchema`、`AgentGateway`、`invoke_structured` 唯一 owner。
- [x] 列出当前两个业务 schema：`knowledge-review.v1`、`question-generation.v1` 的结构规则、跨字段语义规则和版本兼容边界。
- [x] 定义 phase/error/strategy 枚举、`SchemaSpec`、`ProviderCapability`、`ProviderEnvelope`、`ValidatedOutput` 的公共契约。
- [x] 为每个契约写 RED 测试；未解决的 schema、Provider 或持久化冲突停止实现并回到 ADR 裁决。

## T01｜SchemaSpec 编译与兼容 facade

- [x] 在 `apps/agents/schemas.py` 内扩展现有 owner，不创建第二个 schema 注册中心。
- [x] 实现 JSON Schema 安全 subset 编译：对象必须显式 `additionalProperties=false`，拒绝未知关键字、递归引用、超大深度/字节和不支持组合。
- [x] 生成 canonical schema、schema digest、Provider strict 版本和稳定错误路径。
- [x] 保留 `StructuredSchema` 兼容入口，但新注册必须经过 `SchemaSpec` 编译。
- [x] 为 review/generation schema 注册 normalize 与 semantic validator。
- [x] RED/GREEN：重复 key、额外字段、非法 schema、大小边界、validator/provider schema 漂移。

## T02｜四段确定性校验

- [x] 实现 `decode`：UTF-8、响应字节上限、重复 JSON key 拒绝、只允许一个 JSON object。
- [x] 实现 `validate_structure`：required、类型、enum、长度、数组数量、additional properties。
- [x] 实现 `normalize`：只应用声明过的空白/默认/稳定排序，不改变业务语义。
- [x] 实现 `validate_semantics`：跨字段规则和业务不变量；错误只返回 safe path/code/expected。
- [x] `SchemaSpec.validate()` 复制四段结果后才允许 learning service 消费；`ValidatedOutput` 类型封装待 T06 完成。
- [x] RED/GREEN：缺字段、类型错误、额外字段、重复 ID、序号断裂、题型/选项矛盾和 omitted 覆盖错误。

## T03｜统一 ProviderEnvelope

- [x] Provider adapter 已返回包含 finish/refusal/incomplete/tool/usage/response bytes 的统一解析结果（兼容名称 `ParsedProviderResponse`，T03 后续可重命名为 `ProviderEnvelope`）。
- [x] Envelope 字段统一表达 finish reason、refusal、incomplete、content blocks、tool calls、usage trust、response bytes 和 adapter version。
- [x] OpenAI response 解析 native structured content、refusal、length、empty 和多 choice。
- [x] DeepSeek response 解析 JSON mode 与 strict output tool 两种结果；固定 output tool 名称和唯一调用。
- [x] Anthropic response 解析 text、tool_use、refusal/stop reason、多个 content block 和 token usage。
- [x] 未知工具、多工具调用、混合文本/工具结果、空 arguments 均进入明确错误码。
- [x] 不记录原始 response、Prompt、密钥或 Authorization Header。

## T04｜Provider capability matrix 与请求策略

- [x] 扩展 `ProviderAdapterInput`，支持 strategy、output tool schema、固定 tool choice 和 schema name。
- [x] OpenAI-compatible strict schema 优先 `response_format.json_schema`，无能力时可使用 strict output tool。
- [x] DeepSeek V3.2+ 使用 `strict=true` output tool；只有 `json_object` 时标记 best-effort。
- [x] Anthropic 使用固定 output tool 与 `input_schema`；只有明确声明 native 能力才走 native。
- [x] 关键 schema 根据协议选择严格 strategy；未知能力不会静默跳过 strategy 选择。
- [x] 为 capability matrix 建立 provider request fixture 和 payload 合同测试。
- [x] 通过 `langchain_adapter.py` 使用 LangChain structured-output binding；LangChain 不持有网络安全、重试、配额或业务校验所有权。

## T05｜Endpoint capability probe

- [x] 保留连通性 probe 与 schema capability probe 的边界；`EndpointProbeInput.schema_key` 支持按 profile schema 探测。
- [x] capability probe 使用真实 profile schema 的最小、无业务数据请求，读回 strategy、finish、解析和校验结果。
- [x] 保存 Endpoint/Model/Protocol/Schema/strategy/adapter version 的安全结果和错误码。
- [x] 管理页面明确区分：网络可达、可返回 JSON、严格 schema 可执行。
- [x] 不支持关键 schema 的 Endpoint/Profile 不允许启用；待启用 profile 可先探测，启用和每次 Invocation 都要求当前 Endpoint row version 的成功严格 probe；不改变现有 Endpoint 配置。
- [x] 覆盖 fake Provider 的成功、拒绝、超时、空响应和不支持 strict tool；真实隔离执行读回 `SCHEMA_SUPPORTED`、strategy 与 adapter version。

## T06｜Harness 阶段状态机

- [x] 用显式 phase 替换当前 `repair` 布尔值：PREPARE、PROVIDER_RETRY、EXTRACT_REPAIR、SCHEMA_REPAIR、SEMANTIC_REPAIR、ACCEPTED、FAILED、REFUSED、INCOMPLETE、CANCELLED。
- [x] transport retry 与 repair 次数分开计数，共享 token、总时限、lease 和最大尝试预算。
- [x] 每种 repair 最多一次；repair 只发送安全的字段路径/错误码，不回显完整模型输出。
- [x] refusal/incomplete/未知工具/多工具不能被当作普通 schema error 无限修复。
- [x] 失败终态保留业务可重试状态，不写半成品；重复执行继续由幂等键裁决。
- [x] RED/GREEN：网络连续失败、schema 两次失败、语义修复失败、预算不足、租约过期、拒答/截断和重复调用已有 Gateway 回归覆盖；attempt phase/error/终态读回已补齐。

## T07｜Invocation attempt 事实与结算

- [x] 新增 `AgentInvocationAttempt` 模型/迁移；不保存正文。
- [x] 记录 sequence、phase、strategy、provider finish、safe error、schema/adapter version、bytes、usage trust、时间和摘要。
- [x] Invocation 终态只能由 Harness 写入；增加 REFUSED/INCOMPLETE 状态并保持历史状态兼容。
- [x] 成功调用的可信 usage 累加结算；失败/拒答/schema 修复失败/租约失效均以 `0` 结算，不占每日额度，安全错误码进入通知。
- [x] 过期 lease、worker 重试、重复 finalize 和取消沿用现有幂等 owner；attempt 写入使用 invocation 级序号。
- [x] 隔离 PostgreSQL 读回 attempt、终态、ledger 和 lease；最新 agents/learning 聚焦回归均通过，migration 读回 attempt 表初始为 0。

## T08｜AGENT/Prompt 注册与业务接线

- [x] 提供 `seed_default_agent_profiles` 命令，为 `knowledge-review` 和 `question-generation` 注册稳定 AGENT profile、schema key 和默认 Prompt 修订；隔离 PostgreSQL 验证创建与重复 seed 幂等。
- [x] 默认 Prompt 明确审核/生成用途、材料不可信边界和严格结构化输出要求。
- [x] Prompt 只保留业务指令；系统安全包裹、材料隔离、schema/tool strategy 由 Harness 强制提供。
- [x] 审核任务只消费 `ValidatedOutput`；拒绝、失败和 capability unavailable 走现有通知/operations owner。
- [x] 题库生成只消费完整、语义通过的 `ValidatedOutput`；批次内允许动态知识点数量，知识点必须携带当前批次的 `source_unit_ids` 证据引用，主要知识点为 `knowledge_point_ids[0]`，后续为辅助知识点；服务端合并、重新编号和组卷后才发布，禁止发布未完成的整库结果。
- [x] 管理页面显示 profile/schema/capability 状态，不显示 Prompt 运行快照、密钥或原始响应。

## T09｜回归、迁移与 Labs 验收

- [x] 运行 agents adapter/gateway/recovery、learning review/generation 相关聚焦回归：agents `83 passed`，learning review/generation `24 passed`，管理端 `13 passed`；Gateway/probe/default seed + learning 同进程组合 `49 passed`，证明正式 schema 不再被测试 fixture 污染。
- [x] 增加并验证协议 fixture：OpenAI native、DeepSeek strict tool、Anthropic output tool、json mode best-effort。
- [x] 覆盖 refusal、incomplete、empty、unknown/multiple tool、duplicate key、extra field、结构/语义错误和 repair 上限的 adapter/gateway 逻辑；端到端 attempt 读回已覆盖成功路径。
- [x] 执行 Ruff、Django check、migration drift、Python 编译和 `git diff --check`；隔离 PostgreSQL 正向应用至 `agents.0007` 并读回 capability 字段、两个正式 schema 与空 attempt 表，随后删除隔离库。
- [x] Labs 真实验收完成：service `active/running`、`live=200`、`ready=200`、`agents.0004-0007`、`endpoints=1 / profiles=2 / prompts=2`、`LANGCHAIN_AVAILABLE=True` 和 `uv pip check` 均已读回；本地 Gateway 16 项、完整 agents `83 passed`、知识审核/题库 runtime `24 passed`。两个 profile 共用该 Endpoint，均读回 `SCHEMA_SUPPORTED / native / langchain-openai-1.5.2` 并通过正式启用服务启用；管理员现有文章 Markdown 附件已通过正式知识文档上传服务复制，审核读回 `APPROVED`，题库生成读回 `PUBLISHED / COMPLETE`、一卷 5 题，active reservation 为 0。过程中发现并修复 Provider schema projection、文本 token 估算和 30 秒 read timeout 问题；失败尝试、quota 保护和 reset adjustment 均保留安全事实。
- [x] 清理本轮创建的隔离数据库、Redis DB、媒体、浏览器状态和临时输出。

## 完成门槛

只有 T00-T09 全部完成，且所有聚焦测试、数据读回和 Labs 读回都有新鲜证据，才能将 Goal 标记 complete。任何真实 Provider、生产 migration、共享数据写入、Git 交付或 capability 争议都必须停在对应 Todo 并向用户报告。

## 2026-08-24 语义校验补充

最新 Labs 生成失败已定位为业务校验与动态生成契约不一致，而不是 Endpoint 或网络故障：Provider 两次均返回 HTTP 200，结构化 schema 通过；运行时额外注入了“每个源条目必须生成一个知识点和一题”的一对一指令，且统一题目对象允许模型为客观题填写 `reference_answer`/`scoring_points`，发布校验却把这些题型无关字段判为非法。修复集中在既有 owner：去除一对一提示、将动态数量和源证据白名单写清楚，并在 generation schema 的 normalize 阶段清空不适用字段、为空标签补稳定默认值，再进入语义与发布校验。不得通过降低知识点引用、题型答案或题目数量的安全校验来规避失败。

Labs 验证：Worker 重启后通过页面同一重试 service 重新生成系列 `408b7445-dd3d-4322-909f-7bec2098a52a`；14 个批次最终全部 `ACCEPTED`，其中 1 批首次 `agents.request_timeout.v1` 后有界重试成功。最终 `PUBLISHED / PARTIAL`，两卷 `250+210` 题，知识点 `398/397/1`（总数/覆盖/遗漏），TaskRun `succeeded`，活动模型预留为 `0`。本次没有出现 `agents.response_semantics_invalid.v1`。
