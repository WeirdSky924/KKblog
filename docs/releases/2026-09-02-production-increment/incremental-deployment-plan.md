# 2026-09-02 正式增量更新准备方案

状态：候选准备中。本目录记录从上一正式基线到本次候选的增量发布输入和执行顺序，不表示正式备份、迁移、镜像替换、服务重启或生产状态修复已经执行。

## 1. 候选边界

- 上一正式基线：`d8aaba9`（以部署窗口重新从远端 `origin/main` 读回为准）。
- 候选来源：本次任务分支合入远端默认分支后的不可变提交；不得使用可变的 `latest` 标签。
- 发布方式：前向增量更新，保留现有账户、文章、评论、通知、媒体、岗位、答题数据和生产数据卷。
- 本轮不把 Labs 的岗位、采集快照、审核、收藏、任务历史、账号或媒体复制到正式环境。
- 本轮不手动触发新招聘来源抓取；来源配置和适配器由候选代码部署后按既有 Celery 计划执行。

## 2. 本轮变更

### 用户可见与性能

- 公开主页统计和文章列表继续由服务端可见性策略提供，查询使用批量计数，避免逐篇 N+1。
- 文章公开列表和通知可见时间增加条件索引，首页、作者页、通知中心和局部刷新减少全量加载。
- 通知详情局部响应不再重新渲染全站 shell；右上角通知浮窗按最多 5 条内容自然撑开，不创建内部滚动条，标题和摘要有界显示。
- 标签筛选、文章目录、书签/点赞和文章动作沿用现有 owner、HTMX 和主题变量，不新增平行路由或数据中心。
- 分区/标签、文章封面和摘要读取保持原有权限、媒体和空态语义。
- 分析脚本的 host URL 使用站点根路径，避免产生重复的 `/analytics/analytics/collect` 路径。

### 可靠性与边界

- 招聘恢复服务只通过 `apps.operations.public` 读取 TaskRun 安全快照，避免跨模块读取 operations 私有模型。
- 过期租约、终态 TaskRun 但领域运行仍为活动状态的孤儿运行，统一由 recovery owner 协调来源明细、领域运行和后续派发。
- 不直接用 SQL 猜测或删除状态；不符合不变量的记录保留安全 ID/错误码并停止，交由人工审计。

## 3. 数据库迁移

候选包含以下前向迁移，正式数量必须以部署窗口的 `migrate --plan` 读回为准：

1. `content.0017_article_public_listing_idx`：为已发布、未删除且有发布时间的文章公开列表增加 `published_at/id` 条件索引。
2. `notifications.0002_visible_time_index`：为未隐藏、未删除通知增加 `created_at/id` 条件索引。

迁移要求：

- 迁移前先运行 `python manage.py migrate --plan`；若无待执行迁移，记录跳过迁移，不执行反向迁移。
- 若有待执行迁移，先创建新鲜 PostgreSQL custom dump 和媒体归档，记录权限、大小、SHA-256 与 `pg_restore --list` 结果。
- 迁移在维护窗口、Web/Worker/Beat 写入静默后执行；不使用 `--fake`、不删除数据、不重建生产卷。
- 迁移成功但候选应用不健康时只回退应用镜像，数据库保持前向结构，并暂时关闭依赖新结构的入口。

## 4. 质量与构建门禁

候选提交后在隔离测试环境串行执行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
npm run build
```

受影响回归至少覆盖：公开主页/文章查询、通知局部响应、阅读书签、招聘租约恢复、operations TaskRun 和架构依赖守卫。测试必须使用项目规定的 loopback PostgreSQL、Redis DB、Mailpit，禁止连接生产或共享数据库。

前端构建产物由 `npm run build` 生成到 `static/dist/`，候选镜像构建时使用该产物；不手改生成文件，不把 `.env`、`.venv`、`var/`、媒体、日志、缓存或测试产物放入镜像。

正式镜像构建要求：Web、Worker、Beat 使用同一完整 Git SHA；Caddy 仅在本轮确认配置有差异时重建。记录镜像 ID 和 digest，禁止以 `latest` 作为唯一回退依据。

## 5. 正式状态修复顺序

在候选 Worker 健康、数据库连接正常且迁移完成后，先执行一次有界的机会检查恢复入口，再允许每日调度创建新运行：

1. 调用现有 `apps.opportunities.recover_check_leases`（或等价的受控任务入口），不要直接调用 adapter `collect()`。
2. 读回过期 TaskRun 租约是否清零；来源 `RUNNING` 是否回到 `PENDING`、安全失败或 `NOT_EXECUTED`；领域 `OpportunityCheckRun` 是否进入正确终态。
3. 读回没有失效的活动运行、没有 `running` TaskRun、没有终态 TaskRun 绑定活动领域运行；失败保留稳定错误码并沿用通知去重。
4. 只有恢复入口完成并通过不变量后，才允许 Beat 的每日上海时间 18:00 调度和每分钟补偿继续工作。
5. 发现多个互相矛盾的运行、未知任务名或无法安全归属的行时停止发布，不删除、不强制改写，保存安全审计证据。

## 6. 应用切换与验收

1. 记录生产 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 当前镜像、RestartCount、工作目录、migration leaf、关键表计数、媒体/静态路径和 live/ready 状态。
2. 若需要迁移，创建备份后启用维护响应并静默 Web/Worker/Beat；PostgreSQL、Redis、媒体和备份卷保持原位。
3. 执行候选迁移，读回 `showmigrations`、索引存在性和关键状态不变量。
4. 先启动候选 Web 并验证 `/health/live`、`/health/ready`，再启动 Worker，最后启动 Beat；三者使用相同候选 digest。
5. 执行 `collectstatic --noinput`，禁止 `--clear`；验证新版本 CSS/JS、KaTeX 字体、头像、封面、正文图片和附件仍可读。
6. 从公网串行读回主页、文章 Markdown/Tiptap、公开作者页、通知中心、登录、答题入口、找工作公开页/收藏页和管理导航。
7. 观察至少一个每日调度/恢复周期的日志、队列和通知状态；本轮不提前抓取新增招聘来源。

## 7. 回退与停止条件

- 备份、迁移计划、候选镜像或健康读回任一失败：停止后续步骤，保留旧应用、数据库和证据。
- 候选应用不健康：只恢复已记录的旧 Web/Worker/Beat/Caddy 镜像，数据库不反向迁移。
- 状态恢复发现无法归属或不变量仍失败：保持维护状态，禁止每日调度和手动抓取，交由人工审计。
- 日志出现持续 5xx、静态/媒体 404、OOM、循环重启、队列重复派发或秘密泄露：立即停止并按运维故障流程处理。
- 未经另一次明确授权，不删除旧镜像、备份、静态指纹、岗位、通知、媒体或任何生产行。

## 8. 执行记录

部署窗口需补录：候选完整 SHA、旧/新镜像 digest、备份摘要、迁移起止时间与 leaf、状态修复结果、健康检查 URL/状态、关键页面读回和剩余风险。本方案本身不构成生产部署完成证明。
