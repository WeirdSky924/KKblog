# 2026-10-11 正式增量更新执行记录

状态：已完成正式增量更新与定向状态修复（2026-10-11，Asia/Shanghai）。Nginx marker 已移除、公网读回正常；4 个来源因实际响应错误/超时继续保留 `STALE`。

## Git 与候选

- 最终生效提交：`32c3d20`、`affa569`、`c4041bb`、`a201b05`、`4156a90`、`d06af75`；生产部署代码 revision 为 `d06af75a9c315a9966d612a34a9ba27211629583`。
- Web 基线 `kaj-blog-web:42adeb4ceb74` ID `sha256:26caccd5272c9173252504d578846f1e21287700c9981a6b2814749fb7c0aaf8`；候选 `kaj-blog-web:d06af75a9c31` ID `sha256:3a293f011f91e68231662939886fb88ed7a9cf230fdcc360c065c6607bcc9ccb`，revision `d06af75a9c315a9966d612a34a9ba27211629583`。
- Caddy 保持 `kaj-blog-caddy:2cbead0`，image ID `sha256:99002dff038d0ead4b5118dddcf56843f30da5465de32561418a9e999ac6a885`。
- Web/Worker/Beat 最终均为候选镜像，容器 ID 分别以 `b80cdf5c`、`295bf941`、`4e494ca8` 开头；健康状态正常，restart count 为 0。Compose 文件位于 `/home/code/personal-blog/var/production/`。

## 生产只读基线

- `/health/live`：`200`；`/health/ready`：`200`。
- learning migration leaf：`0013_generation_batches`；候选预期前进到 `0015_quiz_attempt_mode_db_default`。
- 35 条已启用来源为 `STALE`：浏览器 socket 错误 26、响应契约错误 8、请求超时 1；没有 `PENDING/RUNNING/CANCEL_REQUESTED` 来源检查。
- browser sandbox 为 `kaj-opportunity-browser.service=active/running`；版本化目录为 `/home/code/personal-blog/var/opportunity-browser/releases/d06af75a9c315a9966d612a34a9ba27211629583`。socket mode `0660`、UID/GID `999:10001`，Worker 内外 inode `26:16256418` 一致。
- 公网入口由宿主 Nginx 所有。维护期间 `/run/kaj-production-maintenance.enabled` 使公网返回 `503` 和 `no-store`/`Retry-After: 120`，并可用代理头直连 Web loopback；完成后 marker 已移除。
- Caddy 容器运行 development profile、位于宿主 Nginx 后，保持基线 `2cbead0`。

## 正式执行读回

- 候选 `check --deploy` 无问题，migration drift 为 `No changes detected`；正式 plan 精确包含 `learning.0014` 和 `0015`。迁移前 `learning_quiz_attempt` 实有 10 条记录、关系总大小 `212,992` 字节。
- PostgreSQL dump：`var/production/backups/pre-deploy-20261011-4156a9065ed1.dump`，262,962,700 字节，SHA-256 `9dae86c6250d3510d972d7b03c78439b32aff76fe63c0da65cc42e229fba053e`，`0600`；`pg_restore --list` 读回 1043 项。
- 媒体归档：`var/production/backups/pre-deploy-20261011-4156a9065ed1-media.tar.gz`，7,056,912 字节，SHA-256 `d5e7a08d7e1c6f37b3367412ec9ac31722082ab03319bc8e883d5b19dded9a50`，`0600`；读回 418 项。
- Compose runtime 快照 SHA-256 `551d7819ba4a9248711e063add07305b5ee5a7a9bbd7d37c84eb16050e60479f`；database 快照 SHA-256 `66de976a5175f274751d2b438845130585e5d16019d50cf50b66d5f602b00622`；两者均为 `0600`。
- Migration：`learning.0014_quizattempt_mode_and_more`、`learning.0015_quiz_attempt_mode_db_default` 均 `OK`；模式约束存在、DB default 为 `'EXAM'::character varying`，10 条既有记录均为 `EXAM`。
- `collectstatic --noinput`：168 files copied、4 post-processed。Web/Worker healthy，Beat running，restart count 均为 0。
- 35 条不同来源的最新人工检查：30 `SUCCEEDED`/`HEALTHY`；1 `TRUNCATED`/`DEGRADED`（ByteDance）；4 `FAILED`/`STALE`（Qcraft timeout、2 Hotjob response invalid、1 Meituan response invalid）。没有直接 SQL 改写状态、每日全量检查或 Provider/AGENT 调用；无活动检查运行。
- 全部启用来源最终聚合：123 `HEALTHY`、2 `DEGRADED`、4 `STALE`。
- 最终公网 `/`、`/health/live`、`/health/ready`、岗位列表、CSS 和 JS 均 `200`；答题入口匿名访问按权限 `302` 到登录。生产登录态答题流未执行。
- Labs Web、Worker、Beat、Outbox service/timer 均 `inactive/dead`；P12 PostgreSQL/Redis/Mailpit 均 `Exited (0)`，未删除测试卷或数据。
- 定向检查期间 PostgreSQL backend 两次以 exit-code 2 退出并执行自动 WAL recovery。数据库容器 restart count 为 0、OOM 为 false，之后恢复 healthy；内核日志未发现 OOM。原因未知，作为独立运维调查跟进。
