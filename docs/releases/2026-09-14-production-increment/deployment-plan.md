# 2026-09-14 正式增量部署方案

状态：待执行；执行完成后以 `deployment-record.md` 为准。

## 候选边界

- 正式旧镜像：`kaj-blog-web:8cfe880`。
- 新镜像：由本轮最终提交构建并使用不可变短 SHA 标签。
- 仅切换 Web、Worker、Beat；不替换 Caddy、PostgreSQL、Redis、Umami、Mailpit 或媒体卷。
- 本轮没有新增迁移；不复制 Labs 账户、文章、岗位、题库、媒体或任务历史，不手动抓取招聘来源。

## 发布前检查

1. 核验远端 `main` 已包含本轮提交，候选镜像构建上下文来自该提交。
2. 执行候选 `check --deploy`、`makemigrations --check --dry-run`、`migrate --plan` 和 Compose 配置校验；确认 migration plan 为空。
3. 创建并校验 PostgreSQL custom dump、媒体归档和生产 Compose 快照，权限设为 `0600`，记录 SHA-256。
4. 读回 Web、Worker、Beat、数据库、Redis、Caddy 和 Beat/Worker 重启计数；确认当前活动任务、Outbox、消费者、招聘运行和 Agent 运行均无异常积压。

## 执行顺序

1. 保持 Web 可用，停止 Beat/Worker 写入任务的入口。
2. 因本轮无待执行迁移，跳过数据库迁移和迁移维护窗口；不得执行 `migrate` 写操作。
3. 使用候选镜像执行 `collectstatic --noinput`，禁止 `--clear`，确认新的 `app.js` 缓存版本可读。
4. 先更新并启动 Web，等待 `/health/live`、`/health/ready` 与首页/登录页通过，再更新 Worker，最后更新 Beat。
5. 运行一次有界的招聘租约恢复与 Outbox/运维告警补偿读回；无异常时不触发来源抓取。
6. 读回关键页面、静态文件、迁移状态、任务状态、招聘运行、Agent/解释运行、Outbox 和消费者状态。

## 停止与回退

- 数据库备份失败、候选配置失败、健康检查失败或旧应用无法恢复时立即停止，保留维护边界和备份，不继续切换。
- 候选应用异常只把 Web、Worker、Beat 恢复到 `kaj-blog-web:8cfe880`；数据库不反向迁移。
- 旧镜像、备份和 Compose 快照保留，不执行清理。
