# 2026-09-02 正式增量更新检查清单

状态：已执行（2026-09-02）。以下结果以同目录 `deployment-record.md` 的生产读回为准；清单不授权后续生产写操作。

## 候选与 Git

- [ ] 远端默认分支已重新读取，候选任务提交是 `d8aaba9` 的后代且无意外 merge。
- [ ] 任务分支只包含本轮代码、迁移和部署文档；没有 `.env`、`.venv`、`var/`、数据库、媒体、日志、缓存、浏览器产物或秘密。
- [ ] 暂存差异已逐文件复核，未混入无关工作区改动。
- [ ] 远端默认分支读回包含候选提交，任务分支推送和 fast-forward 集成结果已记录。

## 质量与构建

- [ ] `uv run ruff check .` 退出 0。
- [ ] `uv run ruff format --check .` 退出 0。
- [ ] `uv run python manage.py check` 退出 0。
- [ ] `uv run python manage.py makemigrations --check --dry-run` 显示无变更。
- [ ] 隔离 PostgreSQL/Redis/Mailpit 中的受影响回归退出 0；失败项已区分基线失败、环境失败和本轮回归。
- [ ] `npm run build` 退出 0，CSS/JS/字体产物可被候选镜像读取。
- [ ] Web、Worker、Beat 使用同一候选完整 SHA；镜像 ID/digest 已记录，未使用可变 `latest` 作为回退依据。

## 正式只读基线

- [ ] Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 的状态、工作目录、镜像、RestartCount 和 migration leaf 已记录。
- [ ] 变更前 `/health/live`、`/health/ready`、主页、文章、通知、登录、答题、找工作和静态/媒体资源读回正常。
- [ ] 正式数据库、媒体、静态和备份路径仍位于生产专用目录，未指向 Labs。
- [ ] `python manage.py migrate --plan` 已读回；结果只允许包含 `content.0017`、`notifications.0002` 或明确“无待执行迁移”。

## 备份与迁移

- [ ] 有待迁移时已创建新鲜 PostgreSQL custom dump 和媒体归档，权限、大小、SHA-256、manifest 与 `pg_restore --list` 已记录。
- [ ] 维护响应已从公网验证，Web/Worker/Beat 写入已静默；数据库和媒体卷未替换。
- [ ] 迁移仅前向执行，未使用 `--fake`、反向迁移或删除数据。
- [ ] `showmigrations`、索引/约束和关键表计数已读回。

## 错误状态修复

- [ ] 候选 Worker 健康且数据库连接可用后，已运行一次有界 `apps.opportunities.recover_check_leases`。
- [ ] 过期租约为 0；没有 `running` TaskRun、失效来源 `RUNNING` 或终态 TaskRun 绑定活动领域运行。
- [ ] 活动 `OpportunityCheckRun` 只有真实可恢复运行；孤儿运行已安全终结并保留稳定错误码/通知去重事实。
- [ ] 恢复入口没有触发 adapter 采集，没有重复派发同一业务对象。
- [ ] 发现未知任务、矛盾状态或无法归属行时已停止，没有直接 SQL 覆盖或删除。

## 来源与数据边界

- [ ] 本窗口未导入 Labs 岗位、快照、收藏、审核、任务历史、账号或媒体。
- [ ] 本窗口未手动调用 `request_source_check`、`request_scheduled_full_check`、adapter `collect()` 或浏览器采集器。
- [ ] 新来源（如有）只完成配置 dry-run/upsert，保持预期公开/检查初始状态；首次采集等待既有 Beat 计划窗口。
- [ ] 岗位发布时间、来源状态、失败/截断通知和公开数量的观察项已登记。

## 应用切换与验收

- [ ] `collectstatic --noinput` 成功且未使用 `--clear`。
- [ ] 候选 Web 健康后再启动 Worker，最后启动 Beat；服务均为 `active/running`，无循环重启或 OOM。
- [ ] 公开主页、文章 Markdown/Tiptap、作者主页、通知浮窗/详情、登录、答题、找工作公开页/收藏页和管理导航真实读回通过。
- [ ] CSS/JS、KaTeX 字体、头像、封面、正文图片和附件无静态/媒体 404。
- [ ] 日志无持续 5xx、迁移错误、队列重复派发、秘密泄露或异常状态回退。
- [ ] 旧镜像、备份和回退配置仍保留。

## 记录与回退

- [ ] 执行记录补录候选 SHA、镜像 digest、备份摘要、迁移 leaf、状态修复计数、健康读回和维护窗口。
- [ ] 候选不健康时只恢复旧应用镜像，数据库保持前向；不反向迁移。
- [ ] 未经新的明确授权，不删除旧镜像、备份、静态指纹、岗位、通知、媒体或生产行。
