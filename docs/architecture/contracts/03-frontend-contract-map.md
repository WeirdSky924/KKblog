# 页面、HTMX 与服务契约映射

URL 是建议的命名空间契约，实施时以 Django `reverse()` 名称为稳定引用，模板禁止手写路径。完整页面返回基础布局，HTMX 端点只返回同领域 partial。

## 公共与阅读页面

| URL name | 页面/模板 | 查询/命令 | HTMX 局部 | 必测状态 |
| --- | --- | --- | --- | --- |
| `public:home` | `discovery/home.html` | `visible_article_page` | 文章索引、标签筛选、页码 | 列表作者 ID/公开主页、左侧导航展开/收起/本地恢复、10/20/50、五标签 OR、空结果 |
| `public:section` | `discovery/home.html` | `articles_in_section` | 主页文章区域/列表/页码 | 列表作者 ID/公开主页、侧栏同页切换、刷新保持主页结构、未知/删除分区不可导航 |
| `public:tag` | `discovery/tag.html` | `articles_for_tags` | 列表/筛选 | 列表作者 ID/公开主页、删除标签为空、恢复后读回 |
| `public:search` | `discovery/search.html` | `search_visible_titles`, `search_public_author_page` | 文章/作者结果与页码 | 文章列表作者 ID/公开主页、作者公开主页、模糊、相关度+时间、权限过滤 |
| `public:search-suggestions` | Header JSON | `search_visible_titles`, `search_public_authors` | 登录用户即时建议 | 未登录固定空结果、文章分区/标签、作者头像、最多五条、无缓存 |
| `article:detail` | `discovery/article_detail.html` | `article_for_reader`, `record_view`, `reading_bookmark_progress`, `article_like_count` | 评论区、收藏、点赞与阅读书签状态 | 作者头像/ID/公开主页、登录提醒、私人/草稿 404、TipTap JSON projection/Markdown 兼容目录 H2、恢复阅读位置 |
| `article:explanation-create` / `article:explanation-status` | 文章阅读页划词解释面板 | `prepare_article_explanation_context`, `create_article_explanation_request`, `article_explanation_request` | JSON 任务状态与安全 Markdown HTML；前端 localStorage 历史 | 仅登录且文章公开可读；选区清理/长度截断；授权、限额、PENDING、SUCCEEDED、FAILED、CANCELLED；非 JSON/HTML 响应显示安全中文错误 |
| `article:bookmark` | partial action | `toggle_bookmark` | 收藏按钮 | 登录要求、重复点击幂等 |
| `article:like` | `discovery/partials/like_control.html` | `set_article_like` | 右侧浮动点赞按钮、详情/列表计数 | 登录要求、固定尺寸、重复点击幂等 |
| `article:comment-pin` | `comments/partials/public_list.html` | `set_article_comment_pin` | 评论首屏重排、置顶状态 | 仅文章作者/管理员、仅公开顶层、无整页闪烁 |
| `article:reading-bookmark` | JSON action | `save_reading_bookmark` | 右侧阅读书签按钮 | 登录要求、正文相对进度 `0..1`、同账户同文章原位更新 |
| `public:profile` | `discovery/public_profile.html` | `visible_articles_by_author` | 文章列表 | 空主页、不同调用者可见性 |
| `public:about` | `navigation/static_page.html` | `published_static_page` | 无 | 无内容 404/隐藏入口 |
| `public:friend-links` | `navigation/friend_links.html` | `visible_friend_links` | 无 | 名称/描述、安全新标签、无 Logo 依赖 |
| `public:guestbook` | `comments/thread_page.html` | `guestbook_thread` | 评论列表/表单 | 开关、访客、登录、举报 |
| `opportunities:index` | `opportunities/index.html` | `public_opportunities`, `public_opportunity_sources`, `public_opportunity_filters`, `public_opportunity_summary` | `opportunity-workspace` | 岗位/来源/我的收藏三视图、同组 OR/组间 AND、搜索提交、即时复选/每页、历史/焦点/滚动恢复、企业发布时间与岗位名称排序、空态 |
| `opportunities:bookmark` | `opportunities/partials/bookmark_button.html` | `set_opportunity_bookmark` | 稳定收藏控件 | 未登录安全回跳、登录幂等持久化、实心图标、通用反馈、仅看收藏取消后刷新 |
| `question-banks:index` | `learning/question_bank_index.html` | `public_question_bank_page` | 列表/搜索/筛选/分页 | 最新/最多答题/题量排序、组内 OR/组间 AND、访客与登录一致、空结果 |
| `question-banks:detail` | `learning/question_bank_detail.html` | `public_question_bank_detail` | 无 | 隐藏/删除 404、题面/答案/解析安全投影、登录答题入口 |
| `api-v1:question-bank-list` | JSON envelope | API gate + limiter + `public_question_bank_page` | 无 | 默认 404/api_disabled、429、503、CORS、分页/ETag、无对象查询泄露 |
| `api-v1:question-bank-detail` | JSON envelope | API gate + limiter + `public_question_bank_detail` | 无 | 开关关闭一致 404、开启 not_found、完整安全题库 projection |
| `public:not-found` | `errors/404.html` | 安全错误映射 | 无 | 不泄露对象存在 |

文章首屏的静态正文可缓存，浏览量、收藏、点赞、阅读书签和评论由独立查询组装。阅读书签保存正文内归一化进度，避免视口变化后绝对像素失效；分享按钮只复制当前永久链接，不调用第三方平台。

## 身份与个人页面

| URL name | 页面 | 服务 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `accounts:login` | 密码/邮箱码同页 tabs | authenticate/request code | 30 天选项、忘记密码仅密码 tab、限制提示、回跳 |
| `accounts:register` | 直接/邀请码模式 | validate invite/request code/register | 注册关闭仍可邀请码；发送按钮；成功自动登录 |
| `accounts:password-reset` | 重置表单 | request/reset password | 第 5 次码错误、每日限制、全部会话撤销 |
| `accounts:settings` | 资料/凭证/主题 tabs | change profile/email/password | 昵称冷却、头像预览、当前密码、新邮箱码 |
| `accounts:sessions` | 设备会话表 | revoke session(s) | 当前会话、退出其他、退出所有二次确认 |
| `accounts:bookmarks` | 私人收藏 | bookmark_page | 可用文章作者 ID/公开主页、失效专属图、用户手动删除 |
| `notifications:list` | 全量通知 | notifications_for/mark read | 未读、单条展开、一键全读、空态 |
| `learning:documents` | 我的知识文档 | owner document queries/submit | 权限入口、逐次声明、上传、待审/审核中/终态、删除/恢复 |
| `learning:document-detail` | 文档状态与访问历史 | owner document detail/appeal/retry | 原文仅本人、访问历史隐藏管理员身份、申诉 Markdown、异步局部读回 |
| `learning:bank-generate` | 题库生成配置/结果 | generate_question_bank | 标题/简介、题型 Switch、完整/部分覆盖、失败重试 |
| `learning:quiz-start` | 答题配置与模式 | create_quiz_attempt | 考试/刷题选择（默认考试）、题型多选、题量、随机题目/选项、软计时 |
| `learning:quiz-attempt` | 考试/刷题作答与结果 | save/submit_quiz_response/submit_quiz_attempt | 自动保存不揭晓；考试整套提交；刷题逐题提交后只揭晓该题；简答自评、跨设备冲突、超时后继续 |
| `learning:wrong-book` | 错题本 | wrong questions/set mastery | 题库分组、TO_REVIEW/MASTERED、错题练习 |
| `learning:records` | 答题记录 | records/delete/export | 详情、复选删除/清空、CSV、防公式注入、删除冷静期 |

全局 Header：左上 Logo/主题切换；头像左侧通知控件；未登录显示登录/注册，登录后显示圆形头像、昵称/账号和个人菜单。搜索默认查文章，可切换作者；登录用户输入时显示最多五条即时建议，未登录不请求也不渲染建议层。管理员配置的公共导航只显示在首页可收起的左侧浮层，不进入 Header；分区节点和其他导航节点使用同一排序结果。点击分区节点只替换主页文章区域，标题、列表、分页 URL 和节点选中态同步更新；直接访问或刷新分区 URL 仍返回完整主页结构。通知 hover 浮层固定五条；点击条目打开完整浮层，不跳页；“查看全部”跳通知页。

## 作者工作台

| URL name | 页面 | 所有者/服务 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `authoring:articles` | 我的文章 | authoring 编排；accounts 申请服务/状态查询；content queries | 作者看到既有工作台；普通登录用户看到一次性申请/已提交状态；未登录回登录 |
| `authoring:create` | 创建方式选择 | create_article/exchange import | Markdown/富文本/导入三选一；空白文章格式一经选择普通流程不可改 |
| `authoring:edit` | 编辑器+预览 | save_revision/media | 本地自动保存、云保存、磁盘限制、冲突、剪贴板图片上传/撤销/失败 |
| `authoring:review` | 全文终稿审查 | prepare/publish/schedule | 返回编辑、立即/定时、退出存草稿 |
| `authoring:versions` | 历史时间线 | revision queries/restore | 版本元数据、恢复预览、创建新修订 |
| `authoring:comments-buffer` | 缓冲卡片 | buffered_comments/delete | 10 分钟倒计时、删除确认 |
| `authoring:comments-article` | 按文章评论 | comment queries/delete | 树、占位、关闭评论区 |
| `authoring:import` | 创建入口的上传/预览/结果 | exchange import | 兼容旧 URL；逐篇选择、分区/标签映射、部分成功，单篇成功进入编辑 |

编辑器桌面并列编辑/实时预览；手机使用“编辑/预览”分段切换。TipTap 和 Markdown 使用不同输入组件，但共同调用安全预览、媒体选择、版本令牌和发布审查组件。

剪贴板图片必须调用既有 `article-body` 上传端点并沿用其格式、大小、权限和未绑定资源清理规则。前端最多接受同一批十张图片并串行上传，在粘贴位置保留不可持久化的临时标记；成功后换成 `media:<ULID>`，撤销后只保留图片库资源，失败后清除标记。存在待上传图片时，编辑器不得提交云端保存或用 `.md` 导入覆盖正文，并应在离页前提示。

富文本图片拖入复用同一批次上限、临时标记和串行上传合同，并按命中位置插入；选中图片的替换上传在成功前保留旧 revision 引用，成功后以单个可撤销 transaction 更新 `src`，alt/title/宽度保持不变。图片节点宽度只允许 `25/50/75/100`，删除节点只改变未保存正文，不绕过 media owner 删除服务器资产。

富文本 attachment node 只能由有附件能力的作者通过既有 picker 插入或替换，document 最多一个，attrs 只含 `src: media:<ULID>`。前端文件名/MIME/大小来自 picker 的当前授权资产，公开卡片来自 revision binding 的 media 授权元数据；未授权作者不渲染上传或插入入口，隐藏 UI 不替代服务端拒绝。

编辑器表单内所有媒体写入共用一个 upload tracker：任务状态只允许 `pending/success/error/cancelled`，进度、AbortSignal、取消、同文件重试和关闭由 tracker 投影到固定上传浮窗。任一任务为 pending 时，云端保存、Markdown 覆盖和离页都必须由同一 pending count 阻断；取消或失败不写媒体字段，成功后才更新 picker 或发出 TipTap transaction。TipTap 失败占位可以留在原位置等待重试，但序列化 JSON、本地草稿和服务端 revision 都不得包含 `kaj-upload:` 临时引用。

编辑大纲只遍历当前 ProseMirror/TipTap JSON 的 H1-H6；`anchor` 缺失、非法或重复时由 heading extension 生成唯一安全值，改名和移动保留，复制去重并与同一历史步骤撤销恢复。桌面默认展开，窄屏默认折叠，条目激活后设置正文 selection 并只滚动编辑容器。公开 TipTap 目录消费 content/media 的 outline projection 并保留 renderer 已输出的 `id`；不得解析或重写 sanitized HTML。Markdown 仍沿用历史 H2 兼容目录。

编辑/预览定位由 `editor-preview-scroll` 单一 owner 维护：Markdown 使用服务端 block start lines，TipTap 使用 selection 文档位置和 top-level block ratio；预览目标为可视高度的 2/3，但 `scrollTop` 始终 clamp 到 `0..maximum`，上方内容不足时必须从顶部开始且禁止伪元素前置留白。预览主动滚动把状态从 `following` 切为 `paused`，selection/content 更新不隐式恢复；替换预览 DOM 后按原滚动比例恢复。只有“继续跟随编辑位置”命令返回 `following`，执行后焦点落回预览正文。

版本和 409 冲突界面的块级变化只显示 before/after 总数及新增、删除、移动、类型变化、内容变化计数。content 拥有有界比较，authoring presenter 拥有标签与方向文案；模板不得接收正文 diff、文本片段、媒体 ID 或内部哈希。块复制/删除继续复用 block menu 的独立可撤销事务，不产生第二套操作入口。

本地草稿与 409 恢复必须把 TipTap JSON 和唯一 `attachmentAssetId` 作为一个一致快照；旧草稿仅可从唯一合法 attachment node 推导缺失字段。刷新、选择新基线和 HTMX workspace 替换后，正文 node、附件 hidden field 与 picker 状态同步恢复；字段/node 错配时显示本地稿不可读并保留云端事实，不把失败恢复伪装为成功。

本地草稿存储键至少含 `user_id + article_id + base_revision_id + format`，防止账号/文章串稿。服务端保存成功前不得删除本地内容。

## 管理员页面

| URL name | 页面 | 委托领域 | 关键状态/弹窗 |
| --- | --- | --- | --- |
| `admin:users` | 用户/作者管理 | accounts | 搜索、状态、授予/撤销、禁用/启用、删除 |
| `admin:ip-blocks` | IP 管理 | accounts | 掩码列表、详情全值、备注、解除 |
| `admin:articles` | 全文章管理 | content/moderation | 居中只读预览弹窗、工作版本/发布历史切换、查看通知、隐藏/恢复、删除/恢复、申诉 |
| `admin:comments` | 评论卡片/tabs | comments | 缓冲、按文章、直接删除理由 |
| `admin:reports` | 举报/申诉审核 | moderation | 初审、证据、举报人隐私、终局复审 |
| `admin:tags` | 标签审核/历史 | content | 通过、拒绝、删除、恢复关联冲突 |
| `admin:sections` | 分区 | content/media | 唯一名称、可空默认封面 picker、编辑弹窗、删除转未知分区并释放封面 |
| `admin:invites` | 邀请码 | accounts | 1..1000 生成、一次显示原码、筛选/撤销/使用者 |
| `admin:notifications` | 群发 | notifications | 全体用户、读回、隐藏/恢复/删除 |
| `admin:navigation` | 三层拖拽树 | navigation | 站内页/分区/外链统一排版；父级切换自动建议位置；插入后移、删除补位 |
| `admin:site-settings` | 分组设置 | navigation/core/media | 品牌、注册、Logo、Hero 图片/视频、正文限制、可信来源、法律页 |
| `admin:article-explanation-settings` | 文章解释设置 | navigation/agents/operations | 用户每日/每分钟解释次数、选区上限、本地历史条数；与 Endpoint/AGENT token 配置分离 |
| `admin:exchange` | 导出任务 | exchange | 单全局任务、取消、下载、三天到期 |
| `admin:audit` | 审计检索 | operations | 关键字、类型、目标、时间、前后值 |
| `admin:errors` | 错误检索 | operations | 错误码、trace、脱敏详情 |
| `admin:tasks` | 任务记录 | operations | 运行/成功/最终失败，无手动重试 |
| `admin:analytics` | Umami | analytics | 同源认证入口、不可公网直达 |
| `admin:opportunities` | 工作机会五标签 | opportunities | 审核队列支持接受当前页与确认后接受全部待审核；来源/岗位 dialog；任务历史按来源分页并以 dialog 按需展示新增/更新岗位；检查仅创建持久任务，不同步抓取 |
| `admin:agent-endpoints` | AI 配置/Endpoint | agents | 运行参数、模型匹配的 reasoning effort/旧版 thinking budget、秘密别名、启停、连接检查、双层 token 上限/用量与 reset |
| `admin:agent-profiles` | AI 配置/AGENT 与 Prompt | agents | profile 绑定、Markdown Prompt 修订/预览、当前版本切换、并发 409 |
| `admin:learning-documents` | 知识文档与申诉 | learning | 有界分页、逐条原文访问、显式勾选批量处置、申诉逐条决定 |
| `admin:question-banks` | 题库与运行设置 | learning | 配额、生成上限、API 开关与账户覆盖；队列通过独立入口管理 |
| `admin:question-bank-queue` | 题库队列 | learning | HTMX 局部筛选、生成/可见性状态、隐藏/恢复/删除、显式勾选批量、冷静期读回 |
| `admin:question-bank-api` | 题库 API 设置 | learning | 默认关闭、分钟/每日限流、精确 HTTPS Origin 白名单、用量摘要 |

不建立空洞的管理仪表盘首页。个人菜单中的“管理”直接进入上次/默认的首个功能入口，移动端管理侧栏变为可滚动模块导航，所有写动作仍使用一致确认弹窗。

## HTMX 响应规范

- 成功局部更新返回领域 partial，并通过响应事件触发 toast、badge 或焦点恢复。
- 管理文档与题库队列的筛选只替换对应列表 partial，并用 `hx-push-url` 保留可分享的筛选参数；无 HTMX 时保留完整页面回退。
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
| `article_explanation_tools` | `static/src/article-explanation.js` + `discovery.css`/文章模板 | 登录文章页 | 账户命名空间 localStorage、选区按钮、授权 dialog、可拖动面板、内部滚动和停止/重试状态；不拥有 AGENT、限流或 Markdown 业务规则 |

共享组件只接受展示 DTO 和 capability flags，不查询 ORM、不自行判断角色、不发起未知领域命令。

## 每页验收模板

每个页面实现时填写：入口身份、初始查询、主要动作、pending、成功、字段错误、系统错误、空态、禁用态、404/登录态、桌面 1440、手机 390、键盘路径、数据库读回和 Playwright 场景编号。
