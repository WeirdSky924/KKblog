# 2026-09-14 正式增量部署记录

状态：已完成（2026 年 9 月 14 日，Asia/Shanghai）。

本记录只记录本轮提交对应的正式增量发布，不包含历史迭代记录。记录中不得写入密码、API Key、Cookie、连接串、正文或个人数据。

## Git 与镜像

- 最终提交：`451bc9fd6c039848e13a3f089ba566d33299b044`，提交信息 `fix: 完善文章解释与招聘交互`。
- 任务分支 `codex/20260914-increment` 已推送，远端 `main` 已从 `f134103` fast-forward 到该提交；任务分支随后已删除。
- 新镜像：`kaj-blog-web:451bc9f`；manifest `sha256:9d4874f56871b7fb3815b582613be24a556e560b604b901a3fc10bcc9f54e5cf`。
- 旧镜像：`kaj-blog-web:8cfe880`，保留用于应用回退。

## 迁移与备份

- `migrate --plan`：`No planned migration operations`；`makemigrations --check --dry-run` 无漂移，本轮未执行 migration。
- PostgreSQL dump：`var/production/backups/pre-deploy-451bc9f-20260914T095805Z.dump`，147,010,821 字节，SHA-256 `43032c10ffb142ab677bb91e580b692847c2795c22647e930f83fde4fa01f3c5`；`pg_restore --list` 读回 1043 条，权限 0600。
- 媒体归档：`var/production/backups/pre-deploy-451bc9f-20260914T095805Z-media.tar.gz`，6,781,864 字节，SHA-256 `b30d25652fcb60be6b0a91c80328cb7ace4fc12c4af2ed2d484faa25b7af196f`；371 个成员、路径安全检查通过，权限 0600。
- Compose 快照：`var/production/backups/compose.runtime.yaml.pre-451bc9f-20260914T095805Z`，6,413 字节，SHA-256 `240b9b349cb905f90fdca21d5e605d7ce67c410f5c9686c022bf61ffd96fb7e2`，权限 0600。

## 状态与健康读回

- 发布后立即恢复入口返回 `opportunity-recovery:0:0:0`；Outbox 补偿 `outbox:0:0`，运维告警邮件补偿 `alert-email:0:0`。
- 发布后 Web、Worker、Beat 均为 `kaj-blog-web:451bc9f`、健康且重启计数为 0；Caddy、PostgreSQL、Redis、Umami、Mailpit 未替换。
- 正式读回 live/ready、首页、登录页、招聘页和静态 JS 均为 200；匿名访问 `admin:article-explanation-settings` 返回 403。
- 招聘筛选 `recruitment_types=CAMPUS` 返回 15180 条，岗位搜索“欧洲电商运营”返回 2 条；默认岗位列表发布时间降序读回正常。
- 生产当前 18:00 定时全量招聘检查为有效运行：`OpportunityCheckRun=01M2FNQYPMVX5TTNZFBM7NCD43`、129 个来源、当前 1 个来源运行且租约有效；这不是遗留卡死状态，未取消或手工改写，未手动抓取来源。
- 其他状态读回：待发布 Outbox 0、处理中消费者 0、Agent 运行 0、文章解释运行 0、过期 TaskRun 0。

## 回退边界

候选应用异常时只回退 Web、Worker、Beat 到 `kaj-blog-web:8cfe880`；不反向迁移数据库、不删除备份、不复制 Labs 数据、不手动抓取招聘来源。
