# P6 阅读与发现（8）

退出门禁：首页、阅读、搜索、标签、分区、收藏、主页、主题、SEO 和公开缓存完成。

### DSC-001 实现全站 Header、Footer、主题与身份导航外壳
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P1。
- 目标/行为：全站显示默认 K/自定义 Logo、站名、动态公开导航、搜索、主题、登录/注册或头像菜单；通知控件预留；Footer 显示站名/年份/可选版权与法律链接。
- 来源：访谈 Q088-Q092、Q158-Q173、Q236、Q241-Q243；`03-frontend-design-system.md` §页面骨架；原型首页/个人页。
- 依赖：前置 `RUN-005`、`MED-005`、`ACC-007`；后续 `DSC-002`、`DSC-005`、`OBS-002`、`ADM-006`、`QA-003`、`QA-006`。
- 文件：base layout components、theme JS/bridge、header/footer presenters、Playwright。
- 边界：公开导航数据归 navigation；通知归 notifications；本任务只组装；访客主题浏览器存、登录后账户主题为真值。
- 影响：数据：Account theme/站点DTO只读；权限：身份菜单；审计无；缓存：静态shell谨慎；异步无；媒体：Logo/avatar；通知：占位接入。
- 测试/验收：Playwright 亮/暗/护眼、未登录→登录偏好覆盖、键盘/hover/触控、1440/390/768、长站名无重叠。
- 风险/停止：重复主题 source、Header 缓存串用户、移动导航遮挡或按钮只靠文字圆角替代熟悉图标即停止。
- 证据：RED `.venv/bin/pytest apps/discovery/tests/test_dsc001.py -q` 收集期退出 2，准确报告 `apps.navigation` 公开站点投影缺失。新增 navigation owner 的只读 `SitePresentation`/三层 `NavigationItem` 契约与默认 K/站名投影，不提前建立 P11 的树/设置模型；全站 Header/Footer 组装动态导航、搜索入口、三主题、访客/登录身份、通知槽、个人菜单、上海年份、可选版权/法律链接和站内 Logo/favicon，accounts 主题入口继续调用唯一 `change_profile` 服务并保留非 JS 回跳。真实 PostgreSQL/Redis/Mailpit 聚焦 GREEN 与账户资料、并发、前端基础、架构回归退出 0，`32 passed`；登录态 Header 切换后 PostgreSQL 读回 `DARK`，访客本地 `DARK` 登录后由账户 `LIGHT` 覆盖且页面无邮箱。`/usr/local/bin/blog-playwright-cli` 在 1440/768/390 对长站名、亮/暗/护眼、桌面 hover、触控导航、Escape 焦点恢复和 skip-link 实际操作，控制台 0 error、三视口横向溢出 0，原尺寸截图检查无重叠/遮挡；首次静态 404 验收无效后以 `--insecure` 项目测试入口重启并重验，首次 CSS hover 面板 0 尺寸缺陷也修复后重验为 208x255。Ruff lint/format、Django check、migration drift、完整 npm build 与 `git diff --check` 均退出 0。搜索结果属于 DSC-004、收藏页属于 DSC-006、通知浮层属于 P8、导航/站点管理写服务属于 ADM-006/007；当前只提供诚实入口/槽位，未执行生产配置、生产迁移、Git 交付或部署。
- 授权：`否`。

### DSC-002 实现首页文章索引、卡片 DTO 与传统分页
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P1。
- 目标/行为：首页只列当前调用者可见发布文章，按首次实际发布时间倒序；默认20，可选10/20/50，传统页码；卡片含封面/标题/摘要/分区/标签/时间/浏览/评论。
- 来源：访谈 Q069、Q079-Q082、Q234-Q235；`modules/05-discovery-reading.md` §查询与排序；`contracts/03-frontend-contract-map.md` §public:home。
- 依赖：前置 `CNT-003`、`CNT-005`、`DSC-001`；后续 `DSC-003`、`DSC-004`、`DSC-006`、`DSC-007`、`DSC-008`、`QA-003`、`QA-006`。
- 文件：discovery home query/ArticleIndexItem/presenters/templates/partials/tests。
- 边界：首版不做点赞；不显示草稿/私人给无权者；动态浏览/评论数不进入静态整页缓存；标题最多两行不挤压。
- 影响：数据：发布投影查询；权限：actor过滤；审计无；缓存：公开静态片段；异步无；媒体：封面；通知无。
- 测试/验收：RED 顺序/稳定二级键/页码边界/空态；Playwright 10/20/50、空/错误/长标题、1440/390。
- 风险/停止：先分页再授权导致漏/泄露、缓存串 AUTH 或动态计数陈旧覆盖即停止。
- 证据：本地聚焦 RED 覆盖可见性先于计数/分页、发布时间与 ULID 稳定二级排序、页边界、10/20/50、AUTO/CUSTOM/NONE 摘要和发布修订分类快照；真实浏览器 RED 在 HTMX 页码切换后观察到两个 `#article-index` 且焦点停留 `BODY`，根因为目标内部默认替换。实现由 content owner 的 `visible_article_page` 统一执行 actor 可见性、遮罩、排序和分页，discovery 只转换共享 `ArticleIndexItem`，局部页码和每页数量改为 `outerHTML` 替换并在交换后聚焦新索引；当前浏览/评论 owner 尚未实施，卡片诚实显示 0，留待 DSC-005/P7 接入动态事实。隔离 PostgreSQL 查询断言退出 0：访客/登录总数 `21/22`，访客 10 条分页为 `10/10/1`、登录第三页为 2，第二页首项“阅读与发现文章 11”，相同发布时间按 ULID 倒序，21 条发布修订的分区/标签快照与 DTO 一致，非法 11 条页宽抛出稳定错误。content 发布/权限/作者遮罩及架构/前端契约回归退出 0，`27 passed`；Ruff lint/format、Django check、migration drift、npm build 和 `git diff --check` 均退出 0。`/usr/local/bin/blog-playwright-cli` 以真实 21 PUBLIC + 1 AUTH 数据验证访客不泄露 AUTH 标题、10/20/50、空态、422、安全 500、长标题两行、HTMX URL/数据/键盘焦点，并在 1440/768/390 与亮/暗/护眼主题检查无重叠或横向溢出；最终读回单一索引、焦点 `article-index`、控制台 0 error/0 warning。未执行生产配置、生产迁移、部署或当前进度后的 Git 交付。
- 授权：`否`。

### DSC-003 实现分区页、标签页与最多五标签 OR 筛选
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P1。
- 目标/行为：分区入口只展示有效分区；首页最多选五标签，OR 匹配，匹配数优先再按发布时间；删除标签旧链接为空、恢复后关联重现。
- 来源：访谈 Q054-Q060、Q082-Q084、Q256-Q258；`modules/05-discovery-reading.md`；`data/04-indexes-constraints.md` §标签/分区索引。
- 依赖：前置 `CNT-010`、`CNT-011`、`DSC-002`；后续 `DSC-008`、`ADM-006`、`QA-003`、`QA-006`。
- 文件：section/tag queries、filter forms/HTMX partials、pagination/tests。
- 边界：未知分区不在分区入口但仍可从首页/标签发现；超过5标签字段错误；待审标签按文章可见规则显示。
- 影响：数据：ArticleTag/发布投影只读；权限：内容过滤；缓存：query generation；审计/异步/媒体/通知无。
- 测试/验收：RED 0/1/5/6标签、OR计数/稳定排序、删除/恢复、未知分区；Playwright 多选换行/移动端筛选。
- 风险/停止：AND误实现、排序不稳定或已删标签缓存继续展示即停止。
- 证据：临时聚焦 RED `.venv/bin/pytest -q apps/discovery/tests/test_dsc003.py` 首次收集退出 2，准确报告 `discovery_filters` 等查询能力缺失；补充权限 RED 退出 1，证明仅私人文章使用的待审标签可被猜测 UUID 泄露名称。content owner 在同一 reader-scoped QuerySet 上增加分区条件、最多五个唯一标签的 OR 过滤与 `matched_tag_count DESC, published_at DESC, id DESC` 稳定排序，筛选选项也只从调用者可见的发布修订生成；discovery 只组装筛选 DTO、分页表单和页面，ACTIVE/公开待审标签可导航、私人待审/REJECTED 对无权者统一 404、DELETED 旧标签链接保持 200 空态并在恢复后重现。聚焦 GREEN 退出 0，`3 passed`，临时测试及生成缓存随后清理；正式内容发布/权限/作者遮罩/分区/标签与架构/前端契约回归退出 0，`34 passed`。隔离 PostgreSQL 最终读回退出 0：1 个有效分区、7 个访客可筛标签、首页 27 篇，三标签 OR 命中 23 篇且三项命中文章排在两项命中之前，分区页 27 篇，标签服务删除 1 条关联后旧链接为 0、恢复 1 条且冲突 0 后页面回到 1 篇；0/1/5 接受、6 返回稳定 422，重复同一标签参数规范化为 1。`/usr/local/bin/blog-playwright-cli` 真实操作复选框、HTMX 筛选、传统分页、分区/标签卡片链接、未知分区 404、标签删除空态与恢复读回；三标签参数跨键盘分页保留，交换后单一索引且焦点正确，六标签错误保留输入并聚焦错误。浏览器验收还修复原生 checkbox 被文字层拦截、选择计数不更新、HTMX 旧 target 覆盖错误焦点及 fieldset 4rem 断词；亮/暗/护眼与 1440/768/390 原尺寸截图无重叠，三视口横向溢出 0，移动触控目标 44px，最终干净会话控制台 0 error/0 warning。Ruff lint/format、Django check、migration drift、npm build 与 `git diff --check` 均退出 0；现有 FK/标签文章索引满足该只读切片，无 schema 变更。未执行生产配置、生产迁移、部署或本轮 Git 交付。
- 授权：`否`。

### DSC-004 实现仅标题的模糊搜索与权限安全排序
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P0。
- 目标/行为：只搜索标题，使用 PostgreSQL pg_trgm 相关度一级、发布时间二级；在相关度计算前限制调用者可见发布修订，不索引正文。
- 来源：访谈 Q058、Q076-Q078、Q135-Q137；`data/04-indexes-constraints.md` §标题相关度；`contracts/03-frontend-contract-map.md` §public:search。
- 依赖：前置 `CNT-005`、`DSC-002`；后续 `DSC-008`、`QA-002`、`QA-003`、`QA-006`。
- 文件：search query/index migration、form/HTMX result、中文样本/tests。
- 边界：首版不引入 Elasticsearch/全文正文搜索；搜索错误/计数不能泄露私人标题；ULID链接稳定。
- 影响：数据：trigram索引；权限：先过滤；缓存：公开搜索可短TTL；审计/异步/媒体/通知无。
- 测试/验收：RED 相似标题/并列时间/PRIVATE-AUTH泄露/空查询；EXPLAIN与真实PostgreSQL结果；Playwright搜索/分页/空态。
- 风险/停止：查询先算全站相似度再过滤、正文命中或阈值无中文样本校准即停止。
- 证据：临时聚焦 RED `.venv/bin/pytest -q apps/discovery/tests/test_dsc004.py` 首次收集退出 2，准确报告 `search_article_page` 缺失；首次实现因未安装 `django.contrib.postgres` 暴露配置缺口，补齐后聚焦 GREEN 退出 0，`3 passed`，临时测试及缓存随后清理。content owner 先复用统一 reader scope，再以事务局部 `pg_trgm.similarity_threshold`、标题 `trigram_similar` 与短中文 `icontains` 补充匹配，按 `similarity DESC, published_at DESC, id DESC` 排序；正文不参与，访客查询“星云关键词”只返回 PUBLIC 标题，不返回正文命中、AUTH 或 PRIVATE 标题。真实中文/混合样本把阈值从 `0.3` 校准至 `0.2`，`PostgreS` 命中“PostgreSQL 标签文章”，`筛选`命中两条标题；PostgreSQL migration 应用退出 0，catalog 读回 `pg_trgm` 与 `article_rev_title_trgm_gin`，强制 planner 使用 GIN。最终参数化数据读回退出 0；首次 catalog 脚本仅因 shell 引号失配退出 1，搜索断言已执行，改参数化 SQL 后成功。相关发布/权限/遮罩/分区/标签与架构/前端回归退出 0，`34 passed`；Django check、migration drift、Ruff lint/format、npm build 与 `git diff --check` 均退出 0。`/usr/local/bin/blog-playwright-cli` 验证初始提示、键盘模糊搜索、空态、25 条分页、10/20/50 参数保留、HTMX 单一索引与焦点；空白查询返回 422、保留三个空格并聚焦 alert，常驻 loading indicator 无缺失错误，控制台只有浏览器对预期 422 的资源记录，正常流 0 error/0 warning。浏览器 RED 另读回搜索页 H1 仅 `16px`，补齐共享页面标题规则后为 `28px/1.35`；亮/暗/护眼及 1440/768/390 原尺寸截图无重叠，横向溢出 0。未执行生产 migration、生产缓存、部署或本任务后的 Git 交付。
- 授权：`否`。

### DSC-005 实现文章阅读、H2 目录、复制链接与浏览计数
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P0。
- 目标/行为：文章页组装安全发布正文、真实封面、仅H2目录、复制ULID链接；每次进入详情原子+1含作者；访客读AUTH先看提醒页并登录回跳，其他无权状态404。
- 来源：访谈 Q070-Q072、Q085-Q087、Q137、Q290；`modules/05-discovery-reading.md` §文章阅读；原型 article。
- 依赖：前置 `CNT-005`、`MED-004`、`MED-007`、`DSC-001`；后续 `DSC-008`、`QA-002`、`QA-003`、`QA-006`。
- 文件：article query/page、TOC parser、view counter service、login gate/safe next、tests。
- 边界：分享不接社交平台；浏览量不是Umami；目录不含H1/H3；404文案不能区分私人/删除/草稿。
- 影响：数据：原子浏览计数；权限：读取矩阵/安全next；缓存：正文静态+动态计数分离；媒体：封面/正文；审计/异步/通知无。
- 测试/验收：RED 四身份×状态、并发计数、恶意next、H2解析；Playwright 登录提醒→登录→回原文、复制链接/移动目录。
- 风险/停止：浏览计数被页面缓存覆盖、open redirect、404差异或未清洗正文即停止。
- 证据：临时聚焦 RED `.venv/bin/pytest -q apps/discovery/tests/test_dsc005.py` 收集退出 2，准确报告 `apps.discovery.queries.article` 缺失。新增 discovery 自有 `ArticleViewCounter` 一对一事实与 PostgreSQL `INSERT ... ON CONFLICT ... count + 1 RETURNING` 原子服务，不保存访问者、IP 或窗口；40 线程 GREEN 精确返回 `1..40`，详情每次成功进入递增，登录提醒与 404 均不计数，首页同批动态读回 40。首次 GREEN 为 `1 passed, 2 failed`，失败仅因测试把 publish 时钟放在审查 token 过期后；统一 prepare/publish 时钟后聚焦退出 0，`3 passed`。content reader query 在权限成功后通过 media owner 的修订绑定快照与统一 sanitizer 生成安全 HTML/可读封面，discovery 只做 H2 结构解析、稳定锚点与页面组装；一次架构回归暴露 discovery 直接导入 media 的反向依赖后下沉 owner，最终 0 违规。migration 仅应用隔离库并完成 `0001 -> zero -> 0001`；首次 catalog 读回发现 Django ORM CASCADE 的数据库 FK 实为 NO ACTION，修正为显式 `discovery_view_article_fk` 后重新读回 `ON DELETE CASCADE DEFERRABLE`、文章主键一对一与非负 CHECK。聚焦及 content/media 联合回归退出 0，`32 passed`；删除临时测试后 accounts 回跳、content 读取/删除/遮罩、media 授权/渲染及架构/前端正式回归退出 0，`58 passed`，Django check、migration drift、Ruff lint/format、npm build 与 `git diff --check` 均退出 0。`/usr/local/bin/blog-playwright-cli` 验证公开详情安全正文、默认封面、H2 两项目录且 H1/H3 排除、复制链接、刷新计数 `2 -> 3` 与首页实时读回 3；访客 AUTH 提醒不泄露标题，登录链接只带 canonical 同源 next，键盘密码登录后回原 ULID，PRIVATE 访客统一 404。手机目录可用 Space 开合并保持焦点；亮/暗/护眼与 1440/768/390 原尺寸截图无重叠，横向溢出 0，当前代码干净会话控制台 0 error/0 warning。未执行生产 migration、生产数据、部署或本任务后的 Git 交付。
- 授权：`否`。

### DSC-006 实现私人收藏与失效文章占位
- 元数据：状态 `完成`；阶段 P6；owner `discovery`；优先级 P1。
- 目标/行为：登录用户幂等收藏/移除；列表仅本人；文章变私人/删除/不可访问仍保留关系，显示“该文章已丢失”及仓库自有 `800x450` 统一失效图，由用户手动移除；恢复可访问后恢复正常。
- 来源：访谈 Q070、Q073-Q075；`modules/05-discovery-reading.md` §收藏；DEC-005。
- 依赖：前置 `ACC-005`、`CNT-005`、`DEC-005`、`DSC-002`；后续 `AUT-001`、`QA-002`、`QA-003`、`QA-006`。
- 文件：Bookmark model/service/query、lost DTO/asset、views/templates/tests。
- 边界：管理员不能代看；不保留已删文章原封面/标题；账户删除级联，身份复用不转移。
- 影响：数据：Bookmark；权限：本人；审计无；缓存：状态实时；异步无；媒体：统一失效图；通知无。
- 测试/验收：RED 重复收藏、他人列表、可见性/删除/恢复、账户删除重用身份；资产尺寸/引用检查；Playwright 正常/失效/移除并确认不泄露或复用原封面。
- 风险/停止：占位泄露旧标题/封面、自动删收藏或缓存越权即停止。
- 证据：一次性聚焦 RED `.venv/bin/pytest -q apps/discovery/tests/test_dsc006.py` 收集退出 2，准确报告 `Bookmark` 缺失；实现 discovery 自有 Bookmark、显式期望状态 `bookmarked=True/False` 的幂等 service、本人分页 query 与有效/失效分离 DTO，聚焦 GREEN 退出 0，`4 passed`，临时测试随后删除。保存前复用 content owner 的当前 reader scope，列表批量复用统一 `ArticleIndexItem`；不可访问项只含文章 ULID、收藏时间、固定“该文章已丢失”和仓库自有 `800x450` 失效图，不保存或渲染旧标题/旧封面。Bookmark 对文章不建 FK，文章 PRIVATE、软删除、恢复和物理删除均保留关系；Account 使用显式 `discovery_bookmark_account_fk ON DELETE CASCADE DEFERRABLE`，账户删除后同邮箱新 UUID 读回 0 条。隔离 migration `0001 -> 0002 -> 0001 -> 0002` 全部退出 0；PostgreSQL catalog 读回唯一约束、分页索引、唯一外键只指向 `account` 且 `confdeltype='c'`，无 Article FK。文章详情接入 `article:bookmark` HTMX 原位控件，`accounts:bookmarks` 由 config 组合 accounts 与 discovery 路由，个人菜单改用 `reverse`；匿名普通/HX 请求分别安全登录跳转，422 可交换且动态状态均 `private, no-store`。最终 content 删除/权限、accounts 会话/删除、media 品牌资产、架构与前端回归退出 0，`43 passed`；Ruff lint/325 文件格式、Django check、migration drift、npm build 与 `git diff --check` 均退出 0。`/usr/local/bin/blog-playwright-cli` 以独立普通读者真实完成登录回原文、收藏、本人列表、PUBLIC→PRIVATE 失效且原标题不出现、PUBLIC 恢复、Space 键移除和空态；亮/暗/护眼与 1440/768/390 原尺寸视觉检查无重叠，三视口 `scrollWidth == innerWidth` 且目标容器无溢出，控制台 0 error/0 warning。未执行生产 migration、生产数据、部署或 Git 交付。
- 授权：`否`。

### DSC-007 实现公开用户主页与空态
- 元数据：状态 `进行中`；阶段 P6；owner `discovery`；优先级 P1。
- 目标/行为：评论昵称/头像可进入公开主页；页面仅展示调用者可见的已发布文章，无文章仍可访问空态，不展示邮箱、角色、安全资料或收藏。
- 来源：访谈 Q101-Q103；`modules/05-discovery-reading.md` §查询；`contracts/02-authorization-matrix.md` §账户与个人数据。
- 依赖：前置 `ACC-007`、`DSC-002`、`CNT-005`；后续 `QA-003`、`QA-006`。
- 文件：profile article query/presenter/template/links/tests。
- 边界：主页属于阅读投影，不在 accounts 复制文章查询；被禁用作者文章隐藏；匿名/注销评论无链接。
- 影响：数据：只读账户+发布文章；权限：可见性；缓存：仅公开安全投影；媒体：头像；审计/异步/通知无。
- 测试/验收：RED 空主页、AUTH文章按调用者差异、禁用作者、已删账户；Playwright从评论进入及直接URL。
- 风险/停止：公开DTO包含邮箱/内部UUID或缓存把登录可见列表给访客即停止。
- 授权：`否`。

### DSC-008 实现 SEO、sitemap 与公开缓存失效
- 元数据：状态 `待处理`；阶段 P6；owner `discovery`；优先级 P0。
- 目标/行为：PUBLIC文章可索引并进入 sitemap；标题为SEO标题、正文纯文本前100字为描述；AUTH/PRIVATE/个人/管理 noindex；只缓存公开清洗正文/列表。
- 来源：访谈 Q135-Q138、Q255、Q273；`modules/05-discovery-reading.md` §缓存/SEO；`data/05-storage-lifecycle.md` §缓存边界。
- 依赖：前置 `DSC-002`、`DSC-003`、`DSC-004`、`DSC-005`、`CNT-009`；后续 `QA-003`、`QA-004`、`QA-006`。
- 文件：seo metadata/sitemap、cache keys/renderer/invalidation consumers、tests。
- 边界：不实现RSS；评论/浏览/收藏/菜单/通知/遮罩不缓存；缓存命中前重判公开策略；sanitizer版本入key。
- 影响：数据：发布投影读；权限：PUBLIC-only；缓存：发布/重发/可见/分类/隐藏/删除/恢复/禁用全失效；异步：outbox消费者；媒体：渲染引用；审计/通知无。
- 测试/验收：RED 缓存命中后各遮罩、Redis flush、sitemap/noindex、描述去HTML；真实请求/缓存键读回。
- 风险/停止：缓存成为事实、私密内容进入搜索引擎或失效事件重复产生错误状态即停止。
- 授权：`否`。

[返回总索引](../implementation-todolist.md)
