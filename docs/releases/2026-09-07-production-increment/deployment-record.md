# 2026-09-07 正式增量部署记录

状态：已完成（Asia/Shanghai）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## Git、镜像与迁移

- 最终代码提交：`5053a67804ee3a3cd4bb17c827bec04ad99a958a`。
- 新镜像：`kaj-blog-web:5053a67804ee`。
- 新镜像 manifest：`sha256:3c18585579b926fcf2709cf45ea4db6e192066a4431e731badfedff374bd313e`。
- 旧镜像：`kaj-blog-web:87621e821802`，manifest `sha256:65716759c674ef528d3c6df6ac38313289318b8ee7d18a1457585247aa1f037`，仍保留。
- 已应用迁移：`agents.0009_endpoint_timeout_thirty_minutes`、`learning.0013_generation_batches`。
- `makemigrations --check --dry-run` 无漂移；生产 `showmigrations` 两条均为 `[X]`。

## 备份

- PostgreSQL dump：`var/production/backups/pre-deploy-5053a67-20260907T030225Z.dump`，114,858,783 字节，SHA-256 `910d5fcee5a39e2d21605897b3121e7c6abe80aa8a1817cf0c36480e70060ea0`。
- 媒体归档：`var/production/backups/pre-deploy-5053a67-20260907T030225Z-media.tar.gz`，6,298,345 字节，SHA-256 `64e68dda831d14a3818a5252aa934bac475dab60ce4d9d1ce841c617e1186833`。
- Compose 快照：`var/production/backups/compose.runtime.yaml.pre-5053a67-20260907T030225Z`，SHA-256 `ece37b6b4c9e0d57c94a3b49771d83e7f11b9a36d02d62ef5bd3a1ef093672e5`。
- 三份备份权限均为 `0600`；PostgreSQL dump 的 `pg_restore --list` 读回 996 个 TOC 条目，媒体归档目录可正常列出。

## 切换与状态读回

- 两条迁移和 `collectstatic --noinput` 成功；静态文件复制 165 个、未修改 3 个、后处理 4 个。
- Web、Worker、Beat 均使用新镜像并健康；Caddy、PostgreSQL、Redis、Umami 保持原镜像和数据卷。
- `/health/live=200`、`/health/ready=200`、首页 200、登录页 200、CSS/JS 静态资源 200。
- 招聘租约恢复入口返回 `opportunity-recovery:0:0:0`，未调用 adapter、未手动抓取来源。
- 运行中/等待重试 TaskRun、待发布 Outbox、处理中消费者、题库 GENERATING、Agent RUNNING、活动招聘运行和 RUNNING 来源均为 0。
- Outbox 全部 `published`（417），消费者全部 `processed`（513），运维邮件窗口全部 `sent`（102）。
- Outbox 与运维告警补偿入口执行成功且没有新增待处理记录。

## 回退边界

旧镜像、PostgreSQL dump、媒体归档和 Compose 快照均保留。若候选应用异常，只回退 Web/Worker/Beat 到旧镜像；本次迁移为新增兼容结构，不执行反向迁移。发现数据库或数据卷异常时停止自动操作，保留备份并人工审查。
