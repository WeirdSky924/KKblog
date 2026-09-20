# 2026-09-20 正式增量部署记录

状态：已完成（Asia/Shanghai）。本记录不包含密码、API Key、Cookie、连接串、正文或个人数据。

## Git 与镜像

- 源码提交：`42adeb4ceb74ec5823df70a66144b21b80b0f275`，提交信息 `perf: 优化公开岗位列表查询`。
- 远端 `main` 已 fast-forward 包含该提交；任务分支已推送后删除。
- 候选镜像：`kaj-blog-web:42adeb4ceb74`。
- 候选镜像 ID：`sha256:26caccd5272c9173252504d578846f1e21287700c9981a6b2814749fb7c0aaf8`。
- 旧镜像：`kaj-blog-web:451bc9f`，ID `sha256:9d4874f56871b7fb3815b582613be24a556e560b604b901a3fc10bcc9f54e5cf`，保留回退。

## 只读预检与备份

- 候选 `check --deploy`：退出 0，无问题。
- 候选 `makemigrations --check --dry-run`：退出 0，`No changes detected`。
- 正式 `migrate --plan`：退出 0，`No planned migration operations`；本轮未执行 migration。
- PostgreSQL dump：`var/production/backups/pre-deploy-42adeb4ceb74-20260920T103510Z.dump`，176,670,834 字节，SHA-256 `2bcba6826b2b0c350d475ff63e9157a4c5e129f8c5d283ac806060bf744c4b4e`，权限 0600；`pg_restore --list` 读回 1043 条。
- 媒体归档：`var/production/backups/pre-deploy-42adeb4ceb74-20260920T103510Z-media.tar.gz`，7,024,193 字节，SHA-256 `e34f7ccd69de09dfbd9c7097a687bdb24fe95dad2f647d453df88883c24ae04e`，权限 0600；读回 410 个成员。
- Compose 快照：`var/production/backups/compose.runtime.yaml.pre-42adeb4ceb74-20260920T103510Z`，6,413 字节，SHA-256 `4a945ddc3b91751ac3b59c47db3ed61321efdc3ed48599647c7ccdd0fded9792`，权限 0600。

## 切换与发布后读回

- 变更前 Web/Worker/Beat 均为旧镜像、healthy、RestartCount 0；live/ready 和岗位搜索均为 200。
- 按 Beat/Worker 停止、Web、Worker、Beat 顺序切换；Caddy、PostgreSQL、Redis、Umami、Mailpit 未替换。
- 发布后 Web/Worker/Beat 均为候选镜像，healthy/running，RestartCount 0；启动时间约为 18:40–18:42（Asia/Shanghai）。
- 发布后 `/health/live`、`/health/ready`、默认列表、`job_q=python`、`recruitment_types=CAMPUS`、`job_page=2`、`/static/dist/app.js` 和 `/static/dist/styles.css` 均为 HTTP 200。
- 最近 2 分钟 Beat 日志未出现 `opportunities-daily-check`/`schedule_daily_check`；Web/Worker/Beat 日志未出现 `Traceback`、`ERROR` 或 `CRITICAL`。
- 本轮未执行招聘采集、Provider/AGENT、恢复入口、Outbox 补偿或生产数据写入。

## 回退边界

候选异常时只将 Web、Worker、Beat 回退至 `kaj-blog-web:451bc9f`；不反向 migration、不删除备份、不清理旧镜像或生产数据。
