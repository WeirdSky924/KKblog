# 正式增量部署方案

## 1. 范围与输入

- 代码候选：任务分支合入远端 `main` 后的不可变提交；上一正式基线为 `e5adc20`。
- 来源配置：`config/opportunity_sources.v1.json`（既有 41 条）和 `config/opportunity_sources.additions-2026-08-29.all.json`（新增 109 条，最终状态含停用项）。
- 发布类型：前向增量。当前候选没有新增 Django migration 文件，仍必须以正式库的 `migrate --plan` 结果为准。
- 不在本次窗口迁移岗位、采集快照、审核记录、TaskRun、Invocation、token reservation、媒体或 Labs 账号数据。

## 2. 发布前只读核验

1. 核对远端 `main` 指向本次候选提交，候选工作树不含 `.env`、`.venv`、`var/`、数据库、媒体、日志、缓存或浏览器产物。
2. 串行运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run python manage.py check`、`uv run python manage.py makemigrations --check --dry-run` 和受影响 pytest；前端按项目脚本生成 `static/dist/`。
3. 构建带完整 Git SHA 的 Web、Worker、Beat 和 Caddy 候选镜像，记录镜像摘要；候选镜像只使用生产环境注入的密钥，不把密钥写入镜像或日志。
4. 在正式服务上只读记录 Web/Worker/Beat/Caddy/PostgreSQL/Redis/Umami 的镜像、RestartCount、工作目录、migration leaf、表计数、媒体目录和健康状态。
5. 执行候选 `docker/scripts/deploy --dry-run --migration-state <current|pending>`，确认顺序为备份（仅 pending 时需要）→维护→迁移→应用切换→健康读回。

## 3. 备份与维护窗口

1. 若 `migrate --plan` 有待执行项，先在正式 PostgreSQL 创建新的 custom-format dump，并按 `docs/operations/backups.md` 生成媒体归档；记录文件权限、大小和 SHA-256。`pg_restore --list` 成功只能证明结构可读，不等于恢复演练完成。
2. 记录当前应用镜像和备份 ID，保留旧镜像与备份，不覆盖历史归档。
3. 进入维护窗口，停止 Web、Worker、Beat 的写入进程；PostgreSQL、Redis、Umami、Caddy 和数据卷保持原位。迁移无待执行项时可跳过停写和迁移，但仍需按候选健康顺序读回。

## 4. 数据库与错误状态修复

1. 执行 `python manage.py migrate --plan`；有待执行项时只执行前向 `python manage.py migrate`，不执行反向迁移。
2. 读回 `showmigrations`、关键索引/约束和 `makemigrations --check`。如果本次生产基线没有待迁移项，记录“无 migration，跳过迁移前备份”或按运维政策仍保留备份，不把代码提交当作迁移成功。
3. 在新 Worker 可用且数据库连接健康后，运行一次有界的机会检查租约恢复入口（等价于 `recover_check_leases_task`）。它会用新连接协调过期 TaskRun、来源明细和 OpportunityCheckRun，并只重新派发到期且可恢复的运行；不得直接执行来源采集函数。
4. 读回以下不变量：没有过期租约继续标为 `running`；活动运行只有一个；来源 `RUNNING` 与 TaskRun 租约一致；终态运行不再被每日调度复用；失败状态保留安全错误码和通知去重事实。
5. 不直接修复或删除无法确认归属的生产行。若恢复入口发现结构矛盾，停止发布并保留 ID、状态和安全错误码，交由人工审计。

## 5. 来源配置导入（不触发爬取）

1. 候选镜像内先执行 dry-run：

   ```bash
   python manage.py import_opportunity_sources \
     --input config/opportunity_sources.additions-2026-08-29.all.json
   ```

2. 通过后，在维护窗口内执行同一文件的 `--apply`。该命令只校验并 upsert 来源、允许域名和适配器参数，重置新增来源的运行态为 `NEVER`、公开状态为 false，不调用 HTTP、浏览器或 Celery 检查。
3. 读回新增来源总数 109、启用 88、停用 21、允许域名、适配器分布（Beisen 56、Feishu 26、Hotjob 18、Moka 9）以及岗位/快照/任务历史没有被导入。
4. 不在发布脚本中调用 `request_source_check`、`request_scheduled_full_check` 或任何 adapter `collect()`。等待既有每日定时任务在下一个计划窗口发起首次采集；本轮不人为提前执行。

## 6. 应用切换与读回

1. 先启动候选 Web，确认 `/health/live` 和 `/health/ready` 为 200，再启动 Worker，最后启动 Beat；三者使用同一镜像摘要和生产 Agent/SMTP 环境文件。
2. 执行 `collectstatic --noinput`，不使用 `--clear`；确认 Caddy 能读取新哈希静态资源和既有媒体。
3. 依次读回主页、文章 Markdown/Tiptap、登录、答题入口、找工作公开页/收藏页、管理导航、来源配置和通知中心。检查无持续 5xx、404、静态资源错误、OOM 或循环重启。
4. 关闭维护页前再次读回 live/ready 和关键用户路径；记录候选摘要、迁移 leaf、来源导入计数和状态修复结果。

## 7. 回退与后续观察

- 候选应用不健康：只恢复旧 Web/Worker/Beat/Caddy 镜像，数据库保持前向；临时关闭新增入口，不反向迁移。
- 迁移、备份或来源导入失败：停止切换，保留维护页和现场日志，不重试破坏性动作。
- 首次定时采集由 Celery 负责，观察每个来源的终态、发布时间覆盖率、截断/失败通知和公开岗位数量；不要把“导入成功”解释为“岗位已爬取”。
