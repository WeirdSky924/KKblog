# H. 管理后台、导航与站点设置

`apps/administration` 是管理页面编排层；`apps/navigation` 拥有导航树、静态页面、友情链接和公开站点结构。账户、内容、审核、通知、运维等命令仍由各领域 owner 执行。

## 内部目录

```text
apps/administration/
  navigation_registry.py       # 管理模块入口注册，不是公开导航树
  presentation/{users,content,comments,settings,operations,exchange}.py
  presenters/{tables,actions,filters}.py
  templates/administration/{layout,partials,<feature>}/
apps/navigation/
  models/{navigation_node,static_page,friend_link,site_configuration}.py
  services/{tree,static_pages,friend_links,site_settings}.py
  policies/admin.py
  queries/{public_navigation,admin_tree,public_pages}.py
```

## 管理后台原则

- 不建立无内容仪表盘首页；从个人菜单进入直接功能入口。
- 模块侧栏/手机横向导航由代码注册表定义；业务导航树由数据库管理，二者不混用。
- 表格、筛选、确认弹窗可复用外壳；领域字段、错误和 action 仍由 owner DTO 提供。
- Django 原生 admin 只用于紧急只读诊断或低风险内部表；高风险写入不得绕过 service/audit。

## 管理功能面

用户/作者/IP、文章查看/隐藏/删除/恢复与申诉、评论/举报、标签/分区、邀请码、群发通知、导航树、品牌/静态页/可信来源/限制设置、导入导出、审计/错误/任务、Umami，以及独立一级组“AI 配置”和“智能与题库”。“AI 配置”只编排整个项目共用的 agents Endpoint、AGENT、Prompt、token 设置；“智能与题库”承载 learning 的配额、文档/申诉、题库运行设置、独立题库队列和 API 设置。这些页面在侧边导航中同级展示，不直接读写两域私有模型。

管理员查看他人文章有受通知只读例外；不能编辑、发布、排期或转移。所有写动作进入正式领域命令并永久审计。

## 导航树

节点类型：仅分组、站内页、文章分区、外链；最多三层；同 parent 下稳定排序；可隐藏不删除。仅分组节点不保存目标且只有存在可见子项时才公开；有链接父项的文字继续导航，独立箭头只控制子项，GROUP 整行控制子项。父节点可配置默认展开，叶节点不能开启；移动或删除最后一个子项后服务自动恢复折叠。该状态只决定页面初始值，本页手动操作不写跨页面偏好。分区不必固定放入“分区”菜单，管理员可拖到任何合法位置。

拖拽提交包含整棵受影响子树的版本令牌。服务在事务中校验：无环、深度 <=3、目标存在、外链 URL 安全、排序连续。冲突返回最新树，不做静默覆盖。

## 站点与公开内容

- SiteConfiguration：站名（默认 Kaj的小房间）、可空描述、版权、注册开关、正文限制、Logo/Hero 资产、可空的验证码 HTML 模板，以及文章解释和专注模式的全站策略。
- “文章阅读设置”管理用户级划词解释额度与本地历史上限，以及专注模式无操作分钟数（1..15，默认 3）和每次专注手动暂停上限（1..10，默认 3）。设置统一由 navigation service 校验管理员身份、锁定 singleton、比较 `row_version` 并写 AuditEntry；发现页只读已验证的配置 DTO。
- Logo：默认 CSS/矢量纯色 K；管理员 PNG/ICO 覆盖并作为 favicon。
- Hero：管理员从共享媒体 picker 选择受限图片或视频；空值使用仓库默认图。视频以默认图为 poster，只在真正播放后覆盖 poster，并提供播放/暂停控制；自动播放失败或 `prefers-reduced-motion` 时保留 poster。
- StaticPage：About、Privacy、Terms，支持 Markdown/富文本；空内容不显示入口/同意框。
- FriendLink：名称、HTTPS URL、描述、排序；管理员 CRUD。公开页和 Footer 均不依赖 Logo。
- TrustedEmbedSource：管理员增删，初始仅 Bilibili；删除后旧嵌入占位。
- 验证码邮件模板：管理员上传不超过 48 KiB 的 UTF-8 HTML 或恢复代码内默认模板；只允许白名单标签、样式与 `site_name/code/minutes/purpose` 变量，必须包含 `code`，审计只记录摘要、是否自定义和版本。

秘密、连接串、SMTP 密钥和 `.env` 不进入任何网页设置或 audit payload；模板正文、验证码和收件人也不进入审计。

## UI 与响应式

桌面窄侧栏 + 主工作区，页面标题保持紧凑；手机模块导航横向滚动/菜单，表格重排关键字段与 overflow actions。确认弹窗明确目标、影响、可选原因/证据和不可逆性。长邮箱/ID/trace 不挤压动作。

## 验证

- 每个管理 URL/POST 使用普通用户和作者伪造请求均拒绝。
- 管理表单成功后领域数据库、通知和审计三方读回。
- 三层树拖拽、并发版本、隐藏/恢复、仅分组的空目标与可见子项过滤、父节点默认展开与失去最后子项后的自动复位、分区目标删除、外链安全。
- 空 About/法律页不显示；配置后即时出现；站点 Logo/favicon 切换；Hero 默认图、图片、视频、失败 poster 与减少动态效果；友情链接无 Logo、排序连续且安全外链。
- 所有管理独立页面、筛选、空/错误/禁用/弹窗在 1440/390 操作可达。
- AI 配置页面验证管理员权限、秘密不回显、Prompt Markdown 预览、Endpoint/AGENT 共用配置入口和并发冲突；智能与题库页面验证显式勾选批量边界、逐条原文访问、API 默认关闭与配额/限流设置的并发冲突。

施工依据：`contracts/03-frontend-contract-map.md`、`contracts/04-events-errors.md`、`03-frontend-design-system.md`。
