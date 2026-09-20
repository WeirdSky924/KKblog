# 2026-09-20 公开岗位性能增量部署方案

状态：已执行（2026-09-20，Asia/Shanghai）。本轮只切换 Web、Worker、Beat 应用镜像；不执行生产 migration、招聘采集、Provider/AGENT 调用或数据修复。

## 候选边界

- 源码提交：`42adeb4ceb74ec5823df70a66144b21b80b0f275`。
- 旧应用镜像：`kaj-blog-web:451bc9f`。
- 候选应用镜像：`kaj-blog-web:42adeb4ceb74`。
- Caddy、PostgreSQL、Redis、Umami、Mailpit、数据库、媒体和静态目录原地保留。
- 岗位公开 query owner 合并筛选选项查询、复用来源计数，并让 HTMX fragment 跳过未使用摘要。

## 发布门禁

1. 候选镜像从远端 `main` 对应提交构建并记录不可变镜像 ID。
2. 候选容器执行 `check --deploy`、`makemigrations --check --dry-run` 和生产 `migrate --plan`；只读迁移计划必须为空。
3. 发布前创建并校验 PostgreSQL custom dump、媒体归档和 Compose 快照，权限为 `0600`。
4. 停止 Beat/Worker 新任务入口，先切换 Web 并验证健康，再切换 Worker，最后恢复 Beat。
5. 发布后只读验证健康端点、岗位列表/搜索/筛选/分页和静态资源；不执行恢复、Outbox 补偿或招聘检查。

## 回退边界

若候选 Web/Worker/Beat 不健康，只回退这三个应用服务到 `kaj-blog-web:451bc9f`；不反向 migration、不删除备份、不修改数据库事实。
