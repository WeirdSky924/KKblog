# E. 公开阅读与发现

所有者：`apps/discovery` 拥有阅读用查询组合、书签、点赞、浏览计数、SEO/sitemap 和公开缓存适配；文章事实仍属于 content，主题账户偏好属于 accounts。

## 内部目录

```text
apps/discovery/
  models/{bookmark,like,view_counter}.py
  services/{bookmarks,likes,views,theme_bridge}.py
  queries/{home,search,sections,tags,article,profiles}.py
  cache/{keys,renderer,invalidation}.py
  seo/{metadata,sitemap}.py
  presentation/{views,forms,presenters}.py
  templates/discovery/{pages,partials}/
  tests/
```

## 查询与排序

- 首页：published_at 倒序，传统页码，默认 20，可选 10/20/50。
- 搜索：默认查文章标题，可切换查公开作者；文章使用 `pg_trgm` 模糊相关度一级、发布时间二级，作者使用精确昵称、昵称前缀和邮箱前缀排序，两类都先执行可见性过滤。登录用户可获得最多五条即时建议，文章建议附分区/标签，未登录固定不返回建议。
- 多标签：最多五个，OR 匹配；匹配标签数倒序，发布时间倒序。
- 分区：只显示有效分区文章；未知分区不在分区入口，但仍在首页/标签。
- 公开主页：只显示该用户已发布且当前访问者可见的文章；空主页可访问。

所有列表使用同一 `ArticleIndexItem` DTO：封面、标题、摘要、分区、标签、发布时间、浏览、评论和点赞数。无上传封面时使用仓库自有 `1600x900` 默认封面；失效收藏使用独立 DTO 和仓库自有 `800x450` 失效图，不假造原文权限，也不复用原文章封面。

## 文章阅读

查询先由 content policy 获得 published revision，再组装安全渲染、H2 目录、动态浏览量/收藏/点赞和评论入口。访客打开登录文章得到提醒页与安全 next；私人、草稿、定时未到、冷静期和永久删除统一 404。

每次进入详情页计一次，包括访客、登录用户和作者；不做时间窗口去重。计数写入使用原子增量，不能因页面刷新缓存覆盖。Umami 是独立全站分析，不替代产品浏览量。

### 登录用户文章划词解释

`apps/discovery` 的阅读页只负责公开文章可见性、选区入口和本地历史展示；Endpoint、AGENT/PROMPT 快照、调用审计、token reservation 由 `apps/agents`，TaskRun/租约/取消由 `apps/operations` 负责。解释能力使用 profile key `article-selection-explanation` 与 `article-selection-explanation.v1`，不复制 Gateway、限流、通知或 Markdown renderer。

服务端每次从公开文章 query 重新组装受限 DTO：清理后的选区、标题、摘要、标签和当前一级标题。图片、图片 alt、链接目标、脚本和外部资源被移除；表格、LaTeX、代码只转为纯文本，不执行任何动作。默认选区上限 1000 字，截断仍请求并返回原始/实际字数；正文其余内容不发送。

阅读页只对登录用户渲染右下角入口、可扩展胶囊和解释面板。面板是固定视口内、可由标题拖动且受视口边界约束的独立区域；中部 `.article-explanation-panel__body` 独立滚动，渲染历史后始终滚到最新记录。浏览器 `localStorage` 使用账户命名空间保存最多配置条数的历史，不作为 AGENT 上下文，也不写服务端正文历史。文章首次请求使用逐文章授权；账户自动接受偏好由 accounts 持有。

请求状态区分 `PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED`。用户停止写入取消终态并丢弃晚到结果；只有 Provider/网络/超时失败允许一次安全重试。客户端对所有解释响应先按文本读取并验证 JSON，HTML 登录页、403、5xx 或空响应映射为安全中文文案，绝不把 JSON 解析异常、响应正文或内部 URL 展示给用户。本期不做流式输出。

## 收藏

仅登录用户可收藏，列表仅本人可见。文章不可访问/删除后保留 bookmark 关系和最小文章 ID，显示“文章已丢失”与统一失效封面；用户自行删除。邮箱/昵称复用不会转移收藏。

## 点赞

仅登录用户可对每篇可读文章保留一个点赞；重复点赞/取消幂等。详情操作只出现在右侧文章快捷浮窗，点赞总数在详情元信息和所有统一文章列表中实时显示。

## 缓存

只缓存 PUBLIC 文章已清洗正文和公开列表静态片段。评论、浏览量、收藏、点赞、账户菜单、通知和遮罩实时读取。发布、重发、可见性、分类、隐藏、删除、恢复、作者禁用/启用均失效相关 key。缓存命中前仍确认当前公开策略。

## SEO 与分享

SEO 标题使用文章标题，描述为正文纯文本前 100 字；只把 PUBLIC 文章加入 sitemap 和搜索引擎索引。AUTH/PRIVATE/个人/管理页使用 noindex。分享只复制 ULID 永久链接。

## 主题

三主题由 design token 驱动。访客选择保存在浏览器；登录后 Account theme 是跨设备事实，浏览器即时切换后通过 accounts 服务同步。未登录到登录时以账户偏好覆盖，不混合两套 source of truth。

## 页面

首页、搜索、分区、标签、文章、登录提醒、404、公开主页、收藏，以及 navigation 提供的 About/友情链接/留言板入口。页面/HTMX 契约见统一映射。

## 验证

可见性直接 URL、登录回跳、搜索不泄露标题、五标签排序、10/20/50 页码、缓存命中后遮罩变化、浏览量并发、收藏失效/恢复、sitemap/noindex、三主题跨设备/浏览器行为。

施工依据：`contracts/03-frontend-contract-map.md`、`data/04-indexes-constraints.md`、`03-frontend-design-system.md`。
