# 需求到架构追踪矩阵

本表用于检查 322 项访谈决策是否有施工落点。它按行为簇聚合；实现时仍以原始 Q 条目为验收输入。多个范围表示同一主题在后续访谈中被补充或修正。

| 需求范围 | 主题 | 主要架构落点 |
| --- | --- | --- |
| Q001-Q013、Q254、Q317 | 文章可见性与评论默认 | article state、authorization、comments state |
| Q014-Q035、Q226-Q229 | 身份、登录、验证码、密码、禁用 | account state、accounts module、identity fields |
| Q036-Q053、Q262-Q264、Q296-Q298、Q321 | 格式、草稿、发布、冲突、版本恢复 | ArticleRevision、article state、authoring module |
| Q038-Q045、Q093-Q096、Q113-Q116、Q123-Q125、Q164、Q230、Q318 | 全站图片用途、默认资产与解码安全上限 | media module、storage lifecycle、field dictionary、requirements resolution |
| Q046-Q047、Q284、Q315 | 删除冷静期、账户/文章永久删除 | article state、storage lifecycle、DB deletion strategy |
| Q054-Q060、Q256-Q258、Q280 | 分区、标签、审核、恢复 | content module、fields、constraints |
| Q061-Q068、Q242-Q243、Q289、Q305-Q309 | 通知、已读、浮层、聚合 | notifications module、event registry、frontend map |
| Q069-Q087、Q135-Q138、Q234-Q235、Q273 | 首页、搜索、筛选、阅读、SEO、缓存 | discovery module、indexes、frontend map |
| Q088-Q092、Q166-Q173 | 三主题、中文、响应式、美术与无障碍 | frontend design system、discovery module |
| Q097-Q103、Q244-Q246、Q295 | 昵称、公开主页、设置、会话、身份复用 | accounts fields/state、frontend map |
| Q104-Q116、Q259-Q261 | 评论管理、排序、加载、占位 | comment state/module、frontend map |
| Q117-Q125、Q287、Q308-Q313 | 举报、申诉、直接删除、留言板 | moderation flow/module、authorization |
| Q126-Q134、Q249-Q252 | 邀请码、注册模式、用户管理 | accounts module/state、frontend map |
| Q139-Q140、Q319-Q320 | Umami 全站分析与一月保留 | exchange/analytics module、tasks |
| Q141-Q147、Q266-Q268 | 开发/测试仅 localhost、生产关闭失败、端口与容器内网 | operations overview、requirements resolution |
| Q148-Q157、Q265、Q288 | 正文存储、Redis、备份与邮件供应商 | storage lifecycle、ADR-002/004/006、exchange module |
| Q158-Q165、Q209-Q210、Q236-Q241、Q247-Q248、Q253 | 品牌、法律页、导航、友情链接、设置 | administration/navigation module、frontend design |
| Q174-Q186 | Git、部署、迁移、回滚、维护页 | project plan、import/export sequences、roadmap |
| Q187-Q190、Q192-Q203 | 秘密、审计、错误与 trace | events/errors、platform/operations modules |
| Q191 | 管理员兼作者使用标准评论/回复能力 | accounts/comment authorization、CMT-002/CMT-003、QA-002 |
| Q204-Q208、Q286 | 初始唯一管理员与安全引导 | account state、requirements resolution、ADR-005 |
| Q211-Q225 | 技术栈、依赖、测试、任务政策 | system directory、platform module、task contract |
| Q231-Q233、Q316 | 外链、HTML、可信嵌入与 sanitizer | media/rendering module、frontend design |
| Q255、Q290 | 发布后可见性与受限直链 | article state、authorization、discovery module |
| Q269-Q272 | 监控、告警、磁盘保护 | storage lifecycle、background tasks、operations module |
| Q274 | 完整实现后统一部署 | project plan、implementation roadmap |
| Q275-Q283 | Markdown 安全限额导入、管理员导出、并发与保留 | import/export sequences、exchange module、tasks、requirements resolution |
| Q285、Q291、Q299-Q301 | 作者角色、所有权、禁用后的文章 | account/article state、authorization |
| Q292-Q294 | 匿名防滥用、永久 IP 封禁与 IP 留存 | account/comment state、security fields |
| Q302-Q307、Q311 | 管理员内容例外、通知、申诉 | ADR-005、authorization、article/moderation state |
| Q314 | 正文默认 `2 MiB`，可配 `64 KiB..2 MiB` | content fields、site settings、capacity validation、requirements resolution |
| Q322 | 无外部 API/第三方登录 | system overview、ADR-003、frontend contract |

## 使用方法

实现一个切片时，在测试计划中引用具体 Q 编号和本表落点。若某条需求在对应文档中找不到字段、状态、服务、页面或验收中的至少一个落点，先补设计；不要把它留给 View 中临时判断。

需求变化后同时更新原始访谈/变更记录、消歧表、本矩阵和受影响施工文档。只有矩阵行存在不等于功能完成，完成证据以 `delivery/02-module-verification-matrix.md` 为准。
