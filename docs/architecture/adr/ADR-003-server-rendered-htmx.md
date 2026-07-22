# ADR-003：服务端渲染与局部增强

状态：Accepted

## Context

产品是阅读、写作和管理工具，需要 SEO、直接链接、权限一致、移动端和大量表单/弹窗，但没有首版公共 API 或移动 App。完整 SPA 会增加第二套路由、认证、状态和 API DTO。

## Decision

使用 Django Templates 生成完整页面，HTMX 负责搜索、分页、评论、表格和表单局部更新，Alpine.js 只管理弹窗、主题和文件预览等局部浏览器状态。TipTap 是富文本编辑器的专门例外。

服务端 Query/Policy 是页面事实来源；HTMX partial 与完整页复用同一展示 DTO 和模板片段。不建设通用 JSON API。

## Consequences

- 权限、SEO 和错误处理集中，首屏与直接 URL 自然工作。
- 需要严格定义完整页/partial 边界、422/409 和焦点恢复。
- 复杂离线协作不是当前目标；本地草稿单独用浏览器存储。
- 将来若有移动 App，再从稳定服务契约设计 API，而不是暴露现有内部端点。

## Rejected alternatives

- React/Next.js SPA：对当前同源工作流增加重复状态与 API 成本。
- 纯模板无增强：评论无限加载、管理筛选和编辑器体验不足。

## Revisit when

出现明确的外部客户端、离线优先或高频实时协作需求，并且服务契约已经稳定。
