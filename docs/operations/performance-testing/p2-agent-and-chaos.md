# P2：AGENT 参数矩阵、成本和故障恢复任务

状态：未执行

目的：在专用 Endpoint、专用额度和隔离数据下，验证 LangChain/Provider 链路、结构化输出、Schema harness、token 额度、并发、取消、重试和故障恢复。P2 不得直接用未知预算冲击正式 Provider。

本任务对应执行日志：[p2-agent-and-chaos.execution.md](p2-agent-and-chaos.execution.md)。每次执行先生成唯一 `run_id`（建议 `P2-YYYYMMDD-HHMM-序号`），Endpoint、AGENT、Prompt、Schema 和故障注入脚本均需记录版本快照；执行日志只追加真实结果。

## 1. Endpoint 参数矩阵

每个实际启用 Endpoint 至少记录一份结果：

- [ ] `P2-ENDPOINT-01`：Provider 协议：OpenAI/GPT、DeepSeek、Anthropic/Claude。
- [ ] `P2-ENDPOINT-02`：认证模式：无认证、服务器密钥别名、自定义 API Key。
- [ ] `P2-ENDPOINT-03`：Base URL：默认地址、自定义地址、错误路径、不可达地址。
- [ ] `P2-ENDPOINT-04`：Model：有效模型、错误模型、无权限模型、上下文不足模型。
- [ ] `P2-ENDPOINT-05`：reasoning effort：上游支持的每个档位、未设置、错误档位。
- [ ] `P2-ENDPOINT-06`：Claude thinking budget：边界值、与 reasoning effort 冲突、超出输出上限。
- [ ] `P2-ENDPOINT-07`：上下文窗口：短文本、中等文本、接近上限、超出上限。
- [ ] `P2-ENDPOINT-08`：单次输出上限：短输出、长输出、接近上限、截断。
- [ ] `P2-ENDPOINT-09`：单业务运行 token 上限、Endpoint 每日 token 上限。
- [ ] `P2-ENDPOINT-10`：请求超时：最小值、默认值、最大值、上游慢响应。
- [ ] `P2-ENDPOINT-11`：Endpoint 并发：1、2、5 及超过上限的排队/拒绝行为。
- [ ] `P2-ENDPOINT-12`：输入/输出价格估算与实际 usage 对账。

当前代码契约为请求超时 10～600 秒、Endpoint 并发上限 1～5；如果业务仍要求 1800 秒，必须先完成代码、数据库约束、Worker 租约和发布文档的一致性确认。

## 2. AGENT 功能链路

- [ ] `P2-AGENT-01`：Endpoint 连通性检查和 schema capability probe。
- [ ] `P2-AGENT-02`：Prompt 加载、版本快照、AGENT profile 快照。
- [ ] `P2-AGENT-03`：正常结构化输出、字段缺失、类型错误、非法 JSON、Markdown 包裹 JSON。
- [ ] `P2-AGENT-04`：Schema 修复、修复次数上限、修复失败和最终失败。
- [ ] `P2-AGENT-05`：Provider 429、401/403、404、5xx、网络断开和超时。
- [ ] `P2-AGENT-06`：token reservation 创建、使用、结算、释放和过期恢复。
- [ ] `P2-AGENT-07`：失败、拒答和截断是否不扣错误额度。
- [ ] `P2-AGENT-08`：多个文档同时审核或生成题库的并发隔离。
- [ ] `P2-AGENT-09`：同一 Endpoint 多 AGENT 竞争并发和每日额度。
- [ ] `P2-AGENT-10`：取消请求在排队、外呼前、外呼中、外呼后到达时的结果。
- [ ] `P2-AGENT-11`：重试只允许 Provider/网络类异常，且幂等、不重复计数。
- [ ] `P2-AGENT-12`：晚到响应不会覆盖取消、失败或新重试结果。
- [ ] `P2-AGENT-13`：失败通知只包含安全错误原因，不泄露正文、密钥或 Provider 原文。

## 3. 故障注入

- [ ] `P2-CHAOS-01`：Worker 在 reservation 创建后退出。
- [ ] `P2-CHAOS-02`：Worker 在 Provider 返回后、数据库提交前退出。
- [ ] `P2-CHAOS-03`：PostgreSQL 连接在状态更新期间断开。
- [ ] `P2-CHAOS-04`：Redis 在任务排队或轮询期间重启。
- [ ] `P2-CHAOS-05`：Beat 重复派发相同周期任务。
- [ ] `P2-CHAOS-06`：Provider 返回慢响应、空响应、非法 schema 和大响应。
- [ ] `P2-CHAOS-07`：Endpoint 被管理员修改或禁用后，已有 Invocation 使用快照继续执行。
- [ ] `P2-CHAOS-08`：任务租约过期后恢复服务重新协调 TaskRun、业务运行和 reservation。
- [ ] `P2-CHAOS-09`：Outbox/通知发送失败后重试且不重复发送。
- [ ] `P2-CHAOS-10`：服务回退到旧应用镜像后，数据库保持向前且新数据可读。

每个故障注入必须预先登记最大持续时间、最大请求数/Token/费用、预期终态、回滚动作和负责人；不在正式环境注入 PostgreSQL/Redis/Worker 故障。

## 4. 成本与安全门禁

- [ ] 每个测试用例有最大请求数、最大 token、最大金额和最大持续时间。
- [ ] 禁止使用真实用户正文、真实密钥和未授权第三方模型。
- [ ] Provider 费用、输入/输出 token、重试次数和失败 token 分开记录。
- [ ] 测试不会改变正式 Endpoint 的每日配额或长期业务数据。
- [ ] 日志、通知、任务历史和错误聚合均脱敏。

真实 Provider 只允许使用专用 Endpoint、专用测试账户和明确额度；未确认的模型参数不得发送。若代码契约与业务要求（例如请求超时上限）不一致，先记录为配置/实现优化任务，不把不一致的结果判为通过。

## 5. 通过标准

- 配置参数与 Provider 实际行为一致，未知模型不发送未确认参数。
- schema 成功、修复、拒答、截断和失败状态可区分且可恢复。
- 取消、重试、租约恢复和 reservation 结算幂等。
- 失败不发布半成品题库、不覆盖新结果、不重复扣额度。
- 所有 Provider 调用、token、费用、耗时和错误均可按 trace 对账。

结论至少给出：可用参数组合、被拒绝参数及错误码、单 Endpoint 稳定并发、单次/每日额度消耗、失败 token 是否结算、取消/重试/租约恢复耗时、重复或丢失数量，以及进入正式环境前必须完成的优化任务。
