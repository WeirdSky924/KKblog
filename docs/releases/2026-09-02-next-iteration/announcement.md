# Kaj 空间下一轮更新公告（持续记录）

状态：Labs 迭代中，尚未形成下一次正式发布候选。

## 发布基线

- 当前正式版本：`82df3ccf689a6e48633b9b28ae19ef840266f195`。
- 当前正式应用镜像：`kaj-blog-web:82df3ccf689a`。
- Labs worktree：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- Labs 分支：`codex/labs-next-iteration`。
- Labs 与正式环境共用同一 Git 基线；本轮新增内容只在 Labs 验证，不自动视为正式发布。
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

## 质量与发布状态

- Labs 服务必须保持 `active/running`，`https://labs.kajspace.cn/health/live` 返回 `200`。
- 新增前端改动完成后先生成对应 `static/dist/` 产物，再做 Labs 读回。
- 新增迁移、持久化、队列或跨模块契约必须补充隔离验证和正式部署步骤。
- 未经明确授权，不执行生产迁移、备份、镜像切换、服务重启、来源抓取或 Git 提交/推送。
- 下一轮正式公告形成前，先把本节所有新增记录与部署执行记录核对，禁止只凭上下文补写。

## 正式发布时补录

下一次生产发布完成后，在本目录补充或链接：候选完整 SHA、镜像 digest、数据库迁移、备份摘要、错误状态修复、健康检查、关键页面读回、回退边界和未执行项。本文件在候选完成前保持“Labs 迭代中”。
