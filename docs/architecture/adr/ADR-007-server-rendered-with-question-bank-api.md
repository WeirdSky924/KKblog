# ADR-007：服务端页面与题库只读 API 例外

状态：Accepted

## Context

ADR-003 选择 Django Templates + HTMX，并基于“没有公共 API”拒绝通用 JSON 层。后续知识题库需求明确需要第三方匿名读取公开题库，同时站内题库、答题、管理和编辑仍是同源页面工作流。把内部 HTMX 暴露为 API 会泄露页面状态与权限细节；为整个站点建设通用 API 又会扩大认证、版本和维护面。

## Decision

继续以 Django Templates 生成完整页面、HTMX 做局部增强，服务端 policy/query 是页面事实来源。新增唯一受控例外：独立 `/api/v1/question-banks` JSON transport，只提供公开题库列表和详情的匿名 GET/HEAD。

HTML 与 JSON 复用 `apps.learning` 的 `public_question_bank_page/detail` filter DTO 与 projection，但 transport 独立承担：

- 默认关闭的 PostgreSQL 配置 gate；关闭时在对象查询前统一 `404/api_disabled` 与 `no-store`。
- 可信客户端 IP 的 Redis 原子分钟/每日限流；Redis 故障在 query 前 `503/rate_limiter_unavailable`，站内 HTML 不受影响。
- 管理员精确 HTTPS Origin 白名单、无 credentials、预检、`Vary: Origin`、ETag 和版本化 JSON/error envelope。
- 固定页码分页与 OpenAPI 合同；内部字段、原知识文档、Prompt、模型输出和个人学习数据永不进入 projection。

首版不提供 AGENT、上传、答题或管理写 API，不提供 API key 和 `ANY_ORIGIN`。内部 HTMX/JSON 辅助端点不成为公共合同。

## Consequences

- 站内和第三方读取共享可见性与筛选事实，避免两套题库规则。
- API 需要独立维护 schema 版本、限流、CORS、缓存和外部兼容性测试。
- API 故障可以 fail closed 而不拖垮站内 HTML，但 Redis 限流不可用时外部调用会暂时中断。
- 默认关闭降低意外暴露；管理员启用前必须显式配置并审计。

## Rejected alternatives

- 暴露 HTMX endpoints：它们是页面 partial，不是稳定或安全的外部 DTO。
- 同 URL 依赖 Accept 协商：会混合 HTML/API 错误、缓存和 gate 语义。
- 通用全站 REST API：当前没有客户端需求，增加不必要的认证与维护面。
- Redis 故障时放行或内存回退：多进程不可一致，会绕过管理员限额。

## Revisit when

需要认证 API、写操作、任意来源 CORS、移动 App 或除题库外的新公共资源时，重新裁决认证、授权、配额、版本和迁移，不静默扩大本例外。
