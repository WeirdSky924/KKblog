# 运维入口

本目录是部署、备份、恢复、健康检查和故障处置文档的唯一入口。正式环境已于 2026-10-11 增量更新至应用 revision `d06af75`，实际步骤与读回见[本轮执行记录](../releases/2026-10-11-production-increment/deployment-record.md)。仓库仍没有自动生产部署命令适配器；生产变更按发布记录人工执行并单独授权。

## 当前边界

- 禁止自动部署。部署和服务重启只在用户当前回合明确授权后执行。
- 当前优化阶段默认把每个已验证的修改切片同步到非生产 Labs；它属于测试环境热更新而非生产部署，执行与读回边界见 `testing.md`。
- 2026-10-11 本轮已实际执行生产 migration、发布前备份、应用切换和公网读回；完整恢复演练与 P0 正式性能金丝雀仍未执行。Git 主线提交不自动代表已部署，实际运行版本以对应发布执行记录为准。
- 生产迁移前必须有新鲜备份；迁移失败时停止并保留当前运行版本。
- 生产缺真实域名、管理员邮箱、已认证发件身份、完整 SMTP 传输配置或其他必需秘密时拒绝启动。
- 开发和测试只使用 localhost 身份与 Mailpit，不向真实收件人发信。
- 首版备份目标仅为 local，计划为 Asia/Shanghai 每周一 03:00（`0 3 * * 1`）；任务完成只代表命令与归档成功。隔离测试仅证明 custom dump 可列出，manifest 的 `restore_verified=false`，未执行完整恢复演练。

## 架构来源

- [测试环境与固定命令](testing.md)
- [通用 SMTP 投递](email.md)
- [Migration 验证与兼容记录](migrations.md)
- [备份与人工恢复](backups.md)
- [Umami 同源分析与保留](analytics.md)
- [部署状态机骨架](deployment.md)
- [源码增量镜像构建](incremental-image-build.md)
- [容量保护门禁](capacity-policy.md)
- [性能测试任务与执行记录：P0 正式金丝雀](performance-testing/p0-production-canary.md) / [P0 执行日志](performance-testing/p0-production-canary.execution.md)
- [性能测试任务与执行记录：P1 隔离环境容量](performance-testing/p1-preproduction-load.md) / [P1 执行日志](performance-testing/p1-preproduction-load.execution.md)
- [性能测试任务与执行记录：P2 AGENT 与故障恢复](performance-testing/p2-agent-and-chaos.md) / [P2 执行日志](performance-testing/p2-agent-and-chaos.execution.md)
- [运行、部署与验证架构](../architecture/04-operations-testing.md)
- [后台任务契约](../architecture/contracts/05-background-tasks.md)
- [交换与维护模块](../architecture/modules/10-exchange-analytics-maintenance.md)
- [实施总清单](../planning/implementation-todolist.md)

后续交付只能在本入口下补充可执行且已验证的部署、备份和恢复步骤，不能用建议命令或模拟成功伪装真实生产动作已经运行。
