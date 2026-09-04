# 2026-09-05 Toast 与反馈计数增量部署方案

状态：待正式部署授权。本方案只描述执行顺序，不表示生产动作已经执行。

## 候选边界

- 代码基线：部署窗口重新读取的远端 `origin/main`；本候选当前从 `82df3cc` 创建。
- 变更类型：模板反馈入口、前端 Toast 标记消费、反馈计数解析器、Django `request` context processor 和部署文档。
- 数据库：无 schema 变更、无数据迁移、无 Labs 数据复制。
- 非目标：不抓取招聘来源，不修改岗位/题库/文章/账户数据，不清空缓存或媒体。

## 部署前准备

1. 重新读取远端默认分支、候选完整 SHA、工作区差异和镜像构建上下文；确认不包含凭据、`var/`、`.env`、`.venv`、媒体、日志或测试产物。
2. 串行执行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run python manage.py check`、`uv run python manage.py makemigrations --check --dry-run` 和受影响回归；执行 `npm run build`。
3. 记录生产 Web、Worker、Beat、Caddy、PostgreSQL、Redis 的镜像、工作目录、RestartCount、migration leaf、健康状态和关键失败计数。
4. 本轮没有待执行 migration；仍须在部署窗口运行 `python manage.py migrate --plan`，若出现意外 migration，停止并重新评估，不使用 `--fake`。
5. 在任何生产写操作前，按 `state-repair-runbook.md` 完成只读快照、备份门禁和错误状态恢复确认。

## 应用切换

1. 从候选完整 SHA 构建 Web、Worker、Beat 镜像并记录 digest，禁止使用 `latest` 作为唯一版本标识。
2. 若部署系统要求刷新静态文件，执行 `collectstatic --noinput`，禁止 `--clear`；确认 CSS、JS、字体、头像、封面、正文图片和附件仍可读。
3. 按 Web -> Worker -> Beat 顺序切换，三者使用同一候选 digest；PostgreSQL、Redis 和媒体卷原位保留。
4. 读回 `/health/live`、`/health/ready`、首页、登录页、文章页、通知中心、答题入口、找工作页和管理员反馈页。
5. 观察 Toast 标记在整页和 HTMX 局部刷新各出现一次，并确认动态数字与操作结果一致；不因缺失统计显示 `0`。

## 停止与回退

- 候选构建、健康检查、反馈读回或状态修复任一步失败，停止后续切换并保留旧镜像和证据。
- 应用不健康时只回退 Web、Worker、Beat 应用镜像；本轮无数据库迁移，不执行反向 migration。
- 发现无法归属的招聘运行、未知 TaskRun、重复 Outbox 投递或持续 `core.outbox_transport_failed.v1` 时停止，不直接 SQL 删除或覆盖。
- 未经新的明确授权，不删除旧镜像、备份、媒体、静态指纹、通知、岗位或任务记录。
