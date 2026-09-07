# 2026-09-07 正式增量部署方案

状态：已执行。

## 候选边界

- 代码提交：`5053a67804ee3a3cd4bb17c827bec04ad99a958a`。
- 新应用镜像：`kaj-blog-web:5053a67804ee`。
- 旧应用镜像：`kaj-blog-web:87621e821802`，部署后保留用于回退。
- 只切换 Web、Worker、Beat；Caddy、PostgreSQL、Redis、Umami、Mailpit 和媒体卷不替换。
- 不复制 Labs 账户、文章、岗位、题库、媒体或任务历史；不手动抓取招聘来源。

## 执行顺序

1. 读取生产健康、任务、Outbox 和招聘运行状态。
2. 创建 PostgreSQL dump、媒体归档和 Compose 配置快照，并校验 SHA-256、权限和归档目录。
3. 停止 Beat/Worker，保持 Web 可用，执行两条兼容迁移。
4. 执行 `collectstatic --noinput`，不使用 `--clear`。
5. 重建 Web 并等待健康，再重建 Worker/Beat。
6. 通过现有招聘租约恢复入口执行一次有界恢复；执行 Outbox 与运维邮件补偿入口。
7. 读回健康端点、主要页面、静态资源、迁移、任务、Outbox、消费者和招聘状态。

候选配置通过 `docker compose config --quiet`；Docker Hub 首次元数据请求超时后使用已验证的国内 Debian/Node/Python 镜像参数完成构建。
