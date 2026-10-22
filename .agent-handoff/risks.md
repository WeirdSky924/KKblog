# Risks, Blockers, And Unknowns

## Current Blockers

- 当前发布没有未解决的部署、数据或交付阻塞。

## Current Risks

- 正式环境已前向应用 `navigation.0009_focus_mode_settings`；如需应用回退，应恢复旧镜像并保留数据库向前状态，不反向删除该 migration。DB、媒体和 Compose 备份位于 `/home/code/personal-blog/var/production/backups/`，不得进入 Git 或宽泛清理。
- 用户明确保留手机版阅读模式、分页手势、专注全屏及光效的真实设备验收；本轮未启动浏览器。这些限制不影响已完成的构建、隔离回归、迁移和运行时读回，但不能宣称已通过最终视觉验收。
- 外部 P0 公网并发复测仍未执行；本轮健康检查、页面读回和发布验证不能替代独立 P0 性能证据。
- Labs Outbox service 保持既有 `failed` 诊断状态且 `MainPID=0`，timer inactive；本轮只停止服务进程，没有 `reset-failed`、清理事件或改写队列状态。相关历史 transport failure 根因仍待单独调查。
- 生产岗位状态只读审计为终态父运行活动来源 `0`、活动父运行 `0`、活动来源 `0`、运行中岗位 TaskRun `0`；因此本轮没有执行状态写修复、恢复 service、Provider/AGENT 或招聘采集。
- Labs P12 容器已停止但数据卷保留；若后续恢复 Labs，必须先读当前 service/worktree 和数据目标，不能把残留卷误当作空库。

## Unknowns / Confirmations Needed

- UNKNOWN: 用户实机是否确认手机版阅读器的分页/设置浮层与专注模式全屏、失焦恢复和黄红边缘提示；浏览器测试由用户明确留作自行验收。
- UNKNOWN: 外部 P0 测试机何时能读取 PostgreSQL、Redis、TaskRun、Outbox 与 Nginx timing，并完成低风险公网基线。
- UNKNOWN: Labs Outbox 历史 `task.final_failed.v1` transport failure 的独立根因；调查时保留失败事实，不直接清零或删除事件。
- UNKNOWN: 生产知识审核 Endpoint 是否已对当前 row version 严格通过 `knowledge-review.v1` capability check；处理前重新只读核验。

## Risk Guidelines

- 继续维护真实失败状态，不用“成功”覆盖未经证据确认的结果。
- 生产数据写入必须复用领域 service；不得直接 SQL 改写业务状态。
- 下一代理先读本文件与 `snapshot.md`。本轮正式事实以 `docs/releases/2026-10-22-production-increment/deployment-record.md` 为准；下一轮 Labs 内容单独写入新公告台账，不追加到本轮正式公告。
