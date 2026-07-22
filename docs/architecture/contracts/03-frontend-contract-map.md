# 页面、HTMX 与服务契约映射

URL 是建议的命名空间契约，实施时以 Django `reverse()` 名称为稳定引用，模板禁止手写路径。完整页面返回基础布局，HTMX 端点只返回同领域 partial。

## 公共与阅读页面

| URL name | 页面/模板 | 查询/命令 | HTMX 局部 | 必测状态 |
| --- | --- | --- | --- | --- |
| `public:home` | `discovery/home.html` | `visible_article_page` | 文章索引、标签筛选、页码 | 10/20/50、五标签 OR、空结果 |
| `public:section` | `discovery/section.html` | `articles_in_section` | 列表/页码 | 未知/删除分区不可导航 |
| `public:tag` | `discovery/tag.html` | `articles_for_tags` | 列表/筛选 | 删除标签为空、恢复后读回 |
| `public:search` | `discovery/search.html` | `search_visible_titles` | 结果/页码 | 模糊、相关度+时间、权限过滤 |
| `article:detail` | `discovery/article_detail.html` | `article_for_reader`, `record_view` | 评论区、收藏状态 | 登录提醒、私人/草稿 404、目录 H2 |
| `article:bookmark` | partial action | `toggle_bookmark` | 收藏按钮 | 登录要求、重复点击幂等 |
| `public:profile` | `accounts/public_profile.html` | `published_articles_by_author` | 文章列表 | 空主页、不同调用者可见性 |
| `public:about` | `navigation/static_page.html` | `published_static_page` | 无 | 无内容 404/隐藏入口 |
| `public:friend-links` | `navigation/friend_links.html` | `visible_friend_links` | 无 | 安全新标签、缺图 |
| `public:guestbook` | `comments/thread_page.html` | `guestbook_thread` | 评论列表/表单 | 开关、访客、登录、举报 |
| `public:not-found` | `errors/404.html` | 安全错误映射 | 无 | 不泄露对象存在 |

文章首屏的静态正文可缓存，浏览量、收藏和评论由独立查询组装。分享按钮只复制当前永久链接，不调用第三方平台。

## 身份与个人页面

| URL name | 页面 | 服务 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `accounts:login` | 密码/邮箱码同页 tabs | authenticate/request code | 30 天选项、忘记密码仅密码 tab、限制提示、回跳 |
| `accounts:register` | 直接/邀请码模式 | validate invite/request code/register | 注册关闭仍可邀请码；发送按钮；成功自动登录 |
| `accounts:password-reset` | 重置表单 | request/reset password | 第 5 次码错误、每日限制、全部会话撤销 |
| `accounts:settings` | 资料/凭证/主题 tabs | change profile/email/password | 昵称冷却、头像预览、当前密码、新邮箱码 |
| `accounts:sessions` | 设备会话表 | revoke session(s) | 当前会话、退出其他、退出所有二次确认 |
| `accounts:bookmarks` | 私人收藏 | bookmark_page | 失效专属图、用户手动删除 |
| `notifications:list` | 全量通知 | notifications_for/mark read | 未读、单条展开、一键全读、空态 |

全局 Header：左上 Logo/主题切换；动态管理员导航；头像左侧通知控件；未登录显示登录/注册，登录后显示圆形头像、昵称/账号和个人菜单。通知 hover 浮层固定五条；点击条目打开完整浮层，不跳页；“查看全部”跳通知页。

## 作者工作台

| URL name | 页面 | 所有者/服务 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `authoring:articles` | 我的文章 | content queries | 已发布、草稿、定时、冷静期、空态 |
| `authoring:create` | 格式选择 | create_article | Markdown/富文本一经选择普通流程不可改 |
| `authoring:edit` | 编辑器+预览 | save_revision/media | 本地自动保存、云保存、磁盘限制、冲突 |
| `authoring:review` | 全文终稿审查 | prepare/publish/schedule | 返回编辑、立即/定时、退出存草稿 |
| `authoring:versions` | 历史时间线 | revision queries/restore | 版本元数据、恢复预览、创建新修订 |
| `authoring:comments-buffer` | 缓冲卡片 | buffered_comments/delete | 10 分钟倒计时、删除确认 |
| `authoring:comments-article` | 按文章评论 | comment queries/delete | 树、占位、关闭评论区 |
| `authoring:import` | 上传/预览/结果 | exchange import | 逐篇选择、分区/标签映射、部分成功 |

编辑器桌面并列编辑/实时预览；手机使用“编辑/预览”分段切换。TipTap 和 Markdown 使用不同输入组件，但共同调用安全预览、媒体选择、版本令牌和发布审查组件。

本地草稿存储键至少含 `user_id + article_id + base_revision_id + format`，防止账号/文章串稿。服务端保存成功前不得删除本地内容。

## 管理员页面

| URL name | 页面 | 委托领域 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `admin:users` | 用户/作者管理 | accounts | 搜索、状态、授予/撤销、禁用/启用、删除 |
| `admin:ip-blocks` | IP 管理 | accounts | 掩码列表、详情全值、备注、解除 |
| `admin:articles` | 全文章管理 | content/moderation | 查看通知、隐藏/恢复、删除/恢复、申诉 |
| `admin:comments` | 评论卡片/tabs | comments | 缓冲、按文章、直接删除理由 |
| `admin:reports` | 举报/申诉审核 | moderation | 初审、证据、举报人隐私、终局复审 |
| `admin:tags` | 标签审核/历史 | content | 通过、拒绝、删除、恢复关联冲突 |
| `admin:sections` | 分区 | content | 唯一名称、删除转未知分区 |
| `admin:invites` | 邀请码 | accounts | 1..1000 生成、一次显示原码、筛选/撤销/使用者 |
| `admin:notifications` | 群发 | notifications | 全体用户、读回、隐藏/恢复/删除 |
| `admin:navigation` | 三层拖拽树 | navigation | 站内页/分区/外链、隐藏、移动端预览 |
| `admin:site-settings` | 分组设置 | navigation/core/media | 品牌、注册、Logo、正文限制、可信来源、法律页 |
| `admin:exchange` | 导出任务 | exchange | 单全局任务、取消、下载、三天到期 |
| `admin:audit` | 审计检索 | operations | 关键字、类型、目标、时间、前后值 |
| `admin:errors` | 错误检索 | operations | 错误码、trace、脱敏详情 |
| `admin:tasks` | 任务记录 | operations | 运行/成功/最终失败，无手动重试 |
| `admin:analytics` | Umami | analytics | 同源认证入口、不可公网直达 |

不建立空洞的管理仪表盘首页。个人菜单中的“管理”直接进入上次/默认的首个功能入口，移动端管理侧栏变为可滚动模块导航，所有写动作仍使用一致确认弹窗。

## HTMX 响应规范

- 成功局部更新返回领域 partial，并通过响应事件触发 toast、badge 或焦点恢复。
- 表单校验失败返回同一表单 partial，HTTP 422，错误紧邻字段，保留输入。
- 并发冲突返回 409 的冲突 partial；不得被全局错误 toast 吞掉。
- 权限过期返回完整登录提醒/重定向约定；HTMX 请求使用 `HX-Redirect` 到同源登录并带安全 next。
- 后台 Job 接受返回 202 语义状态块；轮询/事件只显示真实 Job 状态。
- 删除/隐藏确认弹窗提交时禁用重复点击；失败后保留原因和证据。

## 前端组件所有权

| 组件 | 唯一位置 | 消费者 |
| --- | --- | --- |
| `site_header` / `personal_menu` | `templates/components/navigation/` | 全站 |
| `notification_popover` | `notifications/partials/` | Header |
| `article_index_row` | `discovery/partials/` | 首页、搜索、分区、标签、主页 |
| `comment_thread` | `comments/partials/` | 文章、留言板、管理预览 |
| `confirm_dialog` | `templates/components/feedback/` | 全站命令 |
| `media_picker` | `media/partials/` | 编辑器、头像、评论、证据、设置 |
| `pagination` / `cursor_loader` | `templates/components/navigation/` | 传统分页/无限加载分别复用 |
| `admin_table_shell` | `administration/partials/` | 管理列表，不承载领域规则 |

共享组件只接受展示 DTO 和 capability flags，不查询 ORM、不自行判断角色、不发起未知领域命令。

## 每页验收模板

每个页面实现时填写：入口身份、初始查询、主要动作、pending、成功、字段错误、系统错误、空态、禁用态、404/登录态、桌面 1440、手机 390、键盘路径、数据库读回和 Playwright 场景编号。
