# 2026-10-22 正式增量更新计划

状态：执行中。仅覆盖本次专注模式、手机版阅读模式、对应缺陷修正和必要的 `navigation.0009_focus_mode_settings` migration。

## 基线与候选

- Git 默认分支从远端新鲜读回；所有 Labs 运行时代码及对应记录在任务分支提交、推送并 fast-forward 到 `main`。
- 候选镜像从当前正式 `kaj-blog-web:2c78cddf92ac` 增量构建，源码 revision 使用本次代码提交完整 SHA。
- 构建前端完整产物后，以 `.dockerignore` 精确放行的 `static/dist/` 进入增量 Docker 构建上下文；不改变 Python/Node 依赖。
- 前端完整构建、聚焦前后端测试、Ruff、`check --deploy`、migration drift、候选 `migrate --plan`、Compose 配置和 `collectstatic` 均通过后，才进入维护窗口。

## 数据与备份

- 已只读核对岗位运行状态：终态运行下活动来源 `0`，活动父运行 `0`，活动来源 `0`，运行中的岗位 TaskRun `0`。本轮不运行招聘 adapter，不执行不必要的数据修复，也不改写真实失败状态。
- 候选 migration 计划须精确确认只有 `navigation.0009_focus_mode_settings`。若计划出现其他 migration，停止并复核来源。
- migration 执行前创建并校验新鲜 PostgreSQL dump、受管媒体归档和 Compose runtime 快照；备份文件权限 `0600`，记录大小、SHA-256、TOC/归档可读性。

## 切换顺序

1. 记录生产容器镜像、revision、health、restart count、migration leaf 和公告查询路径；确认维护标记关闭。
2. 创建维护标记并从公网确认 `503`；保留当前生产应用容器及数据卷。
3. 候选 Web 执行 migration plan 和唯一待执行 migration，再读回字段、默认值、约束和 migration 记录。
4. 候选执行 `collectstatic --noinput`；按项目生产 Compose 定向更新 Web、Worker、Beat，不重建 PostgreSQL、Redis、Caddy、Umami 或 Mailpit。
5. 读回候选容器镜像 revision、健康状态、restart count，loopback 与公网 live/ready、首页、公开文章以及管理员设置入口。
6. 再次只读检查岗位活动运行及终态孤儿来源；仅出现经确认的异常时，通过 `apps.opportunities.services.recovery.recover_expired_check_runs` 的受控调用修正，dispatcher 必须确保不启动采集。
7. 候选和数据库均验证后关闭维护标记；再次读回公网路由和生产 Compose 快照。
8. 停止 Labs Web、Worker、Beat、Outbox service/timer 及本轮使用的 P12 PostgreSQL/Redis/Mailpit 容器。保留所有数据卷和诊断状态。

## 失败与回退

- migration 失败：不切换候选，维护标记保持开启，保留旧应用、数据库和新鲜备份；仅做向前修复。
- 候选健康失败：恢复旧 Web/Worker/Beat 镜像，数据库保持已应用 migration 的前向状态；旧应用兼容该新增列。
- 无法证明候选与旧应用的 loopback health 均符合边界时，不关闭维护标记。
- 不重置或清理 Outbox 失败事实，不运行招聘采集、Provider、AGENT 或真实邮件。
