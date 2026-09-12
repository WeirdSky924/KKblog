# Kaj 空间下一轮更新公告（持续记录）

状态：本轮已于 2026-09-12 完成正式增量部署；后续 Labs 迭代继续沿用本文件记录。

## 发布基线

- 当前正式版本：`87621e82180242ec6b04aeb61e474d6774064daa`。
- 当前正式应用镜像：`kaj-blog-web:87621e821802`。
- Labs worktree：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- Labs 分支：`codex/labs-next-iteration`。
- Labs 分支从正式版本的祖先继续迭代；当前未提交的 Labs 修改尚未视为正式发布。
- 9 月 5 日合并发布公告：[2026-09-05 合并增量更新公告](../2026-09-05-production-increment/announcement.md)。
- 上一轮正式公告：[2026-09-02 正式增量更新公告](../2026-09-02-production-increment/announcement.md)。

## 已继承的正式能力

下一轮公告必须保留上一轮已发布能力的事实口径，当前基线包括：

- 公开作者主页和文章列表的批量统计、可见性策略及公开列表查询优化。
- 通知中心的局部响应、合并未读查询，以及右上角通知浮窗按内容自然撑开、不显示内部滚动条。
- 标签筛选、文章目录、阅读书签、点赞和文章动作的现有组件、权限与 HTMX 流程。
- 分析采集路径修正，避免重复的 `/analytics/analytics/collect` 请求。
- 招聘检查的 PostgreSQL 断连、过期租约和孤儿运行恢复；每日 18:00 调度前会检查失效活动运行。
- 文章公开列表和通知可见时间索引：`content.0017`、`notifications.0002`。
- 答题中心的单题浏览、题号导航、自动保存、提交后答案与解析查看，以及知识文档/题库的分页和任务状态反馈。
- Markdown/Tiptap 编辑、代码块、LaTeX 块、文章导入和统一安全渲染链路。
- 找工作岗位发布时间排序、分页筛选、收藏视图、来源适配器和任务历史恢复能力。

## 下一轮新增内容

每完成一个 Labs 修改切片，必须在本节追加一条真实记录，至少说明：

- 用户可见行为或修复点；
- 受影响的页面、服务或数据 owner；
- 验证命令/页面和结果；
- 是否涉及迁移、状态修复、来源抓取或生产风险；
- 后续正式部署需要执行的动作。

本轮已完成分页统一与查询性能审查：

- 将文章、作者搜索、收藏、招聘、学习、管理、评论、审计、任务、导出、备份、会话、标签历史、版本时间线等页码列表统一接入 `templates/components/navigation/pagination.html`（文章索引使用的共享分页组件）；保留评论树和通知收件箱的 keyset/cursor 语义。
- 所有新增页码入口均把 QuerySet 交给 Django `Paginator`，只读取当前页并批量查询当前页关联数据；管理文章案件、评论标题、标签历史、题库生成历史、访问审计等关联查询均限制在当前页 ID 集合内。
- 复用 `apps.core.pagination.page_window` 作为统一页码窗口实现，保留筛选、弹窗和多列表的独立页码参数；未对固定配置选项、题库详情完整题目和媒体库等非页码详情列表强制改造。
- 验证：Ruff、Python compileall、Django check、146 个模板加载烟测、公开主页回归（5 passed）、Labs 健康接口和招聘分页真实浏览器点击均通过；未执行生产迁移或 Git 交付。

本轮补充了共享分页栏的显示规则：

- 分页组件现在在总页数为 1 时也渲染当前页码 `1`，不再要求出现第二页才显示页码列表；
- “每页”选择器由共享组件统一渲染，并固定在页码导航右侧；主页、搜索、收藏、作者主页和招聘列表均复用同一结构，切换每页数量时保留当前筛选字段并回到第一页；
- 验证：共享模板单页烟测通过；`git diff --check`、Ruff、Python compileall、Django check 均通过；Labs `https://labs.kajspace.cn/health/live` 返回 `200`，主页真实读回显示页码 `1`、右侧“每页”和 `per_page`；Playwright 在 390px 视口确认无横向溢出且选择器位于分页栏右侧；未执行迁移、生产部署或 Git 交付。
- 相关回归命令 `.venv/bin/python -m pytest -q apps/discovery/tests/test_public_profile.py apps/discovery/tests/test_search.py` 结果为 `5 passed, 5 errors`；5 个错误均发生在 SQLite 测试库初始化执行现有 `ALTER TABLE ... ADD CONSTRAINT` 迁移时，未进入测试逻辑，需在 PostgreSQL 隔离环境补跑。

本轮补充删除冷静期恢复入口：

- 作者文章列表的“删除冷静期”状态现在为可恢复文章显示明确的“恢复”按钮，提交时携带行版本并复用 `restore_deleted_article` 的权限、期限和并发校验；成功后回到恢复前的发布状态列表，过期、冲突和无权操作分别返回对应状态。
- 管理员文章列表对没有管理案件的作者主动删除文章提供直接恢复确认，对已有管理案件的文章继续走案件恢复流程；知识文档和题库管理队列对管理员删除的冷静期对象提供单项恢复入口，复用既有批量预检、审计和通知服务。
- 验证：作者恢复视图、管理员恢复确认、作者/管理员模板烟测通过；Ruff、Python compileall、Django check 和 `git diff --check` 通过；Labs `/author/articles/` 未登录返回 `302`，恢复端点未登录返回 `302`，管理员入口继续按权限返回 `403`；未执行迁移、生产状态修复或 Git 交付。文章删除恢复 pytest 因既有 SQLite `ALTER TABLE ... ADD CONSTRAINT` 迁移错误无法启动，需在 PostgreSQL 隔离环境补跑。

本轮完成 Labs 基线与发布记录整理：

- 复核 `kaj-labs.service` 工作目录为 `/home/code/.codex-worktrees/personal-blog/labs-test-environment`，服务保持 `active/running`；`https://labs.kajspace.cn/health/live` 返回 `200`。
- Labs 分支 `codex/labs-next-iteration` 的 Git HEAD 已从 `82df3cc` 对齐到正式远端 `origin/main=02ea58b4eaa0b7d1c2728231c292f6e0a8df8a97`；旧 HEAD 由本地回溯引用 `refs/codex/backups/labs-next-iteration-before-formal-baseline` 保留，未推送。
- 将 9 月 5 日两阶段记录合并为 `docs/releases/2026-09-05-production-increment/`，旧阶段目录改为 README 指向唯一正式记录，避免后续公告分叉。
- 现有 Labs 未提交代码、模板、测试和文档修改均保留；本轮没有迁移、状态修复、来源抓取、生产部署或 Git 提交/推送。
- 验证：合并目录文件与正式文档逐项核对，`git diff --check -- docs/releases` 通过；后续切片继续追加到本公告，并在正式候选形成前逐项核对。

本轮修复正式环境知识文档上传失败与错误提示：

- 媒体存储在创建最终目录或执行原子提交时遇到文件系统写入错误，现在由上传端点返回可重试的 `503` 安全分片，不再升级为无上下文的 `500`；内部异常细节不会返回给用户。
- 前端上传模块新增“知识文档”类型识别，校验失败、网络失败和服务端存储失败均不再回退显示“图片上传未完成”。
- 验证：隔离 PostgreSQL/Redis/Mailpit 的 `apps/media/tests/test_med009_knowledge_documents.py` 为 `17 passed`；Labs 真实端点带作者权限上传 Markdown 返回 `201`，资产读回 `ACTIVE`、文件存在，响应包含知识文档成功文案且不包含图片回退文案；测试会话和临时文件已清理，保留的数据库行仅为既有删除生命周期历史记录。
- Labs `kaj-labs.service`、Worker、Beat 保持 `active/running`，`/health/live` 和 `/health/ready` 均返回 `200`；已生成新的 `static/dist/app.js` 并更新模板缓存版本。未执行生产目录权限修复、生产状态清理、迁移、提交或推送；正式部署时需同时核对媒体目录归属为 Web/Worker 运行用户可写。

本轮完成文章阅读划词解释工具：

- 登录用户在文章中选择文字后，可从阅读工具胶囊打开独立解释面板；工具栏和解释面板均支持打开/关闭、拖动、内部滚动、停止和仅对供应商失败显示的幂等重试。
- 解释请求按文章、账户和请求记录隔离，使用文章标题、摘要、标签和当前一级标题作为上下文；图片、链接及其他非纯文本内容在调用前移除，结果只保存安全中文 Markdown，不执行代码或工具。
- 新增管理员“内容与互动”解释配置（默认每日 50 次、每分钟 5 次、选区 1000 字、本地历史 30 条），个人设置支持按账户记忆是否自动接受该文章的首次授权；限额在 AGENT 调用前裁决，拒绝时不消耗模型额度、不发通知。
- 解释任务复用现有 Endpoint、AGENT、Prompt、TaskRun、租约、取消、token reservation 和审计 owner；停止会同步取消未完成调用，晚到结果不会覆盖已停止请求。文档审核和题库生成保持非流式协议，本轮不启用流式输出。
- 前端工具按钮改用可见的酒红色 Lucide `wrench` 图标，并支持工具按钮再次点击关闭阅读工具；并发解释请求的停止、状态轮询和重试互不覆盖。
- 新增 accounts/agents/discovery/navigation/operations 兼容迁移，生产发布前需新鲜数据库备份后按依赖顺序执行迁移，并为已有站点配置、AGENT profile 和任务状态做只读读回；不迁移 Labs 测试账户、解释历史或模型调用数据。
- 验证：前端构建、Node 前端回归、`git diff --check`、Labs live/ready 与桌面/窄屏主题读回通过；测试文件仅保留在 Labs 工作区供回归，不纳入交付提交。正式部署前仍需执行隔离 PostgreSQL 迁移计划、候选镜像构建、生产健康检查和历史错误状态核对。

## 本轮正式部署记录（2026-09-12）

- 正式提交：`8cfe88086bc3c5546ec8055f80b7def8d5fe079e`；任务分支已推送并 fast-forward 集成到远端 `main`，随后删除远端任务分支。
- 正式应用镜像：`kaj-blog-web:8cfe880`，镜像 manifest `sha256:83ab872684fea0ce409c55646a731261af9e56707ff12a5d6aa6a37256abe2ee`；Web、Worker、Beat 使用同一镜像，旧镜像 `kaj-blog-web:5053a67804ee` 保留用于应用回退。
- 本轮迁移 `accounts.0009_account_article_explanation_auto_accept`、`agents.0010_article_explanation_profile`、`discovery.0005_article_explanation_request`、`navigation.0008_article_explanation_settings`、`operations.0008_article_explanation_usage` 已在生产执行成功；候选 `check --deploy`、`makemigrations --check --dry-run` 和迁移计划均通过。
- 发布前备份：`pre-deploy-8cfe880-20260912T111924Z.dump`（SHA-256 `a8da894de01a9594d95dd3b26426af3beea38368c5f6b2eddcf62e49099f57dd`）、`pre-deploy-8cfe880-20260912T111924Z-media.tar.gz`（SHA-256 `b6b161b87a72900b70678d47bdeb556bb1c36d9004984785f328906b5f285360`）和 Compose 快照（SHA-256 `ce64232048b520eb6fbf397dfe7f5a1afc761870dbef035fd6beab8b60884dc4`）均保存于正式备份目录并设为 `0600`；custom dump 的 `pg_restore --list` 读回 1014 个条目。
- 生产初始化：文章解释 AGENT profile 已绑定现有启用 Endpoint，使用真实 Endpoint 严格 schema 检查成功（`SCHEMA_SUPPORTED`）后启用；站点默认用户限制为每日 50 次、每分钟 5 次、选区 1000 字、本地历史 30 条。不迁移 Labs 账户、解释历史或模型调用数据。
- 状态修复：回收 1 个过期健康任务并重放 2 个历史孤儿重试；读回活动招聘检查、运行中来源、非终态 TaskRun、待发布 Outbox 和处理中消费者均为 0。没有手动抓取招聘来源。
- 生产读回：`/health/live=200`、`/health/ready=200`、主页/登录页/文章详情 200、知识答题和招聘入口按权限重定向，静态 JS/CSS 200；Web/Worker 健康且重启次数为 0，Beat 正常运行。
- 回退边界：仅回退 Web/Worker/Beat 到旧镜像，不反向迁移数据库；备份、媒体、Compose 快照和旧镜像均保留。正式部署未复制 Labs 数据，也未在发布窗口触发招聘全量采集。

## 质量与发布状态

- Labs 服务必须保持 `active/running`，`https://labs.kajspace.cn/health/live` 返回 `200`。
- 新增前端改动完成后先生成对应 `static/dist/` 产物，再做 Labs 读回。
- 新增迁移、持久化、队列或跨模块契约必须补充隔离验证和正式部署步骤。
- 未经明确授权，不执行生产迁移、备份、镜像切换、服务重启、来源抓取或 Git 提交/推送。
- 下一轮正式公告形成前，先把本节所有新增记录与部署执行记录核对，禁止只凭上下文补写。

## 后续维护

本轮候选 SHA、镜像 digest、数据库迁移、备份摘要、错误状态修复、健康检查、关键页面读回、回退边界和未执行项已在上方补录；下一轮 Labs 切片继续追加到本文件，并在下一次正式发布时新增独立部署记录。
