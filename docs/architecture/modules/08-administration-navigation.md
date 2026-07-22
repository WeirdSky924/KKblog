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

用户/作者/IP、文章查看/隐藏/删除/恢复与申诉、评论/举报、标签/分区、邀请码、群发通知、导航树、品牌/静态页/可信来源/限制设置、导入导出、审计/错误/任务和 Umami。

管理员查看他人文章有受通知只读例外；不能编辑、发布、排期或转移。所有写动作进入正式领域命令并永久审计。

## 导航树

节点类型：站内页、文章分区、外链；最多三层；同 parent 下稳定排序；可隐藏不删除。外链安全新标签，移动端子项可展开。分区不必固定放入“分区”菜单，管理员可拖到任何合法位置。

拖拽提交包含整棵受影响子树的版本令牌。服务在事务中校验：无环、深度 <=3、目标存在、外链 URL 安全、排序连续。冲突返回最新树，不做静默覆盖。

## 站点与公开内容

- SiteConfiguration：站名（默认 Kaj的小房间）、可空描述、版权、注册开关、正文限制、品牌资产。
- Logo：默认 CSS/矢量纯色 K；管理员 PNG/ICO 覆盖并作为 favicon。
- StaticPage：About、Privacy、Terms，支持 Markdown/富文本；空内容不显示入口/同意框。
- FriendLink：名称、URL、描述、Logo、排序；管理员 CRUD。
- TrustedEmbedSource：管理员增删，初始仅 Bilibili；删除后旧嵌入占位。

秘密、连接串和 `.env` 不进入任何网页设置或 audit payload。

## UI 与响应式

桌面窄侧栏 + 主工作区，页面标题保持紧凑；手机模块导航横向滚动/菜单，表格重排关键字段与 overflow actions。确认弹窗明确目标、影响、可选原因/证据和不可逆性。长邮箱/ID/trace 不挤压动作。

## 验证

- 每个管理 URL/POST 使用普通用户和作者伪造请求均拒绝。
- 管理表单成功后领域数据库、通知和审计三方读回。
- 三层树拖拽、并发版本、隐藏/恢复、分区目标删除、外链安全。
- 空 About/法律页不显示；配置后即时出现；Logo/favicon 切换。
- 所有管理独立页面、筛选、空/错误/禁用/弹窗在 1440/390 操作可达。

施工依据：`contracts/03-frontend-contract-map.md`、`contracts/04-events-errors.md`、`03-frontend-design-system.md`。
