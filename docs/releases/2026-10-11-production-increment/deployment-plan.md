# 2026-10-11 正式增量更新方案

状态：代码候选已完成聚焦验证；Git 推送、镜像预检、备份和正式切换待执行。

## 候选范围

- 代码提交：`32c3d20`、`affa569`、`c4041bb`、`f3405b5`、`a201b05`。
- 正式应用基线：`kaj-blog-web:42adeb4ceb74`；正式 Caddy 基线：`kaj-blog-caddy:2cbead0`。正式切换前重新读回不可变镜像 ID。
- 答题 schema 从生产 `learning.0013_generation_batches` 前进至 `learning.0015_quiz_attempt_mode_db_default`，连续执行 `0014` 和 `0015`。
- 生产错误状态仅涉及当前 35 条招聘来源：26 条浏览器 socket 不可用、8 条响应契约错误、1 条请求超时。状态全部为 `STALE` 且来源启用；没有活动来源检查运行。
- 所有修复检查限定在这 35 条来源，使用现有来源检查 service，逐条串行执行；不运行全量定时检查，不调用 Provider/AGENT。

## 发布步骤

1. 在任务分支完成选择性提交、推送、远端默认分支 fast-forward 和读回；公告只列本轮提交。
2. 从当前正式 Web 镜像与当前正式 Caddy 镜像分别构建候选；应用构建复用完整源码 SHA，并在本轮无依赖锁或系统包变化的前提下使用 `Dockerfile.incremental`。
3. 通过候选容器运行 `check --deploy`、`makemigrations --check --dry-run` 和正式 `migrate --plan`；预期只包含 `learning.0014` 与 `learning.0015`。
4. 记录旧应用/Caddy 镜像和运行状态；创建新的 PostgreSQL custom dump、媒体归档与 Compose 快照，均限制为 `0600` 并读回摘要、大小和可读性。
5. 在正式 Caddy config bind 目录创建 `maintenance.enabled`，验证公开请求返回 `503` 且 health 路径保持 `200`；停止 Beat 与 Worker，确认无运行中的来源检查。
6. 用候选镜像执行前向 migration；读回 `0015`、答题模式检查约束和数据库级 `EXAM` 默认值。迁移失败则保持维护页并停止切换。
7. 更新正式 Compose 镜像，先启动 Web 并验证 live/ready，再执行 `collectstatic --noinput`，确认 Caddy 可读取新静态文件；随后重建 Worker 并验证浏览器 socket、最后启动 Beat。
8. 完成答题入口、主页、岗位页、静态资源和健康检查读回后关闭维护标记。再逐条重查固定的 35 个来源，通过现有 service 更新来源状态，并按终态读回数量与错误码。
9. 保留数据库前向状态、旧镜像和新备份；完成后关闭 Labs Web 以及本轮使用的 Labs PostgreSQL/Redis/Mailpit 测试服务，不删除其数据。

## 停止与回退

- 备份、候选预检或 migration 失败时停止后续切换；数据库 migration 失败或不完整时保持维护页。
- 在新用户流开放前候选健康失败，可将应用恢复到记录的旧镜像；数据库不反向迁移。`0014` 和 `0015` 必须一起完成，`0015` 未完成时不得开放旧应用写入。
- 新用户开始创建刷题记录后，旧应用不理解 `PRACTICE` 模式；此后故障采用前向修复，不把旧应用回退作为常规恢复路径。
- 浏览器 socket 或 Worker 健康检查不通过时，不执行招聘来源重查；保留来源错误状态并记录读回结果。
