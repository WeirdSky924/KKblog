# 2026-10-17 正式增量更新计划

状态：待执行，正式执行结果写入同目录 `deployment-record.md`。

## 前置门禁

1. 核验 `origin/main`、Labs worktree、正式 Web/Worker/Beat 镜像和生产 migration leaf。
2. 完成静态构建、候选镜像构建、候选 `check --deploy`、migration drift、migration plan、Compose/health 检查。
3. 读回生产待修正的招聘状态；只允许通过 `apps.opportunities.services.recovery.recover_expired_check_runs` 修正孤儿来源明细。
4. 迁移有变化时先创建权限 `0600` 的数据库 dump、媒体归档和 Compose 快照，并校验大小、摘要和可读性。

## 生产顺序

1. 写入宿主 Nginx 维护标记，确认公网返回维护响应，保留旧应用容器。
2. 在候选 Web 容器执行 `migrate --plan` 和必要的 `migrate --noinput`；迁移失败立即停止，不切换应用。
3. 运行候选 `collectstatic --noinput`，切换 Web、Worker、Beat 到候选镜像并读回容器 health、restart count 和应用 `/health/live`、`/health/ready`。
4. 运行一次有界招聘恢复 service，确认无活动运行、无活动来源明细和父运行汇总一致；不调用 adapter。
5. 读回匿名首页、公开岗位页、公开答题入口和安全的公开密码重置页；确认新迁移记录和关键表约束。
6. 只有候选和恢复后的旧应用健康检查均通过，才移除维护标记；更新正式 Compose 快照。

## 回退边界

- 候选应用健康失败时恢复 Web/Worker/Beat 到旧镜像，不反向迁移数据库。
- 迁移失败时不切换应用，保留维护标记、旧镜像和备份。
- 状态修正失败时保留数据库前向状态，停止发布并记录实际错误；不直接 SQL 改写状态、不删除招聘记录。
