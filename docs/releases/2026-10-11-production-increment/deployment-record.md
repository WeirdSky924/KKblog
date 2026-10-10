# 2026-10-11 正式增量更新执行记录

状态：执行准备中；以下为生产只读基线，尚未执行生产写入、备份、migration 或服务切换。

## Git 与候选

- 代码提交：`32c3d20`、`affa569`、`c4041bb`、`f3405b5`、`a201b05`。
- 任务分支：`codex/labs-production-increment`；远端集成、候选镜像 revision/ID：待完成后填写。
- Web/Worker/Beat 基线镜像：`kaj-blog-web:42adeb4ceb74`；Caddy 基线：`kaj-blog-caddy:2cbead0`。正式镜像 ID 在切换前重新读回。

## 生产只读基线

- `/health/live`：`200`；`/health/ready`：`200`。
- learning migration leaf：`0013_generation_batches`；候选预期前进到 `0015_quiz_attempt_mode_db_default`。
- 35 条已启用来源为 `STALE`：浏览器 socket 错误 26、响应契约错误 8、请求超时 1；没有 `PENDING/RUNNING/CANCEL_REQUESTED` 来源检查。
- 浏览器服务 `kaj-opportunity-browser.service` 为 `active/running`；生产 Worker 容器内配置的 socket 路径不存在。

## 正式执行读回

- 候选构建、`check --deploy`、migration plan：待执行。
- PostgreSQL/媒体/Compose 新鲜备份及其 SHA-256、大小、权限、归档可读性：待执行。
- Caddy 维护开关、`0014+0015` 正向 migration、Web/Worker/Beat/Caddy 镜像切换、`collectstatic`：待执行。
- 35 条来源逐条重查的成功/失败/截断终态及错误码：待执行；不直接 SQL 改写状态。
- 页面、静态资源和健康读回，维护标记清理：待执行。
- Labs Web 和 P12 PostgreSQL/Redis/Mailpit 测试服务停止读回：待执行；不删除数据卷。
