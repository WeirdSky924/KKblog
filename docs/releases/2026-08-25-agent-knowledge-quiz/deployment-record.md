# 2026-08-25 正式增量部署记录

状态：已完成。

## 代码与镜像

- Git 提交：`dbbe60c843ba44a27f50ca0dacbb776781f0abe6`
- 候选镜像：`kaj-blog-web:dbbe60c843ba`
- 候选镜像摘要：`sha256:7f470b52373e5cc10ea1d485be1fe6d16e4fa01137994b6fa733e024bf7e575e`
- 远端 `main` 已 fast-forward 包含该提交。

## 数据库与媒体

- 正式 PostgreSQL 迁移前备份：`var/production/backups/pre-dbbe60c-20260825T030104+0800.dump`
- 备份 SHA-256：`72a3f2c051ddae197eac6454d362b51a74932f4363f569e000b468a0f5dc1410`
- 备份格式：PostgreSQL custom dump；`pg_restore --list` 读回成功。
- Migration 从 65 条推进到 87 条；`agents.0001-0008`、`learning.0001-0012`、`media.0007`、`opportunities.0005` 均已应用。
- Endpoint 1 个、Agent Profile 2 个、Prompt 修订 7 条、成功 schema capability 检查 2 条已迁移；自定义 API Key 在迁移过程中按正式 `DJANGO_SECRET_KEY` 重新加密，未写入明文。
- 知识文档 1 份，状态 `APPROVED`；媒体文件 637247 字节，SHA-256 与 Labs/数据库一致。
- 已发布题库系列 1 个，状态 `PUBLISHED/PARTIAL`；两卷 250 + 210 题，共 460 题，知识点 398、覆盖 397、遗漏 1，标签关联 6 条。
- 失败生成历史、活动 reservation、Labs 其他文档和题库未迁移；正式库未覆盖账户。

## 服务读回

- Web、Worker、Beat 均使用候选镜像并保持运行。
- Web/Worker 健康检查为 `healthy`；Worker 探针改为检查实际 Celery 进程，避免 control ping 在 solo Worker 忙碌时误报。
- `https://kajspace.cn/health/live`：200。
- `https://kajspace.cn/health/ready`：200。
- `https://kajspace.cn/question-banks/`：200；第一卷详情：200。
- 正式静态文件已由候选镜像执行 `collectstatic --noinput`，新哈希资源可通过 Caddy 读取。

## 回退边界

旧镜像 `kaj-blog-web:a2e57bb96e8f` 和迁移前数据库备份均保留。应用健康失败时只恢复旧应用镜像，数据库保持前向迁移；不执行反向 migration。
