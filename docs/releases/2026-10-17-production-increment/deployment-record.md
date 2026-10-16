# 2026-10-17 正式增量更新记录

状态：已完成（2026-10-17，Asia/Shanghai）。此文件只记录本轮实际提交、推送、生产更新和 Labs 关闭结果，不以旧发布记录代替读回。

## Git 与候选

- 任务分支：`codex/labs-next-20261013`。
- 本轮提交：`2c78cddf92acf6adf7f33f3c57affa32cada522e`，`feat: 完成本轮 Labs 功能与正式更新准备`。
- 任务分支推送：成功；远端提示仓库已迁移到 `WeirdSky924/KKblog`，本次旧地址推送仍成功。
- `origin/main` fast-forward：成功，远端 `main` 与任务提交一致。
- 基线镜像：`kaj-blog-web:d06af75a9c31`，镜像 ID `sha256:3a293f011f91e68231662939886fb88ed7a9cf230fdcc360c065c6607bcc9ccb`。
- 候选镜像：`kaj-blog-web:2c78cddf92ac`，镜像 ID `sha256:029f2d458e4241813a0550bbfe8d5c6680e9cbf0cdd6384c9857e3f23c836a2e`，OCI revision 为完整源码 SHA `2c78cddf92acf6adf7f33f3c57affa32cada522e`。

## 验证

- `npm run build`：已通过，退出码 `0`。
- `npm run test:frontend`：已通过，`5 passed`；存在项目既有 module-type 性能 warning。
- 招聘恢复聚焦回归：隔离资源下 `11 passed in 120.87s`，退出码 `0`。
- `npm run build`：退出 `0`；`npm run test:frontend`：`5 passed`，只有项目既有 module-type warning。
- 目标非测试 Python Ruff：退出 `0`；修改文件 format check：通过；`git diff --check`：通过。
- `manage.py check --settings=config.settings.test`：无 issues；`check --deploy`：退出 `0`，仅 test settings 的既有 HSTS/SSL/CSRF secure warnings；`makemigrations --check --dry-run`：`No changes detected`。
- 隔离 PostgreSQL/Redis/Mailpit 招聘恢复回归：`11 passed in 120.87s`，退出 `0`；临时测试容器已停止。
- 候选镜像 `check --deploy`：无 issues；候选 migration drift：`No changes detected`；候选 `collectstatic --noinput`：`168 static files copied, 168 post-processed`（临时目录），生产 staticfiles 再收集成功。

## 生产读回

- 数据库备份：`var/production/backups/pre-deploy-2c78cdd-20261016T175249Z.dump`，`291139437` 字节，权限 `0600`，SHA-256 `c90224c7d3d9f00e542938470ec24559cd60e5d37e3f6a03da5c212325de3f93`；`pg_restore --list` 读回 `1043` 条。
- 媒体备份：`var/production/backups/pre-deploy-2c78cdd-20261016T175249Z-media.tar.gz`，`7552953` 字节，权限 `0600`，SHA-256 `3866e436fd05e2a0862c0a25a2bfd200728d29847ccdda0cf12ff796fe9519d6`；归档 `437` 项、无符号链接路径。
- Compose 快照：`var/production/backups/compose.runtime.yaml.pre-2c78cdd-20261016T175249Z`，`6418` 字节，权限 `0600`，SHA-256 `595f48d61d560d157fd8e52f4734badcf3c8ae1fe554df0c1162e3be39853597`。
- 维护页开启后公网返回 `503`；应用迁移成功后移除维护标记。
- 生产迁移成功应用 `accounts.0010_account_author_permission_requested_at`、`accounts.0011_admin_password_reset`、`comments.0006_guestbook_board`、`comments.0007_guestbook_daily_quotas`；候选读回无待执行 migration，字段、表、索引和约束存在。
- Web/Worker/Beat 均为 `kaj-blog-web:2c78cddf92ac`；Web/Worker `healthy`、Beat `running`，三者 restart count 均为 `0`。Caddy、PostgreSQL、Redis、Umami、Mailpit 未重建。
- 状态修正前：终态 `PARTIAL` 父运行对应一条来源明细为 `RUNNING`，TaskRun 已 `succeeded`，父汇总失败为 `30`；状态修正后：来源为 `FAILED`、错误码 `opportunities.check_run_orphaned.v1`，父汇总失败为 `31`，活动运行和活动来源明细均为 `0`。候选 Beat 使用恢复 owner 完成修正；随后手动空 dispatcher 复核返回 `recovered=0 redispatched=0 stalled=0 reconciled=0`，未派发采集。
- 生产运行聚合：`opportunity_check_run` 无 `PENDING/RUNNING/CANCEL_REQUESTED`，`opportunity_check_run_source` 无 `PENDING/RUNNING`，机会相关 `running TaskRun=0`；Outbox `published=761`。
- 公网读回：`/health/live=200`、`/health/ready=200`、首页 `200`、公开岗位入口 `302`。

## Labs 收尾

- Labs 关闭前：Web/Worker/Beat 为运行态，Outbox service 已为失败态、timer 已停止；本轮未启动或重置 Outbox。
- Labs 关闭后：`kaj-labs.service`、`kaj-labs-worker.service` 为 `inactive/dead`；`kaj-labs-beat.service`、`kaj-labs-outbox.service` 为 `failed` 且 `MainPID=0`；`kaj-labs-outbox.timer` 为 `inactive/dead`；worktree 无残留 Labs 进程，Labs 公网 health 返回 `502`。
- Labs 测试 PostgreSQL/Redis/Mailpit 临时容器已停止并清理；生产机会浏览器服务未停止。数据卷、媒体、备份和凭据保留，未删除。
