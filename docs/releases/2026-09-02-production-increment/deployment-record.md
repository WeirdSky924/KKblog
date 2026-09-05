# 2026-09-02 正式增量执行记录

状态：已完成（2026-09-02，Asia/Shanghai）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## 候选身份

- 任务分支：`codex/labs-next-iteration`
- 候选提交：`82df3ccf689a6e48633b9b28ae19ef840266f195`
- 远端默认分支：`origin/main` 已 fast-forward 至同一提交。
- 上一正式应用镜像：`kaj-blog-web:a7df26300e`，镜像 revision `a7df26300e790505df07ff9d11305f540bcae7d4`（只读读回）。
- 当前正式 Caddy 镜像：`kaj-blog-caddy:2cbead0`（只读读回）。
- 正式 Web/Worker/Beat 镜像：`kaj-blog-web:82df3ccf689a`。
- 正式候选镜像 digest：`sha256:df9720d4e6d8b5bced61a42f7bcd285f121e219f41a0e0108d3cc3c57fbeb363`。
- 正式切换时间：约 `2026-09-02 16:54–17:00`（Asia/Shanghai）；Web 重载 manifest 后最终静态读回约 `17:05`。

## 本地/隔离验证

- `uv run ruff check .`：通过。
- 目标变更文件 `uv run ruff format --check`：通过。
- `uv run ruff format --check .`：通过（1010 个 Python 文件已格式化）。
- `uv run python manage.py check`：通过。
- `uv run python manage.py makemigrations --check --dry-run`：通过，无模型漂移。
- `npm run build`：通过，已生成 CSS、JS、字体产物。
- 前端行为回归 `npm run test:frontend`：`6 passed`；仅有 Node 的既有模块类型提示，不影响退出码。
- 隔离 PostgreSQL/Redis/Mailpit 受影响回归：招聘恢复/架构/operations `27 passed`；阅读书签 `5 passed`。
- `git diff --cached --check`：通过；提交前未发现环境文件、数据库、媒体、日志、缓存或凭据。

## Labs 读回

- `kaj-labs.service` 工作目录：`/home/code/.codex-worktrees/personal-blog/labs-test-environment`。
- 服务状态：`active/running`。
- `https://labs.kajspace.cn/health/live`：HTTP `200`。
- Labs 页面加载 `styles.css?v=notify-height-20260902`。
- Labs 远程 `static/dist/styles.css` SHA-256 与候选 worktree 一致：`6a0d378d637907828c90f5195721da750cc39445b10da5f843b358d9560b2acd`。
- 未登录浏览器可读回首页；通知浮窗的登录态展开未完成，原因是当前主机资源紧张导致点击后的浏览器动作超时；浏览器会话已关闭。

## 正式部署执行结果

以下动作已在本次维护窗口执行并读回：

1. 从候选完整 SHA 构建镜像并记录 digest；Caddy 保持 `2cbead0`。
2. 正式 `migrate --plan` 仅包含 `content.0017`、`notifications.0002`；两条迁移均成功应用，migration 计数为 `89`，迁移后无待执行项。
3. 创建独立数据库 dump `/home/code/personal-blog/var/production/backups/pre-82df3cc-20260902T084739Z.dump`，大小 `93294908` 字节，SHA-256 `c5881c1060b47b65345cd265708ca988658485e8af15d7d8263e0180d2f6365d`；容器内 `pg_restore --list` 读回 `1005` 条。
4. 创建媒体归档 `/home/code/personal-blog/var/production/backups/pre-82df3cc-20260902T084739Z-media.tar.gz`，大小 `5880874` 字节，SHA-256 `6015309bc00d3c9b0ff9cb43b3c169ed2419013fff89a9ca9f2e572f5a428a8b`，归档路径安全检查通过；旧 Compose 备份保留。
5. 停止旧 Web/Worker/Beat 后启动候选服务；候选 Web/Worker/Beat、PostgreSQL、Redis、Umami、Caddy 均正常运行，应用容器 RestartCount 为 `0`。
6. 执行 `collectstatic --noinput`，复制 `165` 个静态文件，未使用 `--clear`；重载 Web manifest 后新 CSS、JS、导航脚本、主题脚本和字体均返回 HTTP `200`。
7. 执行有界 `apps.opportunities.recover_check_leases`，结果 `opportunity-recovery:0:0:0`；后续 Beat 每分钟恢复任务持续成功，队列深度为 `0`。
8. 读回活动检查、未完成来源、running TaskRun 和租约均为 `0`；未手动触发招聘来源抓取。
9. 读回 `/health/live`、`/health/ready`、主页、文章、知识、招聘、通知和关键静态资源均为 `200`；候选日志无持续 `5xx`、重复 `/analytics/analytics/collect` 或迁移错误。

## 保留与后续观察

- 旧镜像 `kaj-blog-web:a7df26300e`、Caddy 镜像、Compose 备份、数据库 dump 和媒体归档均保留，未执行清理。
- 未导入或抓取招聘来源，未复制 Labs 岗位、任务历史、账号、媒体或收藏；首次新增来源采集继续等待既有 Celery 计划。
- 维护停止旧应用时容器记录 `exit=137`，随后候选容器均健康且无当前 OOM 内核记录；后续继续观察应用停止优雅性。
- 未提交 `tests/frontend/authoring-import-entry.test.mjs`；该路径匹配项目规则禁止暂存的 `*.test.*` 临时测试文件，仍保留在 Labs worktree 供本地验证。
