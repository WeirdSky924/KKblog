# 2026-09-14 正式增量部署记录

状态：待执行。

本记录只记录本轮提交对应的正式增量发布，不包含历史迭代记录。记录中不得写入密码、API Key、Cookie、连接串、正文或个人数据。

## Git 与镜像

- 最终提交：待补充。
- 任务分支推送与远端 `main` fast-forward：待补充。
- 新镜像与 manifest：待补充。
- 旧镜像：`kaj-blog-web:8cfe880`，保留用于应用回退。

## 迁移与备份

- migration plan：待补充；本轮预期为空。
- PostgreSQL dump：待补充。
- 媒体归档：待补充。
- Compose 快照：待补充。

## 状态与健康读回

- 活动 TaskRun、招聘运行、运行中来源、Agent/解释运行、待发布 Outbox、处理中消费者：待补充。
- Web/Worker/Beat/Caddy/数据库/Redis/Umami/Mailpit：待补充。
- live/ready、关键页面和静态资源：待补充。

## 回退边界

候选应用异常时只回退 Web、Worker、Beat 到 `kaj-blog-web:8cfe880`；不反向迁移数据库、不删除备份、不复制 Labs 数据、不手动抓取招聘来源。
