# 2026-10-11 正式增量更新方案

状态：已执行完成。本轮生产部署代码 revision 为 `d06af75`；migration、应用切换、定向来源检查及公网读回完成。

## 候选范围

- 最终生效提交：`32c3d20`、`affa569`、`c4041bb`、`a201b05`、`4156a90`、`d06af75`；生产部署代码 revision 为 `d06af75`。
- 正式应用基线：`kaj-blog-web:42adeb4ceb74`；正式 Caddy 基线：`kaj-blog-caddy:2cbead0`。最终保持现有 Caddy profile，生产 HTTPS 入口由宿主 Nginx 提供。
- 答题 schema 从生产 `learning.0013_generation_batches` 前进至 `learning.0015_quiz_attempt_mode_db_default`，连续执行 `0014` 和 `0015`。
- 发布前的 35 条目标来源均启用且为 `STALE`：26 条浏览器 socket 不可用、8 条响应契约错误、1 条请求超时；无活动来源检查运行。
- 35 条来源使用现有检查 service 逐条串行执行；未运行全量定时检查，不调用 Provider/AGENT。

## 发布步骤

1. 完成选择性提交、任务分支推送、远端 `main` fast-forward 和远端读回。
2. 从 Web 基线 `kaj-blog-web:42adeb4ceb74` 构建候选 `kaj-blog-web:d06af75a9c31`；Caddy 保持 `kaj-blog-caddy:2cbead0`。
3. 候选 `check --deploy`、migration drift 通过；正式 migration plan 仅包含 `learning.0014` 和 `0015`。
4. 记录旧应用/Caddy 镜像和运行状态；创建新的 PostgreSQL custom dump、媒体归档与 Compose 快照，均限制为 `0600` 并读回摘要、大小和可读性。
5. 使用 Nginx marker 开启维护，确认公网 `503`/响应头和 Web loopback live/ready `200`，然后停止 Beat/Worker。
6. 前向执行 `0014`/`0015`，读回模式约束、数据库级 `EXAM` 默认值及旧答题记录。
7. 切换候选 Web 并运行 `collectstatic`；更新版本化 browser sandbox，重建 Worker 刷新 socket mount，验证 socket 后启动 Beat。
8. 用现有 service 逐条检查 35 条来源并读回终态；完成关键页面、静态和 health 读回后删除 Nginx marker。
9. 保留数据库前向状态、旧镜像和新备份；关闭 Labs Web 与 P12 PostgreSQL/Redis/Mailpit 服务，不删除其数据卷。

## 停止与回退

- 备份、候选预检或 migration 失败时停止后续切换；数据库 migration 失败或不完整时保持维护页。
- 在新用户流开放前候选健康失败，可将应用恢复到记录的旧镜像；数据库不反向迁移。`0014` 和 `0015` 必须一起完成，`0015` 未完成时不得开放旧应用写入。
- 新用户开始创建刷题记录后，旧应用不理解 `PRACTICE` 模式；此后故障采用前向修复，不把旧应用回退作为常规恢复路径。
- 浏览器 socket 或 Worker 健康检查不通过时，不执行招聘来源重查；保留来源错误状态并记录读回结果。
- 定向检查期间 PostgreSQL 两次出现 backend `exit code 2` 并自动 WAL recovery；容器无 restart/OOM，之后恢复健康。根因未知，需单独调查。
